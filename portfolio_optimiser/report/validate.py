"""Monte Carlo validation.

  * SIPP (B): 25-year terminal-wealth distribution of the optimised portfolio vs a
    global tracker, simulated jointly so "probability of beating the tracker" is a
    genuine path-by-path comparison.
  * ISA (A): 1-year loss and intra-year max-drawdown distribution -- does the
    portfolio ever breach the liquidity/tail constraint?

Simulation is asset-level with monthly rebalancing to constant target weights, so
the rebalancing bonus shows up in realised geometric growth. Returns are drawn
from a multivariate normal whose monthly mean comes from the CMAs (annual/12) and
whose covariance is the shrinkage estimate (annual/12). Normality understates fat
tails; the CVaR cap already builds in a margin and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..optimiser.config import Settings


@dataclass
class TerminalWealthResult:
    years: int
    median_multiple: float
    p5_multiple: float
    p95_multiple: float
    prob_beat_benchmark: float
    median_benchmark_multiple: float
    realised_geo: float


@dataclass
class DrawdownResult:
    horizon_months: int
    mean_loss: float
    cvar_95: float
    var_95: float
    p95_max_drawdown: float
    worst_max_drawdown: float
    prob_breach_dd: float       # P(max drawdown worse than limit)
    dd_limit: float


def _simulate(mean_m: np.ndarray, cov_m: np.ndarray, n_paths: int, n_months: int,
              seed: int) -> np.ndarray:
    """Return (n_paths, n_months, k) of simulated monthly returns."""
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(mean_m, cov_m, size=(n_paths, n_months))
    return draws


def terminal_wealth(
    weights: pd.Series,
    mu_annual: pd.Series,
    cov_annual: pd.DataFrame,
    bench_returns: pd.Series,
    bench_mu_annual: float,
    asset_returns: pd.DataFrame,
    settings: Settings,
    years: int = 25,
) -> TerminalWealthResult:
    keys = list(weights.index)
    # Build a joint (assets + benchmark) monthly mean/cov so the comparison shares
    # the same market draws.
    joint_ret = asset_returns[keys].join(bench_returns.rename("BENCH"), how="inner").dropna()
    cov_m = np.cov(joint_ret.values, rowvar=False)
    mean_m = np.empty(len(keys) + 1)
    mean_m[:-1] = mu_annual.loc[keys].values / 12.0
    mean_m[-1] = bench_mu_annual / 12.0

    n_months = years * 12
    sims = _simulate(mean_m, cov_m, settings.mc_paths, n_months, settings.random_seed)

    w = weights.loc[keys].values
    port_m = sims[:, :, :-1] @ w                     # (paths, months)
    bench_m = sims[:, :, -1]
    port_tw = np.prod(1 + port_m, axis=1)
    bench_tw = np.prod(1 + bench_m, axis=1)

    realised_geo = float(np.exp(np.log(port_tw).mean() / years) - 1)
    return TerminalWealthResult(
        years=years,
        median_multiple=float(np.median(port_tw)),
        p5_multiple=float(np.percentile(port_tw, 5)),
        p95_multiple=float(np.percentile(port_tw, 95)),
        prob_beat_benchmark=float((port_tw > bench_tw).mean()),
        median_benchmark_multiple=float(np.median(bench_tw)),
        realised_geo=realised_geo,
    )


def drawdown_distribution(
    weights: pd.Series,
    mu_annual: pd.Series,
    cov_annual: pd.DataFrame,
    asset_returns: pd.DataFrame,
    settings: Settings,
    dd_limit: float,
    cvar_alpha: float = 0.95,
    horizon_months: int = 12,
) -> tuple[DrawdownResult, np.ndarray]:
    keys = list(weights.index)
    joint = asset_returns[keys].dropna()
    cov_m = np.cov(joint.values, rowvar=False)
    mean_m = mu_annual.loc[keys].values / 12.0

    sims = _simulate(mean_m, cov_m, settings.mc_paths, horizon_months, settings.random_seed)
    w = weights.loc[keys].values
    port_m = sims @ w                                # (paths, months)

    cum = np.cumprod(1 + port_m, axis=1)
    terminal = cum[:, -1]
    one_year_loss = 1 - terminal                     # +ve = loss
    running_max = np.maximum.accumulate(cum, axis=1)
    drawdowns = cum / running_max - 1                # <= 0
    max_dd = drawdowns.min(axis=1)                   # most negative per path

    var = float(np.percentile(one_year_loss, cvar_alpha * 100))
    tail = one_year_loss[one_year_loss >= var]
    cvar = float(tail.mean()) if tail.size else var

    result = DrawdownResult(
        horizon_months=horizon_months,
        mean_loss=float(one_year_loss.mean()),
        cvar_95=cvar,
        var_95=var,
        p95_max_drawdown=float(np.percentile(max_dd, 5)),  # 5th pct = deep DD
        worst_max_drawdown=float(max_dd.min()),
        prob_breach_dd=float((max_dd < -abs(dd_limit)).mean()),
        dd_limit=dd_limit,
    )
    return result, max_dd
