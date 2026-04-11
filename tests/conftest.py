import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_dates():
    """252 trading days of dates."""
    return pd.bdate_range("2023-01-02", periods=252, freq="B")


@pytest.fixture
def sample_ohlcv(sample_dates):
    """Synthetic OHLCV DataFrame with realistic price patterns."""
    np.random.seed(42)
    n = len(sample_dates)

    # Random walk for close prices starting at 25.0
    returns = np.random.normal(0.0003, 0.02, n)
    close = 25.0 * np.exp(np.cumsum(returns))

    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_ = low + (high - low) * np.random.uniform(0.2, 0.8, n)
    volume = np.random.randint(100_000, 1_000_000, n).astype(float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=sample_dates)


@pytest.fixture
def sample_related(sample_dates):
    """Dict of related asset DataFrames for cross-asset features."""
    np.random.seed(123)
    n = len(sample_dates)

    def make_series(start, vol=0.01):
        returns = np.random.normal(0.0002, vol, n)
        close = start * np.exp(np.cumsum(returns))
        return pd.DataFrame({"close": close}, index=sample_dates)

    return {
        "DXY": make_series(104.0, 0.005),
        "GOLD": make_series(1900.0, 0.01),
        "SPX": make_series(4500.0, 0.012),
        "VIX": make_series(18.0, 0.03),
        "CL": make_series(75.0, 0.02),
        "BZ": make_series(80.0, 0.02),
        "XLE": make_series(85.0, 0.015),
    }
