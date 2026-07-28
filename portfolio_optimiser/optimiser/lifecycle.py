"""Lifecycle modelling for a contribution-funded pot: bootstrap, glidepath, sequence risk.

``report/validate.py`` answers "what happens to a lump sum?". A pension funded by
a monthly contribution stream is a different problem, and three things change:

1. **Effective duration is roughly half the calendar horizon.** The first
   contribution compounds for the full term; the last one for a single month.
   Terminal wealth is therefore dominated by the middle years, not the early
   ones, and quoting a 23-year compound return over the whole pot overstates
   what the money actually earns. ``terminal_wealth_stream`` compounds the real
   cashflow schedule instead.

2. **Sequence-of-returns risk runs the opposite way to decumulation.** A crash
   early in accumulation is a discount on every future contribution; the same
   crash a year before access is a permanent loss on the whole pot. This is what
   licenses an aggressive early allocation, and it is why the sensible glidepath
   is flat-then-declining rather than declining from the start.
   ``sequence_risk_decomposition`` measures the asymmetry directly by dropping
   an identical shock at different points in the path.

3. **Normal returns understate the thing you are being paid to bear.** Monthly
   returns are fat-tailed, left-skewed and serially dependent; drawdowns cluster.
   ``bootstrap_paths`` resamples contiguous blocks of the *observed* history
   (the stationary bootstrap of Politis & Romano, 1994) so crashes arrive with
   their real shape and persistence instead of being averaged away.

Everything here takes an already-optimised weight vector. Nothing in this module
chooses an allocation; it stress-tests one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StreamResult:
    """Terminal-wealth distribution for a contribution stream."""

    months: int
    total_contributed: float
    median_gbp: float
    p5_gbp: float
    p25_gbp: float
    p75_gbp: float
    p95_gbp: float
    median_multiple: float          # terminal / total contributed
    p5_multiple: float
    prob_below_contributions: float  # P(end with less than you paid in)
    money_weighted_return: float     # annualised IRR of the median path
    worst_drawdown_median: float     # median across paths of each path's max DD
    worst_drawdown_p5: float


@dataclass
class GlidepathComparison:
    static: StreamResult
    glidepath: StreamResult
    derisk_start_month: int
    derisk_months: int
    terminal_defensive_frac: float


# ---------------------------------------------------------------------------
# Stationary block bootstrap
# ---------------------------------------------------------------------------

def bootstrap_paths(
    returns: pd.DataFrame,
    n_paths: int,
    n_months: int,
    seed: int,
    block_mean: int = 12,
) -> np.ndarray:
    """Resample the observed monthly panel into (n_paths, n_months, k) draws.

    Stationary bootstrap: block lengths are geometric with mean ``block_mean``
    and the start index wraps around, which keeps the resampled series
    stationary. Blocks are taken across all columns at once, so the
    cross-sectional correlation structure of each month is preserved exactly --
    including the way correlations converge toward one in a crash, which a
    covariance matrix cannot express.

    ``block_mean`` defaults to 12 months: long enough to carry a drawdown and
    its recovery, short enough that paths are not just replays of history.
    """
    panel = returns.dropna(how="any").values
    n_obs = panel.shape[0]
    if n_obs < 24:
        raise ValueError(
            f"Need at least 24 complete monthly observations to bootstrap, got {n_obs}."
        )
    rng = np.random.default_rng(seed)
    p_new_block = 1.0 / block_mean

    # Walk the index forward: with probability p start a fresh random block,
    # otherwise continue the current one (wrapping at the end of the sample).
    idx = np.empty((n_paths, n_months), dtype=np.int64)
    current = rng.integers(0, n_obs, size=n_paths)
    idx[:, 0] = current
    for t in range(1, n_months):
        restart = rng.random(n_paths) < p_new_block
        current = np.where(restart, rng.integers(0, n_obs, size=n_paths), (current + 1) % n_obs)
        idx[:, t] = current
    return panel[idx]


def normal_paths(
    mu_annual: pd.Series,
    cov_annual: pd.DataFrame,
    keys: list[str],
    n_paths: int,
    n_months: int,
    seed: int,
) -> np.ndarray:
    """Multivariate-normal draws, for comparison against the bootstrap.

    Retained deliberately: the report shows both so the reader can see how much
    of the downside a Gaussian model hides.
    """
    rng = np.random.default_rng(seed)
    mean_m = mu_annual.loc[keys].values / 12.0
    cov_m = cov_annual.loc[keys, keys].values / 12.0
    return rng.multivariate_normal(mean_m, cov_m, size=(n_paths, n_months))


# ---------------------------------------------------------------------------
# Contribution accumulation
# ---------------------------------------------------------------------------

def accumulate(
    asset_draws: np.ndarray,
    weight_path: np.ndarray,
    monthly_contribution: np.ndarray,
    opening_balance: float = 0.0,
    monthly_fee: float = 0.0,
    monthly_fee_above: float | None = None,
    fee_threshold_gbp: float | None = None,
) -> np.ndarray:
    """Wealth paths for a contributed, monthly-rebalanced portfolio.

    ``asset_draws``          (n_paths, n_months, k) monthly asset returns
    ``weight_path``          (n_months, k) target weights per month (the glidepath)
    ``monthly_contribution`` (n_months,) cash paid in at the START of each month
    ``monthly_fee``          flat platform fee in currency units, charged monthly

    Contributions are invested at the start of the month and the portfolio is
    rebalanced to target, so the rebalancing bonus shows up in realised growth.
    The flat fee is subtracted in currency terms, which is what a fixed-fee
    platform actually charges -- its drag falls as the pot compounds.

    ``monthly_fee_above`` and ``fee_threshold_gbp`` model a tiered flat fee: once
    a path's balance passes the threshold it pays the higher monthly charge. This
    is per-path, not per-scenario, so a lucky path correctly starts paying the
    larger plan fee sooner.

    Returns (n_paths, n_months) end-of-month wealth.
    """
    n_paths, n_months, _ = asset_draws.shape
    port_returns = np.einsum("pmk,mk->pm", asset_draws, weight_path)
    tiered = monthly_fee_above is not None and fee_threshold_gbp is not None

    wealth = np.empty((n_paths, n_months))
    balance = np.full(n_paths, float(opening_balance))
    for t in range(n_months):
        balance = (balance + monthly_contribution[t]) * (1.0 + port_returns[:, t])
        if tiered:
            fee = np.where(balance > fee_threshold_gbp, monthly_fee_above, monthly_fee)
            balance = np.maximum(balance - fee, 0.0)
        elif monthly_fee:
            balance = np.maximum(balance - monthly_fee, 0.0)
        wealth[:, t] = balance
    return wealth


def recentre(returns: pd.DataFrame, target_annual_mu: pd.Series) -> pd.DataFrame:
    """Shift a historical panel so its mean matches a forward-looking view.

    A raw bootstrap of 2003-2026 would project the returns that *happened* --
    a period containing an exceptional US equity run -- rather than the returns
    the CMAs say to expect. That is a straightforwardly optimistic assumption and
    it would also be inconsistent with the optimiser, which is driven by the
    CMAs.

    So we subtract each column's realised mean and add the CMA monthly mean. The
    result keeps everything the history is actually good evidence for --
    volatility, skew, fat tails, correlation structure, the tendency of losses to
    arrive in runs -- while the level of returns comes from the stated
    assumptions, where it belongs.
    """
    keys = list(returns.columns)
    missing = set(keys) - set(target_annual_mu.index)
    if missing:
        raise ValueError(f"No expected return supplied for: {sorted(missing)}")
    shift = target_annual_mu.loc[keys] / 12.0 - returns.mean()
    return returns + shift


def constant_weight_path(weights: pd.Series, n_months: int) -> np.ndarray:
    """(n_months, k) target-weight matrix that never changes."""
    return np.tile(weights.values, (n_months, 1))


def glidepath_weight_path(
    growth: pd.Series,
    defensive: pd.Series,
    n_months: int,
    derisk_start_month: int,
    derisk_months: int,
    terminal_defensive_frac: float,
) -> np.ndarray:
    """(n_months, k) weights that hold ``growth`` then blend toward ``defensive``.

    Flat at 100% growth until ``derisk_start_month``, then the defensive share
    ramps linearly to ``terminal_defensive_frac`` over ``derisk_months``, then
    holds. Both inputs are indexed on the same union of keys.
    """
    keys = sorted(set(growth.index) | set(defensive.index))
    g = growth.reindex(keys).fillna(0.0).values
    d = defensive.reindex(keys).fillna(0.0).values

    months = np.arange(n_months)
    progress = np.clip((months - derisk_start_month) / max(derisk_months, 1), 0.0, 1.0)
    def_frac = progress * terminal_defensive_frac          # (n_months,)
    return np.outer(1.0 - def_frac, g) + np.outer(def_frac, d)


# ---------------------------------------------------------------------------
# Summarising a set of wealth paths
# ---------------------------------------------------------------------------

def _max_drawdown(wealth: np.ndarray, contributions: np.ndarray) -> np.ndarray:
    """Per-path worst peak-to-trough fall in the *investment* value.

    Contributions keep pushing the balance up, which masks market falls if you
    look at the raw balance. We therefore track wealth net of money paid in to
    date, so the drawdown reflects what the markets did rather than what the
    direct debit did.
    """
    paid_in = np.cumsum(contributions)
    invested_value = wealth / np.maximum(paid_in, 1e-9)   # wealth per £ contributed
    running_max = np.maximum.accumulate(invested_value, axis=1)
    dd = invested_value / running_max - 1.0
    return dd.min(axis=1)


def _irr(cashflows: np.ndarray, terminal: float) -> float:
    """Annualised money-weighted return solving NPV = 0, by bisection.

    Contributions are paid at the START of each month (times 0..n-1) and the pot
    is valued at the END of the last month (time n), matching ``accumulate``.
    """
    n = len(cashflows)
    flows = np.zeros(n + 1)
    flows[:n] = -cashflows.astype(float)
    flows[n] += terminal

    def npv(monthly_rate: float) -> float:
        disc = (1.0 + monthly_rate) ** np.arange(n + 1)
        return float(np.sum(flows / disc))

    lo, hi = -0.99 / 12, 1.0
    if npv(lo) * npv(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return float((1.0 + 0.5 * (lo + hi)) ** 12 - 1.0)


def summarise_stream(
    wealth: np.ndarray, contributions: np.ndarray, label: str = ""
) -> StreamResult:
    terminal = wealth[:, -1]
    total_in = float(contributions.sum())
    max_dd = _max_drawdown(wealth, contributions)
    median_terminal = float(np.median(terminal))
    return StreamResult(
        months=wealth.shape[1],
        total_contributed=total_in,
        median_gbp=median_terminal,
        p5_gbp=float(np.percentile(terminal, 5)),
        p25_gbp=float(np.percentile(terminal, 25)),
        p75_gbp=float(np.percentile(terminal, 75)),
        p95_gbp=float(np.percentile(terminal, 95)),
        median_multiple=median_terminal / total_in if total_in else float("nan"),
        p5_multiple=float(np.percentile(terminal, 5)) / total_in if total_in else float("nan"),
        prob_below_contributions=float((terminal < total_in).mean()),
        money_weighted_return=_irr(contributions, median_terminal),
        worst_drawdown_median=float(np.median(max_dd)),
        worst_drawdown_p5=float(np.percentile(max_dd, 5)),
    )


def terminal_wealth_stream(
    weights: pd.Series,
    returns: pd.DataFrame,
    monthly_contribution: np.ndarray,
    n_paths: int,
    seed: int,
    opening_balance: float = 0.0,
    monthly_fee: float = 0.0,
    block_mean: int = 12,
    draws: np.ndarray | None = None,
) -> StreamResult:
    """Bootstrap the terminal-wealth distribution of a contributed portfolio."""
    keys = list(weights.index)
    n_months = len(monthly_contribution)
    if draws is None:
        draws = bootstrap_paths(returns[keys], n_paths, n_months, seed, block_mean)
    wealth = accumulate(
        draws, constant_weight_path(weights, n_months),
        monthly_contribution, opening_balance, monthly_fee,
    )
    return summarise_stream(wealth, monthly_contribution)


def contribution_schedule(
    monthly_gbp: float, horizon_years: int, escalation_annual: float = 0.0
) -> np.ndarray:
    """(n_months,) contributions, optionally escalating once a year."""
    n_months = horizon_years * 12
    year = np.arange(n_months) // 12
    return monthly_gbp * (1.0 + escalation_annual) ** year


# ---------------------------------------------------------------------------
# Glidepath and sequence risk
# ---------------------------------------------------------------------------

def evaluate_glidepath(
    growth: pd.Series,
    defensive: pd.Series,
    returns: pd.DataFrame,
    monthly_contribution: np.ndarray,
    n_paths: int,
    seed: int,
    derisk_start_month: int,
    derisk_months: int,
    terminal_defensive_frac: float,
    opening_balance: float = 0.0,
    monthly_fee: float = 0.0,
    monthly_fee_above: float | None = None,
    fee_threshold_gbp: float | None = None,
    block_mean: int = 12,
) -> GlidepathComparison:
    """Static max-growth allocation vs the same allocation on a glidepath.

    Both are run on the *same* bootstrap draws, so the comparison is paired and
    the difference is attributable to the glidepath rather than to sampling.
    """
    keys = sorted(set(growth.index) | set(defensive.index))
    n_months = len(monthly_contribution)
    draws = bootstrap_paths(returns[keys], n_paths, n_months, seed, block_mean)

    static_path = glidepath_weight_path(
        growth, defensive, n_months, n_months + 1, 1, 0.0)   # never de-risks
    glide_path = glidepath_weight_path(
        growth, defensive, n_months, derisk_start_month, derisk_months,
        terminal_defensive_frac)

    fee_kw = dict(monthly_fee=monthly_fee, monthly_fee_above=monthly_fee_above,
                  fee_threshold_gbp=fee_threshold_gbp)
    static_w = accumulate(draws, static_path, monthly_contribution, opening_balance, **fee_kw)
    glide_w = accumulate(draws, glide_path, monthly_contribution, opening_balance, **fee_kw)

    return GlidepathComparison(
        static=summarise_stream(static_w, monthly_contribution),
        glidepath=summarise_stream(glide_w, monthly_contribution),
        derisk_start_month=derisk_start_month,
        derisk_months=derisk_months,
        terminal_defensive_frac=terminal_defensive_frac,
    )


def sequence_risk_decomposition(
    weights: pd.Series,
    returns: pd.DataFrame,
    monthly_contribution: np.ndarray,
    n_paths: int,
    seed: int,
    shock: float = -0.40,
    shock_years: tuple[int, ...] = (1, 5, 10, 15, 20, 23),
    opening_balance: float = 0.0,
    monthly_fee: float = 0.0,
    monthly_fee_above: float | None = None,
    fee_threshold_gbp: float | None = None,
    block_mean: int = 12,
) -> pd.DataFrame:
    """Terminal wealth when an identical crash lands in different years.

    The same bootstrap draws are reused for every scenario and a one-month
    ``shock`` return is imposed at the chosen point, so the only thing that
    varies is *when* the crash happens. For an accumulator the result is
    strongly ordered: early crashes cost little because most contributions are
    still to come, late crashes cost the most.
    """
    keys = list(weights.index)
    n_months = len(monthly_contribution)
    base_draws = bootstrap_paths(returns[keys], n_paths, n_months, seed, block_mean)
    w_path = constant_weight_path(weights, n_months)
    fee_kw = dict(monthly_fee=monthly_fee, monthly_fee_above=monthly_fee_above,
                  fee_threshold_gbp=fee_threshold_gbp)

    baseline = summarise_stream(
        accumulate(base_draws, w_path, monthly_contribution, opening_balance, **fee_kw),
        monthly_contribution,
    )

    rows = []
    for year in shock_years:
        month = min(max(year * 12 - 1, 0), n_months - 1)
        shocked = base_draws.copy()
        shocked[:, month, :] = shock                     # every asset falls together
        res = summarise_stream(
            accumulate(shocked, w_path, monthly_contribution, opening_balance, **fee_kw),
            monthly_contribution,
        )
        rows.append({
            "shock_year": year,
            "shock_return": shock,
            "median_gbp": res.median_gbp,
            "vs_baseline_pct": res.median_gbp / baseline.median_gbp - 1.0,
            "p5_gbp": res.p5_gbp,
        })
    out = pd.DataFrame(rows)
    out.attrs["baseline_median_gbp"] = baseline.median_gbp
    return out


# ---------------------------------------------------------------------------
# Fee drag
# ---------------------------------------------------------------------------

def flat_fee_drag(
    wealth_median_path: np.ndarray, monthly_fee: float
) -> pd.DataFrame:
    """Annual flat fee as a percentage of the pot, year by year.

    A flat platform fee is a large percentage drag on a small pot and a rounding
    error on a large one -- the opposite profile to a percentage-fee platform,
    and the reason a flat-fee provider suits a pot that starts at nil and
    compounds for two decades.
    """
    n_months = len(wealth_median_path)
    years = np.arange(n_months) // 12
    rows = []
    for y in np.unique(years):
        pot = float(np.mean(wealth_median_path[years == y]))
        rows.append({
            "year": int(y) + 1,
            "mean_pot_gbp": pot,
            "annual_fee_gbp": monthly_fee * 12,
            "fee_drag_pct": (monthly_fee * 12) / pot if pot > 0 else float("nan"),
        })
    return pd.DataFrame(rows)
