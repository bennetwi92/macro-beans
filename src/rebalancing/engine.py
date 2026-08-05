"""The backtest engine.

One code path for every policy. The engine holds asset *values* rather than
weights, grows them by daily total returns, and lets the policy decide whether
to trade. Costs are charged on the traded notional and paid out of the
portfolio, so a high-turnover policy is penalised in wealth terms exactly as it
would be in reality.

Two entry points share the same arithmetic:

* :func:`run` -- a single historical path, returning full diagnostics.
* :func:`run_batch` -- thousands of bootstrap replicates stepped
  simultaneously, returning terminal wealth only. Vectorising across
  replicates rather than looping over them is what turns a multi-hour
  bootstrap into a sub-minute one.

Execution convention: trades happen at the *same* close whose prices triggered
them. That is a mild look-ahead -- a real investor sees the close and trades
the next open. :func:`run` therefore accepts ``exec_lag=1`` to defer every
trade by one day, and the study reports both so the reader can see the
convention is not doing any work.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.rebalancing.config import ASSETS, TRADING_DAYS_PER_YEAR, CostModel
from src.rebalancing.policies import Policy


@dataclass
class BacktestResult:
    """Everything downstream analysis needs from one backtest."""

    policy: str
    dates: pd.DatetimeIndex
    value: NDArray[np.float64]
    weights: NDArray[np.float64]
    weights_predrift: NDArray[np.float64]
    turnover: NDArray[np.float64]
    cost: NDArray[np.float64]
    n_trade_days: int
    n_legs: int
    contributed: float
    target: NDArray[np.float64]
    currency: str

    @property
    def returns(self) -> pd.Series:
        """Daily portfolio return, net of costs.

        Derived from the value path *before* contributions are added back, so
        that a contribution is never mistaken for a return.
        """
        return pd.Series(self._net_returns, index=self.dates, name=self.policy)

    _net_returns: NDArray[np.float64] = None  # type: ignore[assignment]

    @property
    def wealth(self) -> pd.Series:
        return pd.Series(self.value, index=self.dates, name=self.policy)

    @property
    def weight_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.weights, index=self.dates, columns=list(ASSETS))


def _contribution_mask(dates: pd.DatetimeIndex) -> NDArray[np.bool_]:
    series = pd.Series(np.arange(len(dates)), index=dates)
    firsts = series.groupby(dates.to_period("M")).min().to_numpy()
    mask = np.zeros(len(dates), dtype=bool)
    mask[firsts] = True
    mask[0] = False
    return mask


def run(
    returns: pd.DataFrame,
    policy: Policy,
    target: NDArray[np.float64],
    cost: CostModel,
    *,
    exec_lag: int = 0,
    monthly_contribution: float = 0.0,
    currency: str = "GBP",
) -> BacktestResult:
    """Run ``policy`` over ``returns`` and return the full diagnostic path."""
    dates = pd.DatetimeIndex(returns.index)
    ret = returns.to_numpy(dtype=float)
    n_days, n_assets = ret.shape
    target = np.asarray(target, dtype=float)

    equity_level = np.cumprod(1.0 + ret[:, 0])
    schedule = policy.schedule_mask(dates, equity_level)
    if exec_lag:
        schedule = np.concatenate([np.zeros(exec_lag, dtype=bool), schedule[:-exec_lag]])

    contrib_days = (
        _contribution_mask(dates)
        if monthly_contribution > 0
        else np.zeros(n_days, dtype=bool)
    )

    spread = np.asarray(cost.spread_vector(), dtype=float) / 10_000.0
    commission = cost.commission_flat

    value = target * cost.initial_value
    weights_out = np.empty((n_days, n_assets))
    weights_pre = np.empty((n_days, n_assets))
    value_out = np.empty(n_days)
    net_returns = np.empty(n_days)
    turnover_out = np.zeros(n_days)
    cost_out = np.zeros(n_days)
    n_trade_days = 0
    n_legs = 0
    contributed = 0.0

    for t in range(n_days):
        opening = value.sum()
        value = value * (1.0 + ret[t])
        gross = value.sum()

        inflow = 0.0
        if contrib_days[t]:
            inflow = monthly_contribution
            contributed += inflow
            if policy.contributions_to_underweight:
                # Steer the whole contribution at the single most underweight
                # asset. With a big enough pot this never fully corrects a
                # drift, which is precisely the finding the policy exists to
                # expose.
                shortfall = target * (gross + inflow) - value
                pick = int(np.argmax(shortfall))
                value[pick] += inflow
            else:
                # Neutral handling for every other policy: buy at current
                # weights, so the contribution itself carries no rebalancing
                # effect and cannot flatter the comparison.
                value += inflow * (value / gross)

        total = value.sum()
        weights_pre[t] = value / total

        if schedule[t] and policy.sells_allowed and policy.breached(weights_pre[t], target):
            desired = target * total
            delta = desired - value
            traded = np.abs(delta)
            legs = int((traded > 1e-9).sum())
            charge = float(traded @ spread) + legs * commission
            total_after = total - charge
            value = target * total_after
            turnover_out[t] = float(traded.sum()) / total
            cost_out[t] = charge
            n_trade_days += 1
            n_legs += legs

        value_out[t] = value.sum()
        weights_out[t] = value / value_out[t]
        # Strip the contribution out of the return so a pound paid in is never
        # counted as a pound earned.
        net_returns[t] = (value_out[t] - inflow) / opening - 1.0

    result = BacktestResult(
        policy=policy.name,
        dates=dates,
        value=value_out,
        weights=weights_out,
        weights_predrift=weights_pre,
        turnover=turnover_out,
        cost=cost_out,
        n_trade_days=n_trade_days,
        n_legs=n_legs,
        contributed=contributed,
        target=target,
        currency=currency,
    )
    result._net_returns = net_returns
    return result


def run_batch(
    base_returns: NDArray[np.float64],
    index: NDArray[np.int64],
    policy: Policy,
    target: NDArray[np.float64],
    cost: CostModel,
    dates: pd.DatetimeIndex,
) -> NDArray[np.float64]:
    """Step ``B`` bootstrap replicates through ``policy`` simultaneously.

    ``index`` is ``(B, T)`` of row positions into ``base_returns``; holding
    only the index rather than ``B`` copies of the return matrix keeps memory
    at tens of megabytes instead of hundreds.

    Returns terminal wealth per replicate. Contributions are not modelled here
    -- the bootstrap compares policies on a lump sum, and the cash-flow policy
    is excluded from it for that reason.
    """
    n_reps, n_days = index.shape
    n_assets = base_returns.shape[1]
    target = np.asarray(target, dtype=float)

    if policy.drawdown_trigger is not None:
        equity_paths = np.cumprod(1.0 + base_returns[index, 0], axis=1)
        schedule = policy.schedule_mask(dates, equity_paths)  # (B, T)
        per_rep_schedule = True
    else:
        schedule = policy.schedule_mask(dates)  # (T,)
        per_rep_schedule = False

    spread = np.asarray(cost.spread_vector(), dtype=float) / 10_000.0
    commission = cost.commission_flat

    value = np.tile(target * cost.initial_value, (n_reps, 1))

    for t in range(n_days):
        value *= 1.0 + base_returns[index[:, t]]
        total = value.sum(axis=1, keepdims=True)

        allowed = schedule[:, t] if per_rep_schedule else np.full(n_reps, schedule[t])
        if not allowed.any():
            continue
        weights = value / total
        act = allowed & policy.breached(weights, target) & policy.sells_allowed

        if not act.any():
            continue
        sub_total = total[act]
        desired = target * sub_total
        traded = np.abs(desired - value[act])
        legs = (traded > 1e-9).sum(axis=1)
        charge = traded @ spread + legs * commission
        value[act] = target * (sub_total - charge[:, None])

    return value.sum(axis=1)


def constant_mix(
    returns: pd.DataFrame, weights: NDArray[np.float64]
) -> pd.Series:
    """A frictionless daily-rebalanced portfolio at fixed ``weights``.

    This is the reference object for the return/risk decomposition: it isolates
    what a given *average allocation* earns, with no trading decisions and no
    costs, so that any residual can be attributed to the rebalancing act.
    """
    weights = np.asarray(weights, dtype=float)
    daily = returns.to_numpy(dtype=float) @ weights
    return pd.Series(daily, index=returns.index, name="constant_mix")


def annualise(total_return: float, n_days: int) -> float:
    years = n_days / TRADING_DAYS_PER_YEAR
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


__all__ = ["BacktestResult", "annualise", "constant_mix", "run", "run_batch"]
