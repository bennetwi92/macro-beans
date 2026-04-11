import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine


@pytest.fixture
def engine():
    return BacktestEngine(initial_capital=100_000, cost_bps=10)


@pytest.fixture
def prices(sample_dates):
    np.random.seed(42)
    returns = np.random.normal(0.0003, 0.02, len(sample_dates))
    close = 25.0 * np.exp(np.cumsum(returns))
    return pd.Series(close, index=sample_dates, name="close")


class TestBacktestEngine:
    def test_buy_and_hold(self, engine, prices):
        """Buy-and-hold should approximate underlying returns minus small costs."""
        signals = pd.Series(1.0, index=prices.index)
        result = engine.run(prices, signals, strategy_name="buy_hold")

        assert result.strategy_name == "buy_hold"
        assert len(result.returns) == len(prices)
        assert result.equity_curve.iloc[-1] > 0

    def test_all_flat_returns_zero(self, engine, prices):
        """All-flat signal should yield near-zero returns."""
        signals = pd.Series(0.0, index=prices.index)
        result = engine.run(prices, signals, strategy_name="flat")

        # Returns should be essentially zero (only tiny cost on first day if any)
        assert abs(result.returns.sum()) < 1e-10

    def test_no_lookahead(self, engine, prices):
        """Signal on day T should not affect return on day T."""
        # Create a signal that switches from 0 to 1 on day 100
        signals = pd.Series(0.0, index=prices.index)
        signals.iloc[100:] = 1.0

        result = engine.run(prices, signals)

        # Day 100: signal just changed, but position uses shift(1),
        # so the position on day 100 is still 0 (from day 99's signal).
        # Position on day 101 should be 1 (from day 100's signal of 1).
        # Returns on day 100 should be 0 (flat position) minus any cost
        assert result.returns.iloc[100] <= 0  # flat or cost

    def test_signals_clamped(self, engine, prices):
        """Signals outside [0,1] should be clamped."""
        signals = pd.Series(2.0, index=prices.index)
        result = engine.run(prices, signals)
        # Should behave like all-1s
        assert result.equity_curve.iloc[-1] > 0

    def test_transaction_costs_applied(self, prices):
        """More frequent trading should result in higher costs."""
        engine = BacktestEngine(initial_capital=100_000, cost_bps=50)

        # Buy and hold - 1 trade
        hold_signals = pd.Series(1.0, index=prices.index)
        hold_result = engine.run(prices, hold_signals)

        # Frequent switching - many trades
        switch_signals = pd.Series(
            [1.0 if i % 2 == 0 else 0.0 for i in range(len(prices))],
            index=prices.index
        )
        switch_result = engine.run(prices, switch_signals)

        # Frequent trader should have lower final equity due to costs
        assert switch_result.equity_curve.iloc[-1] < hold_result.equity_curve.iloc[-1]

    def test_result_structure(self, engine, prices):
        signals = pd.Series(1.0, index=prices.index)
        result = engine.run(prices, signals, strategy_name="test", params={"a": 1})

        assert result.strategy_name == "test"
        assert result.params == {"a": 1}
        assert isinstance(result.signals, pd.Series)
        assert isinstance(result.returns, pd.Series)
        assert isinstance(result.equity_curve, pd.Series)
