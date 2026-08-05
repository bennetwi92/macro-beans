"""Data validation that runs before any modelling.

The rule here is that nothing is silently dropped. Every check prints what it
found; a check that fails hard raises. Suspicious observations are *flagged
for inspection*, not deleted, because a -12% day in gold is usually a real
day in gold and deleting it would flatter every drawdown number in the study.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.rebalancing.data import Panel, fetch_lbma_gold, fetch_yahoo

# Above these, a daily move is printed for eyeball inspection against known
# events. Not a filter -- a flag.
EXTREME_RETURN: dict[str, float] = {"equity": 0.10, "bond": 0.05, "gold": 0.08}

# Minimum acceptable daily-return correlation between the LBMA fix and GLD.
GOLD_CROSSCHECK_MIN: float = 0.90


@dataclass
class Diagnostic:
    check: str
    detail: str
    status: str  # "ok" | "flag" | "fail"


def _fmt(rows: list[Diagnostic]) -> str:
    width = max(len(r.check) for r in rows)
    return "\n".join(
        f"  [{r.status:>4}] {r.check:<{width}}  {r.detail}" for r in rows
    )


def calendar_gaps(panel: Panel) -> list[Diagnostic]:
    """Gaps in the trading calendar that are longer than a normal holiday."""
    idx = panel.returns.index
    gaps = pd.Series(idx, index=idx).diff().dt.days.dropna()
    big = gaps[gaps > 5]
    rows = [
        Diagnostic(
            "calendar span",
            f"{len(idx)} trading days, {idx.min().date()} -> {idx.max().date()} "
            f"({(idx.max() - idx.min()).days / 365.25:.1f} years)",
            "ok",
        ),
        Diagnostic(
            "calendar gaps >5d",
            f"{len(big)} gaps; largest {int(gaps.max())}d on "
            f"{gaps.idxmax().date() if len(gaps) else 'n/a'}",
            "ok" if len(big) < 30 else "flag",
        ),
    ]
    return rows


def missing_census(panel: Panel) -> list[Diagnostic]:
    rows: list[Diagnostic] = []
    for col in panel.returns.columns:
        n_missing = int(panel.returns[col].isna().sum())
        rows.append(
            Diagnostic(
                f"missing {col}",
                f"{n_missing} NaN of {len(panel.returns)}",
                "ok" if n_missing == 0 else "fail",
            )
        )
    n_cash = int(panel.cash.isna().sum())
    rows.append(
        Diagnostic(
            "missing cash",
            f"{n_cash} NaN of {len(panel.cash)}",
            "ok" if n_cash == 0 else "fail",
        )
    )
    return rows


def extreme_returns(panel: Panel, *, top: int = 5) -> list[Diagnostic]:
    """Flag the largest daily moves per asset so they can be eyeballed."""
    rows: list[Diagnostic] = []
    for col in panel.returns.columns:
        series = panel.returns[col]
        threshold = EXTREME_RETURN.get(col, 0.10)
        breaches = series[series.abs() > threshold]
        worst = series.abs().nlargest(top)
        detail = ", ".join(
            f"{d.date()} {series.loc[d]:+.1%}" for d in worst.index
        )
        rows.append(
            Diagnostic(
                f"extreme {col}",
                f"{len(breaches)} days beyond +/-{threshold:.0%}; largest: {detail}",
                "flag" if len(breaches) else "ok",
            )
        )
    return rows


def dividend_adjustment(tickers: tuple[str, ...]) -> list[Diagnostic]:
    """Confirm the total-return adjustment actually happened.

    ``adj_close / close`` must drift upward over time for a dividend-paying
    fund. A flat ratio would mean the adjustment silently failed and we are
    modelling price return while calling it total return -- an error worth
    roughly 2%/yr on equities, which would swamp every effect in this study.
    """
    rows: list[Diagnostic] = []
    for ticker in tickers:
        frame = fetch_yahoo(ticker)
        ratio = (frame["adj_close"] / frame["close"]).dropna()
        drift = float(ratio.iloc[-1] / ratio.iloc[0] - 1.0)
        years = (frame.index[-1] - frame.index[0]).days / 365.25
        implied_yield = (1 + drift) ** (1 / years) - 1 if years > 0 else 0.0
        ok = implied_yield > 0.001
        rows.append(
            Diagnostic(
                f"TR adj {ticker}",
                f"adj/close drift {drift:+.1%} over {years:.1f}y "
                f"= {implied_yield:.2%}/yr implied distribution",
                "ok" if ok else "fail",
            )
        )
    return rows


def split_check(tickers: tuple[str, ...]) -> list[Diagnostic]:
    """Look for an unadjusted split: a raw price jump with no matching TR move."""
    rows: list[Diagnostic] = []
    for ticker in tickers:
        frame = fetch_yahoo(ticker)
        raw = frame["close"].pct_change()
        adj = frame["adj_close"].pct_change()
        suspect = frame.index[(raw.abs() > 0.30) & ((raw - adj).abs() > 0.20)]
        rows.append(
            Diagnostic(
                f"splits {ticker}",
                "none detected"
                if len(suspect) == 0
                else f"{len(suspect)} suspected: {[d.date() for d in suspect[:3]]}",
                "ok" if len(suspect) == 0 else "fail",
            )
        )
    return rows


def gold_crosscheck() -> list[Diagnostic]:
    """LBMA fix vs the investable ETF, at a frequency the stamps support.

    The comparison has to be made monthly, not daily, and the reason is
    itself a finding worth recording. The LBMA PM fix is struck at 15:00
    London; GLD's close is 16:00 New York, five and a half hours later. The
    two series therefore measure *different overlapping windows* of the same
    market, which drives the same-day return correlation down to ~0.65 while
    the correlation of the underlying prices is essentially perfect. Sampling
    monthly lets the window offset wash out.

    The level check is the one that would catch a genuinely broken series:
    GLD should trail the fix by roughly its 0.40% expense ratio and nothing
    more. That divergence is expected, reported, and deliberately *not*
    corrected -- an investor really does pay it.
    """
    lbma = fetch_lbma_gold()["usd"]
    gld = fetch_yahoo("GLD")["adj_close"]
    idx = lbma.index.intersection(gld.index)
    idx = idx[idx >= pd.Timestamp("2004-12-01")]
    a, b = lbma.reindex(idx), gld.reindex(idx)

    def _corr(freq: str | None) -> float:
        if freq is None:
            ra, rb = a.pct_change(), b.pct_change()
        else:
            ra = a.resample(freq).last().pct_change()
            rb = b.resample(freq).last().pct_change()
        joined = pd.concat([ra, rb], axis=1).dropna()
        return float(np.corrcoef(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1])

    daily, weekly, monthly = _corr(None), _corr("W-FRI"), _corr("ME")
    years = (idx[-1] - idx[0]).days / 365.25
    lbma_cagr = float((a.iloc[-1] / a.iloc[0]) ** (1 / years) - 1)
    gld_cagr = float((b.iloc[-1] / b.iloc[0]) ** (1 / years) - 1)
    gap = lbma_cagr - gld_cagr

    return [
        Diagnostic(
            "gold LBMA vs GLD",
            f"monthly return correlation {monthly:.3f} over {years:.1f}y; "
            f"GLD trails the fix by {gap:.2%}/yr vs its 0.40% expense ratio",
            "ok" if (monthly >= GOLD_CROSSCHECK_MIN and 0.002 < gap < 0.008) else "fail",
        ),
        Diagnostic(
            "gold stamp offset",
            f"same-day corr {daily:.2f} -> weekly {weekly:.2f} -> monthly "
            f"{monthly:.2f}: LBMA fix is 15:00 London, GLD is 16:00 New York. "
            "Cross-asset correlations are therefore computed WEEKLY.",
            "flag",
        ),
    ]


def stamp_offset_impact(panel: Panel) -> list[Diagnostic]:
    """Quantify what the timestamp offsets cost the daily risk numbers.

    Gold is stamped 15:00 London, US funds 16:00 New York, and FRED's GBP/USD
    is a 12:00 New York rate. Non-synchronous stamps bias *daily* cross-asset
    correlation toward zero; short-horizon mean reversion pushes the other
    way. Rather than assume which wins, this measures the net effect by
    annualising the portfolio's volatility from daily returns and from weekly
    returns and reporting the gap.

    Measured result on this data: the daily-sampled figure comes out *higher*
    than the weekly one, so mean reversion dominates the stamp offset and the
    daily-based risk numbers in this study are, if anything, conservative.
    Reported as a flag either way, because the size of the gap is a caveat on
    every volatility and Sharpe figure in the results table.
    """
    weights = np.array([0.60, 0.20, 0.20])
    daily_port = panel.returns.to_numpy() @ weights
    daily_vol = float(np.std(daily_port, ddof=1) * np.sqrt(252))
    weekly = (
        pd.Series(daily_port, index=panel.returns.index)
        .add(1.0)
        .resample("W-FRI")
        .prod()
        .sub(1.0)
        .dropna()
    )
    weekly_vol = float(weekly.std(ddof=1) * np.sqrt(52))
    gap = weekly_vol - daily_vol
    return [
        Diagnostic(
            "vol: daily vs weekly",
            f"60/20/20 annualised vol {daily_vol:.2%} from daily returns vs "
            f"{weekly_vol:.2%} from weekly ({gap:+.2%}). Negative sign = "
            "short-horizon mean reversion outweighs the stamp offset.",
            "flag" if abs(gap) > 0.005 else "ok",
        )
    ]


def fx_sanity(panel: Panel) -> list[Diagnostic]:
    """The GBP/USD series should look like GBP/USD."""
    fx = panel.fx
    return [
        Diagnostic(
            "GBP/USD range",
            f"{fx.min():.3f} - {fx.max():.3f} "
            f"(min {fx.idxmin().date()}, max {fx.idxmax().date()})",
            "ok" if 1.0 < fx.min() < 1.5 and 1.5 < fx.max() < 2.2 else "flag",
        )
    ]


def run_all(panel: Panel, *, verbose: bool = True) -> list[Diagnostic]:
    """Run every check. Raises if any check fails hard."""
    rows: list[Diagnostic] = []
    rows += calendar_gaps(panel)
    rows += missing_census(panel)
    rows += extreme_returns(panel)
    rows += dividend_adjustment(("ACWI", "IEF", "VFINX", "VFITX", "VTSMX", "VGTSX"))
    rows += split_check(("ACWI", "IEF", "VFINX", "VFITX"))
    rows += gold_crosscheck()
    rows += stamp_offset_impact(panel)
    rows += fx_sanity(panel)

    if verbose:
        print(f"\nData validation ({panel.currency}):")
        print(_fmt(rows))

    failures = [r for r in rows if r.status == "fail"]
    if failures:
        raise RuntimeError(
            "data validation failed:\n"
            + "\n".join(f"  {r.check}: {r.detail}" for r in failures)
        )
    return rows


__all__ = ["Diagnostic", "run_all"]
