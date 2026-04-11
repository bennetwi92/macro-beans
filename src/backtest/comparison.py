import pandas as pd
from loguru import logger

from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import compute_metrics
from src.strategy.base import Strategy


class StrategyComparison:
    """Runs all strategies and ranks by Sharpe ratio."""

    def __init__(self, engine: BacktestEngine, risk_free_rate: float = 0.04):
        self.engine = engine
        self.risk_free_rate = risk_free_rate
        self.results: list[BacktestResult] = []

    def run_all(self, strategies: list[Strategy],
                data: pd.DataFrame, prices: pd.Series) -> pd.DataFrame:
        """
        Run every strategy, compute metrics, return a ranked DataFrame.
        """
        self.results = []
        rows = []

        for strategy in strategies:
            try:
                signals = strategy.generate_signals(data)
                result = self.engine.run(
                    prices, signals,
                    strategy_name=strategy.name,
                    params=strategy.config.params,
                )

                # Count trades from position changes
                position = signals.clip(0, 1).round()
                n_trades = int(position.diff().abs().sum())

                metrics = compute_metrics(result.returns, self.risk_free_rate)
                metrics["num_trades"] = n_trades
                result.metrics = metrics
                self.results.append(result)

                rows.append({
                    "strategy": strategy.name,
                    "params": str(strategy.config.params),
                    **metrics,
                })
            except Exception as e:
                logger.warning(f"Strategy {strategy.name} failed: {e}")
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).sort_values("sharpe", ascending=False).reset_index(drop=True)
        logger.info(f"Ran {len(rows)} strategies. Top Sharpe: {df.iloc[0]['sharpe']:.3f} ({df.iloc[0]['strategy']})")
        return df

    def top_n(self, n: int = 5) -> list[BacktestResult]:
        """Return the top N results by Sharpe."""
        sorted_results = sorted(self.results, key=lambda r: r.metrics.get("sharpe", 0), reverse=True)
        return sorted_results[:n]
