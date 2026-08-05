"""Data acquisition, caching and splicing for the rebalancing study.

Three sources, each probed live before being written into the study:

* **yfinance** -- ETF and index-fund adjusted closes (total return).
* **FRED** (via ``pandas-datareader``) -- GBP/USD, US T-bill, SONIA.
* **LBMA** -- the daily gold PM fix, published in USD *and* GBP since 1968.

Two environment notes that are load-bearing, not trivia:

1. ``yfinance`` defaults to a ``curl_cffi`` session that impersonates Chrome's
   TLS fingerprint. Behind a TLS-terminating egress proxy that handshake is
   reset, and every download silently returns an empty frame. Passing a plain
   ``curl_cffi`` session fixes it. See :func:`_yahoo_session`.
2. Stooq -- the fallback named in the brief -- now serves a JavaScript
   proof-of-work challenge to non-browser clients and returns HTML rather than
   CSV. It is therefore *not* used. FRED and LBMA replace it, and for gold
   LBMA is a strictly better source: an actual fixing, in both currencies,
   with 24 more years of history than any gold ETF.

Every raw download is cached to ``data/rebalancing/cache/`` as CSV and the
cache is committed, so the study reproduces byte-for-byte with no network.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from src.rebalancing.config import CACHE_DIR

LBMA_GOLD_PM_URL: Final = "https://prices.lbma.org.uk/json/gold_pm.json"
_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Forward-filling a price is fine over a holiday; over a fortnight it is
# fabrication. Anything longer than this is a hard error.
MAX_FFILL_DAYS: Final = 5

# Splice quality gates on the overlap-window daily-return correlation.
SPLICE_CORR_WARN: Final = 0.97
SPLICE_CORR_FAIL: Final = 0.85


# ---------------------------------------------------------------------------
# Low-level fetchers (cached)
# ---------------------------------------------------------------------------


def _yahoo_session():  # noqa: ANN202 - curl_cffi has no useful public type
    """A ``curl_cffi`` session with browser impersonation *disabled*.

    yfinance's default ``impersonate="chrome"`` session is reset by a
    TLS-terminating proxy; a plain session negotiates normally.
    """
    from curl_cffi import requests as curl_requests

    return curl_requests.Session(headers={"User-Agent": _USER_AGENT})


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{name}.csv"


def _read_cache(name: str) -> pd.DataFrame | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index.name = "date"
    return frame


def _write_cache(name: str, frame: pd.DataFrame) -> None:
    frame = frame.copy()
    frame.index.name = "date"
    frame.to_csv(_cache_path(name), float_format="%.10g")


def fetch_yahoo(ticker: str, *, refresh: bool = False) -> pd.DataFrame:
    """Daily OHLCV + adjusted close for ``ticker``, cached to disk."""
    name = f"yahoo_{ticker.replace('^', 'idx_').replace('=', '_').lower()}"
    if not refresh:
        cached = _read_cache(name)
        if cached is not None:
            return cached

    import yfinance as yf

    raw = yf.download(
        ticker,
        start="1970-01-01",
        auto_adjust=False,
        progress=False,
        threads=False,
        session=_yahoo_session(),
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"Yahoo returned no rows for {ticker!r}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns={"Adj Close": "adj_close", "Close": "close"})
    frame = raw[["adj_close", "close"]].astype(float)
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    _write_cache(name, frame)
    return frame


def fetch_fred(series_id: str, *, refresh: bool = False) -> pd.Series:
    """A single FRED series as a float ``Series`` indexed by date."""
    name = f"fred_{series_id.lower()}"
    if not refresh:
        cached = _read_cache(name)
        if cached is not None:
            return cached.iloc[:, 0].astype(float)

    import pandas_datareader.data as web

    frame = web.DataReader(series_id, "fred", "1970-01-01", "2100-01-01")
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    frame = frame.dropna()
    if frame.empty:
        raise RuntimeError(f"FRED returned no rows for {series_id!r}")
    _write_cache(name, frame)
    return frame.iloc[:, 0].astype(float)


def fetch_lbma_gold(*, refresh: bool = False) -> pd.DataFrame:
    """LBMA gold PM fix in USD and GBP per troy ounce, daily since 1968."""
    name = "lbma_gold_pm"
    if not refresh:
        cached = _read_cache(name)
        if cached is not None:
            return cached.astype(float)

    import requests

    response = requests.get(
        LBMA_GOLD_PM_URL, timeout=120, headers={"User-Agent": _USER_AGENT}
    )
    response.raise_for_status()
    payload = json.loads(response.text)
    rows = [
        {"date": row["d"], "usd": row["v"][0], "gbp": row["v"][1]}
        for row in payload
        if row.get("v")
    ]
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    # The 1968-2000 tail carries occasional zero/None placeholders on days the
    # fix did not happen; drop them rather than carry a zero price through.
    frame = frame.replace(0.0, np.nan).dropna()
    _write_cache(name, frame)
    return frame.astype(float)


# ---------------------------------------------------------------------------
# Splicing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpliceSegment:
    """One leg of a spliced series: a return stream and the date it takes over."""

    label: str
    returns: pd.Series
    start: pd.Timestamp | None = None


@dataclass(frozen=True)
class SpliceReport:
    """Diagnostics for one splice join, written to ``results/splices.csv``."""

    series: str
    join_date: pd.Timestamp
    old_label: str
    new_label: str
    overlap_days: int
    overlap_correlation: float
    old_annualised: float
    new_annualised: float


def chain_returns(
    name: str, segments: list[SpliceSegment]
) -> tuple[pd.Series, list[SpliceReport]]:
    """Splice segments by chaining *daily returns*, never by scaling levels.

    Segments are given newest-last. Each join is validated on the overlap
    window. Below :data:`SPLICE_CORR_FAIL` the two series are not measuring
    the same exposure and the run stops rather than quietly producing a
    plausible-looking hybrid; between that and :data:`SPLICE_CORR_WARN` the
    join is allowed but printed as a warning, because a splice that weak is a
    result-limiting compromise the report has to disclose.
    """
    if not segments:
        raise ValueError("no segments to chain")

    reports: list[SpliceReport] = []
    pieces: list[pd.Series] = []

    for index, segment in enumerate(segments):
        seg_start = segment.start
        seg_end = segments[index + 1].start if index + 1 < len(segments) else None
        piece = segment.returns
        if seg_start is not None:
            piece = piece[piece.index >= seg_start]
        if seg_end is not None:
            piece = piece[piece.index < seg_end]
        pieces.append(piece.rename(name))

        if index + 1 < len(segments):
            nxt = segments[index + 1]
            overlap = segment.returns.index.intersection(nxt.returns.index)
            if len(overlap) < 20:
                raise ValueError(
                    f"{name}: splice {segment.label}->{nxt.label} has only "
                    f"{len(overlap)} overlapping days; cannot validate"
                )
            old = segment.returns.loc[overlap]
            new = nxt.returns.loc[overlap]
            corr = float(np.corrcoef(old.values, new.values)[0, 1])
            if corr < SPLICE_CORR_FAIL:
                raise ValueError(
                    f"{name}: splice {segment.label}->{nxt.label} overlap "
                    f"correlation {corr:.3f} < {SPLICE_CORR_FAIL} -- series "
                    "are not measuring the same exposure"
                )
            if corr < SPLICE_CORR_WARN:
                print(
                    f"  [splice warning] {name}: {segment.label} -> "
                    f"{nxt.label} overlap correlation {corr:.3f} "
                    f"(< {SPLICE_CORR_WARN}). Usable, but this is a "
                    "result-limiting compromise -- disclose it."
                )
            years = len(overlap) / 252.0
            reports.append(
                SpliceReport(
                    series=name,
                    join_date=pd.Timestamp(nxt.start),  # type: ignore[arg-type]
                    old_label=segment.label,
                    new_label=nxt.label,
                    overlap_days=len(overlap),
                    overlap_correlation=corr,
                    old_annualised=float((1 + old).prod() ** (1 / years) - 1),
                    new_annualised=float((1 + new).prod() ** (1 / years) - 1),
                )
            )

    chained = pd.concat(pieces).sort_index()
    chained = chained[~chained.index.duplicated(keep="first")]
    return chained, reports


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------


@dataclass
class Panel:
    """Everything the engine needs, on one calendar.

    ``returns`` holds daily *total* returns per asset in the requested
    currency; ``cash`` is the daily risk-free accrual in that currency;
    ``levels`` are cumulative wealth indices normalised to 1.0 at the start.
    """

    returns: pd.DataFrame
    cash: pd.Series
    currency: str
    fx: pd.Series
    usd_returns: pd.DataFrame
    splices: list[SpliceReport]
    sources: dict[str, str]

    @property
    def levels(self) -> pd.DataFrame:
        return (1.0 + self.returns).cumprod()

    def slice(self, start: str | None = None, end: str | None = None) -> Panel:
        mask = pd.Series(True, index=self.returns.index)
        if start is not None:
            mask &= self.returns.index >= pd.Timestamp(start)
        if end is not None:
            mask &= self.returns.index <= pd.Timestamp(end)
        idx = self.returns.index[mask.to_numpy()]
        return Panel(
            returns=self.returns.loc[idx],
            cash=self.cash.loc[idx],
            currency=self.currency,
            fx=self.fx.loc[idx],
            usd_returns=self.usd_returns.loc[idx],
            splices=self.splices,
            sources=self.sources,
        )


def _adj_returns(ticker: str, *, refresh: bool = False) -> pd.Series:
    frame = fetch_yahoo(ticker, refresh=refresh)
    return frame["adj_close"].pct_change().dropna().rename(ticker)


def _rate_to_daily_accrual(rate_pct: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    """Convert an annualised percentage rate into a per-period accrual.

    Accrual is act/365 over the *actual* gap between consecutive calendar
    entries, so a Friday-to-Monday step earns three days of interest rather
    than one. That matters over 35 years: getting it wrong biases the
    risk-free rate used in every Sharpe ratio by roughly a third.
    """
    rate = rate_pct.reindex(calendar.union(rate_pct.index)).ffill().reindex(calendar)
    rate = rate.bfill() / 100.0
    day_count = pd.Series(calendar, index=calendar).diff().dt.days.fillna(1.0)
    return ((1.0 + rate) ** (day_count / 365.0) - 1.0).rename("cash")


def build_panel(
    *,
    currency: str = "GBP",
    refresh: bool = False,
    equity_source: str = "spliced",
) -> Panel:
    """Assemble the daily total-return panel.

    ``equity_source="acwi"`` uses ACWI alone (2008->), the splice-free
    sub-sample used to check that conclusions are not splice artefacts.
    """
    if currency not in {"GBP", "USD"}:
        raise ValueError(f"currency must be GBP or USD, got {currency!r}")

    splices: list[SpliceReport] = []
    sources: dict[str, str] = {}

    # --- equity: spliced global equity total return, USD -------------------
    acwi = _adj_returns("ACWI", refresh=refresh)
    if equity_source == "acwi":
        equity_usd = acwi.rename("equity")
        sources["equity"] = "ACWI (2008-03->), no splice"
    else:
        vfinx = _adj_returns("VFINX", refresh=refresh)
        vtsmx = _adj_returns("VTSMX", refresh=refresh)
        vgtsx = _adj_returns("VGTSX", refresh=refresh)
        # 55/45 US/ex-US approximates MSCI ACWI's US weight through the late
        # 1990s and 2000s. Daily-rebalanced blend, which is what a cap-weighted
        # index is not -- a documented approximation, checked at the splice.
        blend = (0.55 * vtsmx + 0.45 * vgtsx).dropna().rename("blend")
        equity_usd, reports = chain_returns(
            "equity",
            [
                SpliceSegment("VFINX (US only)", vfinx, None),
                SpliceSegment("0.55 VTSMX + 0.45 VGTSX", blend, pd.Timestamp("1996-04-30")),
                SpliceSegment("ACWI", acwi, pd.Timestamp("2008-03-31")),
            ],
        )
        splices += reports
        sources["equity"] = (
            "VFINX -> 0.55*VTSMX+0.45*VGTSX (1996-04-30) -> ACWI (2008-03-31)"
        )

    # --- bonds: intermediate US Treasuries, USD ---------------------------
    vfitx = _adj_returns("VFITX", refresh=refresh)
    ief = _adj_returns("IEF", refresh=refresh)
    bond_usd, reports = chain_returns(
        "bond",
        [
            SpliceSegment("VFITX", vfitx, None),
            SpliceSegment("IEF", ief, pd.Timestamp("2002-07-31")),
        ],
    )
    splices += reports
    sources["bond"] = "VFITX -> IEF (2002-07-31)"

    # --- gold: LBMA PM fix, natively in both currencies --------------------
    gold = fetch_lbma_gold(refresh=refresh)
    sources["gold"] = "LBMA gold PM fix (USD and GBP), 1968->"

    # --- FX and cash -------------------------------------------------------
    fx_usd_per_gbp = fetch_fred("DEXUSUK", refresh=refresh).rename("fx")
    sources["fx"] = "FRED DEXUSUK (USD per GBP)"

    # --- common calendar ---------------------------------------------------
    # US equity/bond trading days are the master calendar: they are the days a
    # UK investor's ETFs could actually have been priced against.
    calendar = equity_usd.index.intersection(bond_usd.index).sort_values()
    calendar = pd.DatetimeIndex(calendar)

    def _align(series: pd.Series, label: str) -> pd.Series:
        joined = series.reindex(series.index.union(calendar)).ffill()
        aligned = joined.reindex(calendar)
        # Detect a stale forward-fill: how many calendar days since the last
        # genuine observation?
        observed = pd.Series(series.index, index=series.index).reindex(
            series.index.union(calendar)
        ).ffill().reindex(calendar)
        stale = (calendar - pd.DatetimeIndex(observed)).days
        first_valid = int(np.argmax(~aligned.isna().to_numpy())) if aligned.isna().any() else 0
        worst = int(np.nanmax(stale[first_valid:])) if len(stale) else 0
        if worst > MAX_FFILL_DAYS:
            bad = calendar[first_valid:][stale[first_valid:] > MAX_FFILL_DAYS]
            raise ValueError(
                f"{label}: forward-filled {worst} calendar days "
                f"(limit {MAX_FFILL_DAYS}); first offender {bad[0].date()}"
            )
        return aligned

    gold_usd_px = _align(gold["usd"], "gold USD")
    gold_gbp_px = _align(gold["gbp"], "gold GBP")
    fx = _align(fx_usd_per_gbp, "GBP/USD")

    usd_returns = pd.DataFrame(
        {
            "equity": equity_usd.reindex(calendar),
            "bond": bond_usd.reindex(calendar),
            "gold": gold_usd_px.pct_change(),
        }
    )

    if currency == "USD":
        returns = usd_returns.copy()
        cash_rate = fetch_fred("DTB3", refresh=refresh)
        sources["cash"] = "FRED DTB3 (US 3M T-bill)"
    else:
        # A USD total-return stream converted to GBP: multiply by the change in
        # GBP purchasing power of a dollar, i.e. divide the level by USD-per-GBP.
        fx_ret = fx.pct_change()
        gbp_factor = 1.0 / (1.0 + fx_ret) - 1.0  # return contribution of FX
        returns = pd.DataFrame(
            {
                "equity": (1 + usd_returns["equity"]) * (1 + gbp_factor) - 1,
                "bond": (1 + usd_returns["bond"]) * (1 + gbp_factor) - 1,
                # Gold uses the LBMA GBP fix directly rather than a synthetic
                # cross -- fewer moving parts, and it is the price a UK
                # investor's ETC actually tracks.
                "gold": gold_gbp_px.pct_change(),
            }
        )
        sonia = fetch_fred("IUDSOIA", refresh=refresh)
        uk_3m = fetch_fred("IR3TIB01GBM156N", refresh=refresh)
        cash_rate = pd.concat([uk_3m[uk_3m.index < sonia.index.min()], sonia]).sort_index()
        sources["cash"] = "FRED IUDSOIA (SONIA), pre-1997 FRED IR3TIB01GBM156N"

    cash = _rate_to_daily_accrual(cash_rate, calendar)

    returns = returns.dropna()
    idx = returns.index
    return Panel(
        returns=returns,
        cash=cash.reindex(idx),
        currency=currency,
        fx=fx.reindex(idx),
        usd_returns=usd_returns.reindex(idx),
        splices=splices,
        sources=sources,
    )


__all__ = [
    "MAX_FFILL_DAYS",
    "Panel",
    "SpliceReport",
    "SpliceSegment",
    "build_panel",
    "chain_returns",
    "fetch_fred",
    "fetch_lbma_gold",
    "fetch_yahoo",
]
