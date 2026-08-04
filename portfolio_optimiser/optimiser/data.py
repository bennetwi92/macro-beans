"""Total-return history with proxy splicing, GBP conversion, and a CSV cache.

The funds in this universe are young (Avantis UCITS 2024, European defence 2025,
uranium 2022). Feeding 1-3 years of returns into a covariance estimate is a recipe
for instability, so we *splice*:

  * fetch each fund's own GBP total-return series where it exists,
  * fetch a long-history proxy (converted to GBP if it is USD-denominated),
  * use the fund where available and the proxy for the earlier window, joined on
    the overlap so the splice is level-continuous.

All series are resampled to month-end total returns. Results are cached to
``outputs/returns_monthly.csv`` so an annual re-run is reproducible and so the
optimiser can run with no network (pass a CSV).

If the runtime cannot reach market data and no cache/CSV exists, this raises with
a clear message asking the investor to supply a returns CSV.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import Settings, Universe

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"
CACHE = OUTPUTS / "returns_monthly.csv"
FX_TICKER = "GBPUSD=X"  # USD per GBP


def _download(tickers: list[str], start: str) -> pd.DataFrame:
    """Adjusted-close (total-return) prices via yfinance. Lazy import."""
    import yfinance as yf

    data = yf.download(
        tickers, start=start, progress=False, auto_adjust=True, group_by="column"
    )
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]
    else:  # single ticker
        close = data["Close"].to_frame(tickers[0])
    return close.dropna(how="all")


def _to_month_end(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.resample("ME").last()


def _gbp_convert(prices: pd.DataFrame, fx: pd.Series) -> pd.DataFrame:
    """USD price series -> GBP. fx is USD per GBP, so GBP price = USD / fx."""
    fx_aligned = fx.reindex(prices.index).ffill()
    return prices.div(fx_aligned, axis=0)


def _splice(fund: pd.Series, proxy: pd.Series) -> pd.Series:
    """Return one spliced *return* series: proxy returns early, fund returns late.

    Both inputs are price levels. We compute returns from each and concatenate:
    fund returns where the fund exists, proxy returns before the fund's first date.
    This is level-agnostic (we never join prices, only returns), so no scaling
    factor is needed.
    """
    fund = fund.dropna()
    proxy = proxy.dropna()
    proxy_ret = proxy.pct_change().dropna()
    if fund.empty:
        return proxy_ret
    fund_ret = fund.pct_change().dropna()
    first_fund = fund_ret.index.min()
    early = proxy_ret[proxy_ret.index < first_fund]
    return pd.concat([early, fund_ret]).sort_index()


def build_returns(
    universe: Universe,
    settings: Settings,
    keys: list[str] | None = None,
    use_cache: bool = True,
    refresh: bool = False,
) -> pd.DataFrame:
    """Month-end GBP total returns, one column per instrument key (spliced).

    Falls back to the cache, then errors with guidance if data is unreachable.
    """
    keys = keys or universe.keys()

    if use_cache and not refresh and CACHE.exists():
        cached = pd.read_csv(CACHE, index_col=0, parse_dates=True)
        if set(keys).issubset(cached.columns):
            return cached[keys].dropna(how="all")

    try:
        returns = _fetch_and_splice(universe, settings, keys)
    except Exception as exc:  # network/data failure
        if CACHE.exists():
            cached = pd.read_csv(CACHE, index_col=0, parse_dates=True)
            have = [k for k in keys if k in cached.columns]
            if have:
                return cached[have].dropna(how="all")
        raise RuntimeError(
            "Could not fetch market data and no usable cache exists.\n"
            f"Underlying error: {exc}\n"
            "Supply a month-end total-return CSV at "
            f"{CACHE} (date index, one column per instrument key) and re-run."
        ) from exc

    OUTPUTS.mkdir(exist_ok=True)
    # Merge into any existing cache so partial fetches accumulate.
    if CACHE.exists():
        prev = pd.read_csv(CACHE, index_col=0, parse_dates=True)
        merged = prev.combine_first(returns)
        merged.update(returns)
        merged.to_csv(CACHE)
    else:
        returns.to_csv(CACHE)
    return returns


def _fetch_and_splice(
    universe: Universe, settings: Settings, keys: list[str]
) -> pd.DataFrame:
    start = settings.data_start

    # Collect every ticker we need: each fund line + each proxy source + FX.
    fund_tickers = {k: universe.instruments[k].ticker for k in keys}
    proxy_specs = {k: universe.proxies[universe.instruments[k].proxy] for k in keys}
    all_tickers = sorted(
        set(fund_tickers.values())
        | {p.source for p in proxy_specs.values()}
        | {FX_TICKER}
    )

    raw = _download(all_tickers, start)
    raw = _to_month_end(raw)
    fx = raw[FX_TICKER]

    out: dict[str, pd.Series] = {}
    for key in keys:
        fund_tkr = fund_tickers[key]
        spec = proxy_specs[key]

        fund_px = raw[fund_tkr] if fund_tkr in raw.columns else pd.Series(dtype=float)
        proxy_px = raw[spec.source] if spec.source in raw.columns else pd.Series(dtype=float)

        # The FUND line and the PROXY carry independent currencies -- convert each
        # on its own evidence. A `.L` suffix does NOT imply sterling: several funds
        # here list both a GBX and a USD line on the LSE under different tickers.
        #
        # Reading a USD line and skipping the conversion (the pre-2026-08 bug) does
        # not add noise -- it silently models the CURRENCY-HEDGED return, dropping
        # the GBP/USD exposure a sterling investor actually bears. The damage is in
        # the covariance: every genuinely-sterling holding shares one FX factor, so
        # an unconverted USD line looks far less correlated with the rest of the
        # book than it is (IWQU vs AVWC measured 0.79 unconverted, 0.94 correct)
        # and the optimiser rewards it as a diversifier it is not.
        inst = universe.instruments[key]
        if not inst.is_sterling and not fund_px.empty:
            fund_px = _gbp_convert(fund_px.to_frame("p"), fx)["p"]

        if spec.ccy.upper() == "USD":
            proxy_px = _gbp_convert(proxy_px.to_frame("p"), fx)["p"]

        ret = _splice(fund_px, proxy_px)
        out[key] = ret

    df = pd.DataFrame(out).sort_index()
    # Require a minimum overlap so the covariance is well-defined.
    return df.dropna(how="all")


def benchmark_returns(settings: Settings) -> pd.Series:
    """Month-end GBP total returns for the global-tracker benchmark (proxy)."""
    src = settings.benchmark_proxy
    raw = _to_month_end(_download([src, FX_TICKER], settings.data_start))
    px = raw[src]
    if settings.benchmark_proxy_ccy.upper() == "USD":
        px = _gbp_convert(px.to_frame("p"), raw[FX_TICKER])["p"]
    return px.pct_change().dropna().rename("benchmark")
