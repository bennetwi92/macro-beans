"""Statistical machinery: rolling windows, the block bootstrap, crash windows
and correlation regimes.

The purpose of this module is to make it hard to report a single historical
path as if it were an answer. One 35-year path is one draw. Every headline
comparison in the study has to survive being resampled and re-windowed, and
gets a plain-English verdict attached saying whether it did.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.rebalancing.config import RANDOM_SEED, TRADING_DAYS_PER_YEAR, CostModel
from src.rebalancing.engine import run_batch
from src.rebalancing.policies import Policy


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

DISTINGUISHABLE = "distinguishable from noise"
DIRECTIONAL = "directionally consistent but within noise"
INDISTINGUISHABLE = "not distinguishable from noise"


def verdict(share_positive: float) -> str:
    """Turn a bootstrap sign-agreement share into one of three plain labels.

    Deliberately coarse. A two-sided 95% threshold maps to 0.975/0.025; an
    80% majority is worth calling 'directional' but not 'real'. Anything
    reported in the study carries one of these three labels, so no comparison
    can be quoted without its noise verdict attached.
    """
    if share_positive >= 0.975 or share_positive <= 0.025:
        return DISTINGUISHABLE
    if share_positive >= 0.80 or share_positive <= 0.20:
        return DIRECTIONAL
    return INDISTINGUISHABLE


# ---------------------------------------------------------------------------
# Stationary block bootstrap
# ---------------------------------------------------------------------------


def stationary_bootstrap_index(
    n_days: int,
    n_replicates: int,
    mean_block: int,
    *,
    seed: int = RANDOM_SEED,
) -> NDArray[np.int64]:
    """Politis-Romano stationary bootstrap indices, shape ``(B, T)``.

    Blocks have geometrically distributed length with mean ``mean_block``,
    wrapping circularly. Resampling *rows* of the joint return matrix (rather
    than each asset independently) is essential here: it preserves the
    cross-asset correlation structure, which is the whole mechanism under
    test. Shuffling assets independently would destroy the diversification
    return and guarantee a null result.
    """
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    starts = rng.integers(0, n_days, size=(n_replicates, n_days))
    new_block = rng.random((n_replicates, n_days)) < p
    new_block[:, 0] = True

    index = np.empty((n_replicates, n_days), dtype=np.int64)
    current = starts[:, 0].copy()
    for t in range(n_days):
        fresh = new_block[:, t]
        current = np.where(fresh, starts[:, t], (current + 1) % n_days)
        index[:, t] = current
    return index


@dataclass
class BootstrapResult:
    policy: str
    benchmark: str
    n_replicates: int
    mean_block: int
    mean_diff_bps: float
    median_diff_bps: float
    p05_bps: float
    p95_bps: float
    share_policy_wins: float
    verdict: str
    differences_bps: NDArray[np.float64]


def bootstrap_policies(
    returns: pd.DataFrame,
    policies: list[Policy],
    benchmark: Policy,
    target: NDArray[np.float64],
    cost: CostModel,
    *,
    n_replicates: int = 2000,
    mean_block: int = 63,
    seed: int = RANDOM_SEED,
) -> list[BootstrapResult]:
    """Bootstrap the CAGR difference between each policy and ``benchmark``.

    Every policy sees the *same* resampled paths, so the comparison is paired
    and the difference distribution is not inflated by independent sampling
    noise.
    """
    base = returns.to_numpy(dtype=float)
    n_days = len(returns)
    index = stationary_bootstrap_index(
        n_days, n_replicates, mean_block, seed=seed
    )
    years = n_days / TRADING_DAYS_PER_YEAR

    def _cagr(terminal: NDArray[np.float64]) -> NDArray[np.float64]:
        return (terminal / cost.initial_value) ** (1.0 / years) - 1.0

    bench_cagr = _cagr(
        run_batch(base, index, benchmark, target, cost, returns.index)
    )

    results: list[BootstrapResult] = []
    for policy in policies:
        if policy.name == benchmark.name:
            continue
        policy_cagr = _cagr(
            run_batch(base, index, policy, target, cost, returns.index)
        )
        diff = (policy_cagr - bench_cagr) * 1e4
        share = float((diff > 0).mean())
        results.append(
            BootstrapResult(
                policy=policy.name,
                benchmark=benchmark.name,
                n_replicates=n_replicates,
                mean_block=mean_block,
                mean_diff_bps=float(diff.mean()),
                median_diff_bps=float(np.median(diff)),
                p05_bps=float(np.percentile(diff, 5)),
                p95_bps=float(np.percentile(diff, 95)),
                share_policy_wins=share,
                verdict=verdict(share),
                differences_bps=diff,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Rolling windows
# ---------------------------------------------------------------------------


def rolling_window_differences(
    wealth: dict[str, pd.Series],
    benchmark: str,
    *,
    years: int,
    step: int = 21,
) -> pd.DataFrame:
    """CAGR difference vs ``benchmark`` over every overlapping N-year window.

    Overlapping windows are not independent observations and the study says so
    -- they are reported to show *consistency across eras*, which is a
    different question from statistical significance, and the bootstrap
    handles the latter.
    """
    window = int(years * TRADING_DAYS_PER_YEAR)
    dates = wealth[benchmark].index
    if len(dates) <= window:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for start in range(0, len(dates) - window, step):
        end = start + window
        row: dict[str, object] = {
            "start": dates[start],
            "end": dates[end],
        }
        base = wealth[benchmark]
        base_cagr = (base.iloc[end] / base.iloc[start]) ** (1 / years) - 1
        for name, series in wealth.items():
            cagr_n = (series.iloc[end] / series.iloc[start]) ** (1 / years) - 1
            row[name] = float((cagr_n - base_cagr) * 1e4)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Crash windows
# ---------------------------------------------------------------------------


@dataclass
class CrashWindow:
    label: str
    peak: pd.Timestamp
    trough: pd.Timestamp
    depth: float


def find_crash_windows(
    equity_wealth: pd.Series, *, min_depth: float = 0.15
) -> list[CrashWindow]:
    """Locate peak-to-trough equity drawdowns deeper than ``min_depth``.

    Dated off the study's own spliced equity series rather than hard-coded
    from memory, so the windows are consistent with the data actually used.
    Non-overlapping by construction: once a trough is found, the search
    restarts from the date the series regains its prior peak.

    The 15% default is deliberate and currency-driven. In sterling, 2022 was
    a 15.3% equity drawdown, not the 26.4% it was in dollars, because sterling
    fell from 1.35 to 1.07 over the same period and cushioned an unhedged UK
    holder. A 20% screen would silently drop the single event the brief most
    wants examined -- which is itself the finding that unhedged FX dominates
    a UK investor's crash experience.
    """
    values = equity_wealth.to_numpy()
    dates = equity_wealth.index
    windows: list[CrashWindow] = []

    i = 0
    n = len(values)
    while i < n:
        peak_idx = i
        peak = values[i]
        j = i + 1
        trough_idx = i
        trough = peak
        recovered = None
        while j < n:
            if values[j] > peak:
                if (peak - trough) / peak >= min_depth:
                    recovered = j
                    break
                peak, peak_idx = values[j], j
                trough, trough_idx = values[j], j
            elif values[j] < trough:
                trough, trough_idx = values[j], j
            j += 1

        depth = (peak - trough) / peak
        if depth >= min_depth:
            windows.append(
                CrashWindow(
                    label=str(dates[trough_idx].year),
                    peak=dates[peak_idx],
                    trough=dates[trough_idx],
                    depth=float(depth),
                )
            )
            i = recovered if recovered is not None else n
        else:
            break
    return windows


def crash_analysis(
    wealth: dict[str, pd.Series],
    windows: list[CrashWindow],
    *,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    """Per-event policy performance: inside the drawdown, and from the trough.

    Reported per event and never only as a mean. With four events, the mean is
    an average of four numbers and its standard error is enormous; showing the
    four lets a reader see whether the effect is consistent or driven by one
    episode.
    """
    rows: list[dict[str, object]] = []
    for window in windows:
        for name, series in wealth.items():
            row: dict[str, object] = {
                "event": window.label,
                "peak": window.peak.date(),
                "trough": window.trough.date(),
                "equity_depth": round(window.depth, 4),
                "policy": name,
            }
            seg = series.loc[window.peak : window.trough]
            row["drawdown_window_return"] = float(seg.iloc[-1] / seg.iloc[0] - 1)
            for horizon in horizons:
                end = window.trough + pd.DateOffset(years=horizon)
                after = series.loc[window.trough : end]
                if after.index[-1] < end - pd.Timedelta(days=20):
                    row[f"post_{horizon}y_cagr"] = np.nan
                else:
                    row[f"post_{horizon}y_cagr"] = float(
                        (after.iloc[-1] / after.iloc[0]) ** (1 / horizon) - 1
                    )
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Correlation regimes
# ---------------------------------------------------------------------------


def weekly_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Weekly compounding, used for every correlation estimate.

    Daily correlations across these series are contaminated by non-synchronous
    close stamps -- the LBMA gold fix is struck five and a half hours before
    the US close. Weekly sampling removes that artefact at the cost of a
    little precision, which is the right trade when the quantity of interest
    is a regime, not a tick.
    """
    return (1.0 + returns).resample("W-FRI").prod() - 1.0


def rolling_correlation(
    returns: pd.DataFrame, a: str, b: str, *, window_weeks: int = 52
) -> pd.Series:
    weekly = weekly_returns(returns)
    return weekly[a].rolling(window_weeks).corr(weekly[b]).dropna()


def correlation_regimes(returns: pd.DataFrame) -> pd.DataFrame:
    """Unconditional and stress-conditional correlations, by decade.

    The safe-haven claim is a *conditional* one -- gold is supposed to help
    when equities fall hard -- so it is tested conditionally, on the worst 5%
    of equity weeks, as well as unconditionally.
    """
    weekly = weekly_returns(returns).dropna()
    rows: list[dict[str, object]] = []
    # Stress is defined once, on the full sample, and then applied to each
    # sub-period. Using each period's own 5th percentile would redefine
    # "stress" per decade and make the columns incomparable -- and would leave
    # a single calendar year with two observations to correlate.
    stress_threshold = float(weekly["equity"].quantile(0.05))

    def _block(label: str, frame: pd.DataFrame) -> dict[str, object]:
        stress = frame[frame["equity"] <= stress_threshold]
        row: dict[str, object] = {
            "period": label,
            "weeks": len(frame),
            # Reported so a NaN stress correlation is explicable rather than
            # mysterious: a period can simply contain too few bad weeks.
            "stress_weeks": len(stress),
        }
        for other in ("bond", "gold"):
            row[f"corr_equity_{other}"] = float(frame["equity"].corr(frame[other]))
            row[f"corr_equity_{other}_stress"] = (
                float(stress["equity"].corr(stress[other])) if len(stress) >= 6 else np.nan
            )
            row[f"mean_{other}_in_stress"] = (
                float(stress[other].mean()) if len(stress) > 0 else np.nan
            )
        return row

    rows.append(_block("full sample", weekly))
    for decade, frame in weekly.groupby((weekly.index.year // 10) * 10):
        if len(frame) < 52:
            continue
        rows.append(_block(f"{decade}s", frame))
    rows.append(_block("2022 only", weekly.loc["2022"]))
    return pd.DataFrame(rows)


__all__ = [
    "BootstrapResult",
    "CrashWindow",
    "DIRECTIONAL",
    "DISTINGUISHABLE",
    "INDISTINGUISHABLE",
    "bootstrap_policies",
    "correlation_regimes",
    "crash_analysis",
    "find_crash_windows",
    "rolling_correlation",
    "rolling_window_differences",
    "stationary_bootstrap_index",
    "verdict",
    "weekly_returns",
]
