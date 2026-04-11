import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class BacktestResult:
    strategy_name: str
    params: dict
    signals: pd.Series
    returns: pd.Series
    equity_curve: pd.Series
    metrics: dict = field(default_factory=dict)


class BacktestEngine:
    """Vectorized backtesting engine for long/flat strategies."""

    def __init__(self, initial_capital: float = 100_000, cost_bps: float = 10.0):
        self.initial_capital = initial_capital
        self.cost_bps = cost_bps

    def run(self, prices: pd.Series, signals: pd.Series,
            strategy_name: str = "", params: dict = None) -> BacktestResult:
        """
        Run a vectorized backtest.

        prices: daily close prices
        signals: 0 (flat) or 1 (long), aligned with prices index
        """
        if params is None:
            params = {}

        # Align signals and prices to common index
        common = prices.index.intersection(signals.index)
        prices = prices.loc[common]
        signals = signals.loc[common]

        # Clamp signals to {0, 1}
        signals = signals.clip(0, 1).round().astype(float)

        # Daily asset returns
        daily_ret = prices.pct_change()

        # Position for each day is based on PREVIOUS day's signal (no look-ahead)
        position = signals.shift(1).fillna(0)

        # Transaction costs: applied only when position changes
        position_changes = position.diff().abs().fillna(0)
        costs = position_changes * (self.cost_bps / 10_000)

        # Strategy returns
        strat_ret = position * daily_ret - costs

        # Equity curve
        equity = (1 + strat_ret).cumprod() * self.initial_capital

        return BacktestResult(
            strategy_name=strategy_name,
            params=params,
            signals=signals,
            returns=strat_ret,
            equity_curve=equity,
        )
