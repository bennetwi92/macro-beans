"""Performance, risk and control metrics, plus the return/risk decomposition.

The decomposition is the part that stops a false winner. Left alone, a
rebalancing study will crown whichever policy drifted hardest into equities
during a 35-year equity bull market, and call it skill. Splitting the excess
return into an *allocation* component and a *rebalancing* component makes that
visible instead of letting it masquerade as edge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.rebalancing.config import ASSETS, TRADING_DAYS_PER_YEAR
from src.rebalancing.engine import BacktestResult, constant_mix


# ---------------------------------------------------------------------------
# Primitive statistics
# ---------------------------------------------------------------------------


def cagr(returns: pd.Series) -> float:
    years = len(returns) / TRADING_DAYS_PER_YEAR
    return float((1.0 + returns).prod() ** (1.0 / years) - 1.0)


def annual_volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe(returns: pd.Series, cash: pd.Series) -> float:
    excess = returns - cash.reindex(returns.index).fillna(0.0)
    vol = excess.std(ddof=1)
    if vol == 0:
        return float("nan")
    return float(excess.mean() / vol * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino(returns: pd.Series, cash: pd.Series) -> float:
    excess = returns - cash.reindex(returns.index).fillna(0.0)
    downside = excess[excess < 0]
    if len(downside) < 2:
        return float("nan")
    dd = np.sqrt((downside**2).mean())
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS_PER_YEAR))


def drawdown_curve(returns: pd.Series) -> pd.Series:
    wealth = (1.0 + returns).cumprod()
    return wealth / wealth.cummax() - 1.0


def max_drawdown(returns: pd.Series) -> float:
    return float(drawdown_curve(returns).min())


def ulcer_index(returns: pd.Series) -> float:
    """Root-mean-square drawdown: penalises depth *and* duration.

    Max drawdown reports one bad day. The Ulcer index reports how long the
    investor spent underwater, which is closer to what makes people abandon a
    policy -- and abandoning the policy is the dominant real-world risk in
    this whole subject.
    """
    dd = drawdown_curve(returns)
    return float(np.sqrt((dd**2).mean()))


def time_underwater(returns: pd.Series) -> float:
    """Share of days spent below a previous high."""
    return float((drawdown_curve(returns) < -1e-12).mean())


# ---------------------------------------------------------------------------
# Policy metrics
# ---------------------------------------------------------------------------


@dataclass
class PolicyMetrics:
    portfolio: str
    policy: str
    family: str
    currency: str
    cost_model: str
    start: str
    end: str
    years: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    ulcer_index: float
    time_underwater: float
    terminal_wealth: float
    trades_per_year: float
    turnover_per_year: float
    cost_drag_bps: float
    total_cost: float
    mean_abs_weight_deviation: float
    max_abs_weight_deviation: float
    mean_equity_weight: float
    max_equity_weight: float
    allocation_effect_bps: float
    rebalancing_effect_bps: float
    cost_effect_bps: float

    def as_row(self) -> dict[str, object]:
        return asdict(self)


def weight_deviation(result: BacktestResult) -> tuple[float, float]:
    """Mean and max absolute deviation of realised weights from target.

    This is the risk-control measure, and arguably the real point of
    rebalancing: it says how far the portfolio wandered from the risk the
    investor signed up for, regardless of whether wandering happened to pay.
    Measured on pre-trade weights, since post-trade weights of a frequent
    rebalancer are target by construction and would flatter it.
    """
    deviation = np.abs(result.weights_predrift - result.target)
    active = result.target > 0
    per_day = deviation[:, active].sum(axis=1) / 2.0  # total misallocation
    return float(per_day.mean()), float(per_day.max())


def cost_drag(net: BacktestResult, gross: BacktestResult) -> float:
    """Annualised CAGR lost to trading, as a decimal.

    Measured as the difference between the identical policy run with and
    without costs, rather than by dividing cumulative fees by a portfolio
    value. Fees paid early compound away for decades, so the naive ratio
    understates the true drag badly -- for a daily rebalancer it reports
    roughly a third of the real number.
    """
    return cagr(gross.returns) - cagr(net.returns)


def decompose(
    result: BacktestResult,
    benchmark: BacktestResult,
    returns: pd.DataFrame,
    *,
    result_gross: BacktestResult,
    benchmark_gross: BacktestResult,
) -> tuple[float, float, float]:
    """Split excess CAGR over ``benchmark`` into allocation / rebalancing / cost.

    * **allocation** -- what a frictionless constant-mix portfolio held at the
      policy's own *realised average weights* earns, versus one held at the
      benchmark's average weights. This is the "you simply held more
      equities" component, and it is not skill.
    * **cost** -- the policy's own gross-minus-net CAGR, net of the
      benchmark's. Exact by construction.
    * **rebalancing** -- the residual. This is the genuine volatility
      harvesting / buy-low-sell-high contribution, and it is usually far
      smaller than people expect.

    The three components sum to the total excess CAGR by construction.
    Returned in basis points per year.
    """
    own_avg = result.weights_predrift.mean(axis=0)
    bench_avg = benchmark.weights_predrift.mean(axis=0)

    allocation = cagr(constant_mix(returns, own_avg)) - cagr(
        constant_mix(returns, bench_avg)
    )
    total = cagr(result.returns) - cagr(benchmark.returns)
    cost = -(cost_drag(result, result_gross) - cost_drag(benchmark, benchmark_gross))
    rebalancing = total - allocation - cost
    return allocation * 1e4, rebalancing * 1e4, cost * 1e4


def summarise(
    result: BacktestResult,
    *,
    portfolio: str,
    family: str,
    cash: pd.Series,
    returns: pd.DataFrame,
    benchmark: BacktestResult,
    result_gross: BacktestResult,
    benchmark_gross: BacktestResult,
    cost_model: str,
) -> PolicyMetrics:
    rets = result.returns
    years = len(rets) / TRADING_DAYS_PER_YEAR
    mean_dev, max_dev = weight_deviation(result)
    allocation, rebalancing, cost_effect = decompose(
        result,
        benchmark,
        returns,
        result_gross=result_gross,
        benchmark_gross=benchmark_gross,
    )
    equity_weights = result.weights_predrift[:, ASSETS.index("equity")]

    total_cost = float(result.cost.sum())
    cost_drag_bps = cost_drag(result, result_gross) * 1e4

    return PolicyMetrics(
        portfolio=portfolio,
        policy=result.policy,
        family=family,
        currency=result.currency,
        cost_model=cost_model,
        start=str(result.dates[0].date()),
        end=str(result.dates[-1].date()),
        years=round(years, 2),
        cagr=cagr(rets),
        volatility=annual_volatility(rets),
        sharpe=sharpe(rets, cash),
        sortino=sortino(rets, cash),
        max_drawdown=max_drawdown(rets),
        ulcer_index=ulcer_index(rets),
        time_underwater=time_underwater(rets),
        terminal_wealth=float(result.value[-1]),
        trades_per_year=result.n_trade_days / years,
        turnover_per_year=float(result.turnover.sum()) / years,
        cost_drag_bps=cost_drag_bps,
        total_cost=total_cost,
        mean_abs_weight_deviation=mean_dev,
        max_abs_weight_deviation=max_dev,
        mean_equity_weight=float(equity_weights.mean()),
        max_equity_weight=float(equity_weights.max()),
        allocation_effect_bps=allocation,
        rebalancing_effect_bps=rebalancing,
        cost_effect_bps=cost_effect,
    )


def metrics_frame(rows: list[PolicyMetrics]) -> pd.DataFrame:
    return pd.DataFrame([r.as_row() for r in rows])


__all__ = [
    "PolicyMetrics",
    "annual_volatility",
    "cagr",
    "decompose",
    "drawdown_curve",
    "max_drawdown",
    "metrics_frame",
    "sharpe",
    "sortino",
    "summarise",
    "time_underwater",
    "ulcer_index",
    "weight_deviation",
]
