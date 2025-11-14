# tests/market_data/test_collector.py

import pytest
import pandas as pd
import pytz
from datetime import datetime, date
from freezegun import freeze_time

# Assuming the project structure allows this import.
# This might need adjustment based on the project's Python path setup.
from src.market_data.collector import fetch_market_data
from src.broker.connection import BrokerError

# --- Test Fixtures ---

@pytest.fixture
def mock_get_historical_data(mocker):
    """Mocks the get_historical_data function."""
    return mocker.patch('src.market_data.collector.get_historical_data')

@pytest.fixture
def sample_daily_df():
    """A sample daily DataFrame returned by the broker."""
    dates = pd.to_datetime(pd.date_range(start="2025-09-29", end="2025-11-12", freq="B"))
    data = {
        "open": 100, "high": 102, "low": 99, "close": 101,
        "volume": 100000, "vwap": 100.5
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "date"
    return df.tz_localize('UTC')

@pytest.fixture
def sample_intraday_df():
    """A sample intraday DataFrame returned by the broker."""
    trade_date = date(2025, 11, 12)
    start_time = datetime.combine(trade_date, datetime.min.time()).replace(hour=9)
    end_time = start_time.replace(hour=12, minute=59, second=55)
    
    dates = pd.to_datetime(pd.date_range(start=start_time, end=end_time, freq="5s"))
    data = {
        "open": 101.1, "high": 101.2, "low": 101.0, "close": 101.15,
        "volume": 100, "vwap": 101.12
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "date"
    return df.tz_localize('Europe/London').tz_convert('UTC')

# --- Test Cases ---

@freeze_time("2025-11-13")
def test_fetch_market_data_success(mock_get_historical_data, sample_daily_df, sample_intraday_df):
    """
    Tests the success path of fetch_market_data.
    Verifies that the broker function is called with correct parameters and data is returned.
    """
    # Configure the mock to return different data based on bar_size
    def side_effect(*args, **kwargs):
        if kwargs.get("bar_size") == "DAILY":
            return sample_daily_df
        elif kwargs.get("bar_size") == "5 secs":
            return sample_intraday_df
        return pd.DataFrame()

    mock_get_historical_data.side_effect = side_effect

    # Call the function under test
    result = fetch_market_data(symbol="SPY", trade_date="2025-11-12")

    # --- Assertions ---
    assert mock_get_historical_data.call_count == 2
    assert "daily" in result
    assert "intraday_5s" in result
    pd.testing.assert_frame_equal(result["daily"], sample_daily_df)
    pd.testing.assert_frame_equal(result["intraday_5s"], sample_intraday_df)

    # Check arguments for the daily call
    daily_call_args = mock_get_historical_data.call_args_list[0].kwargs
    assert daily_call_args["symbol"] == "SPY"
    assert daily_call_args["bar_size"] == "DAILY"
    assert daily_call_args["start_date"] == pytz.utc.localize(datetime(2025, 9, 28, 0, 0))
    assert daily_call_args["end_date"] == pytz.utc.localize(datetime(2025, 11, 12, 23, 59, 59, 999999))

    # Check arguments for the intraday call
    intraday_call_args = mock_get_historical_data.call_args_list[1].kwargs
    assert intraday_call_args["symbol"] == "SPY"
    assert intraday_call_args["bar_size"] == "5 secs"
    assert intraday_call_args["start_date"] == pytz.timezone("Europe/London").localize(datetime(2025, 11, 12, 9, 0))
    assert intraday_call_args["end_date"] == pytz.timezone("Europe/London").localize(datetime(2025, 11, 12, 13, 0))


def test_fetch_market_data_broker_error(mock_get_historical_data):
    """
    Tests that fetch_market_data returns empty DataFrames when the broker raises an error.
    """
    # Configure the mock to raise a BrokerError
    mock_get_historical_data.side_effect = BrokerError("Connection failed")

    # Call the function under test
    result = fetch_market_data(symbol="FAIL", trade_date="2025-11-12")

    # --- Assertions ---
    assert "daily" in result
    assert "intraday_5s" in result
    assert result["daily"].empty
    assert result["intraday_5s"].empty
    # Ensure the function was called at least once before failing
    mock_get_historical_data.assert_called_once()

def test_fetch_market_data_empty_response(mock_get_historical_data):
    """
    Tests that fetch_market_data handles empty DataFrame responses from the broker.
    """
    # Configure the mock to return empty DataFrames
    mock_get_historical_data.return_value = pd.DataFrame()

    # Call the function under test
    result = fetch_market_data(symbol="EMPTY", trade_date="2025-11-12")

    # --- Assertions ---
    assert "daily" in result
    assert "intraday_5s" in result
    assert result["daily"].empty
    assert result["intraday_5s"].empty
    assert mock_get_historical_data.call_count == 2
