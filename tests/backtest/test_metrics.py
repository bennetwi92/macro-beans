import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics import compute_metrics


class TestComputeMetrics:
    def test_positive_returns(self):
        """Constant positive returns should give positive Sharpe."""
        returns = pd.Series([0.001] * 252)
        metrics = compute_metrics(returns, risk_free_rate=0.0)
        assert metrics["sharpe"] > 0
        assert metrics["total_return"] > 0
        assert metrics["max_drawdown"] == 0  # No drawdown with constant positive returns

    def test_zero_returns(self):
        returns = pd.Series([0.0] * 252)
        metrics = compute_metrics(returns, risk_free_rate=0.0)
        assert metrics["sharpe"] == 0.0
        assert metrics["total_return"] == 0.0

    def test_empty_returns(self):
        metrics = compute_metrics(pd.Series(dtype=float))
        assert metrics["sharpe"] == 0.0

    def test_known_sharpe(self):
        """Daily return with known mean and std should produce expected Sharpe."""
        np.random.seed(42)
        n = 252 * 5
        daily_mean = 0.0005
        daily_std = 0.01
        returns = pd.Series(np.random.normal(daily_mean, daily_std, n))

        metrics = compute_metrics(returns, risk_free_rate=0.0)
        # Expected Sharpe ~ (0.0005 / 0.01) * sqrt(252) ~ 0.79
        assert 0.3 < metrics["sharpe"] < 1.5  # Wide range due to randomness

    def test_max_drawdown_negative(self):
        """A series with a drawdown should have negative max_drawdown."""
        returns = pd.Series([0.05, 0.05, -0.20, 0.01, 0.01])
        metrics = compute_metrics(returns)
        assert metrics["max_drawdown"] < 0

    def test_win_rate(self):
        returns = pd.Series([0.01, -0.01, 0.01, 0.01, -0.01])
        metrics = compute_metrics(returns, risk_free_rate=0.0)
        assert metrics["win_rate"] == 0.6

    def test_profit_factor(self):
        returns = pd.Series([0.02, -0.01, 0.02, -0.01])
        metrics = compute_metrics(returns, risk_free_rate=0.0)
        # Gains = 0.04, losses = 0.02, PF = 2.0
        assert metrics["profit_factor"] == 2.0

    def test_cagr_positive(self):
        returns = pd.Series([0.001] * 504)  # ~2 years of positive returns
        metrics = compute_metrics(returns)
        assert metrics["cagr"] > 0
