import pytest
import pandas as pd
from datetime import datetime, timedelta
from src.aggregation.aggregator import aggregate_data
from loguru import logger
import logging # Import the standard logging module

@pytest.fixture
def sample_market_data():
    """
    Generates a sample intraday_5s DataFrame for testing aggregation.
    Spans 10 minutes (120 rows) with predictable OHLCV and VWAP values.
    """
    start_time = datetime(2025, 1, 1, 9, 30, 0)
    data = []
    for i in range(120):  # 10 minutes * 12 5-second bars/minute = 120 bars
        current_time = start_time + timedelta(seconds=i * 5)
        open_price = 100 + i * 0.1
        high_price = open_price + 0.5
        low_price = open_price - 0.5
        close_price = open_price + 0.1
        volume = 1000 + i * 10
        vwap = open_price + 0.05 # Simple predictable vwap

        data.append({
            'datetime': current_time,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume,
            'vwap': vwap
        })

    df = pd.DataFrame(data)
    df = df.set_index('datetime')
    df.index = pd.to_datetime(df.index) # Ensure DatetimeIndex

    return {'intraday_5s': df, 'daily': pd.DataFrame()}

def test_successful_aggregation(sample_market_data):
    """
    Verifies the standard, successful aggregation of 5s data into 1m and 5m bars.
    """
    aggregated = aggregate_data(sample_market_data)

    assert 'daily' in aggregated
    assert 'intraday_5s' in aggregated
    assert 'intraday_1m' in aggregated
    assert 'intraday_5m' in aggregated

    intraday_1m_df = aggregated['intraday_1m']
    intraday_5m_df = aggregated['intraday_5m']
    intraday_5s_df = sample_market_data['intraday_5s']

    # Assert lengths
    assert len(intraday_1m_df) == 10
    assert len(intraday_5m_df) == 2

    # --- Verify first 1-minute bar (09:30:00 - 09:30:55) ---
    # Corresponds to first 12 rows of 5s data (index 0 to 11)
    first_1m_bar = intraday_1m_df.iloc[0]
    expected_5s_slice_1m = intraday_5s_df.iloc[0:12]

    assert first_1m_bar['open'] == expected_5s_slice_1m['open'].iloc[0]
    assert first_1m_bar['high'] == expected_5s_slice_1m['high'].max()
    assert first_1m_bar['low'] == expected_5s_slice_1m['low'].min()
    assert first_1m_bar['close'] == expected_5s_slice_1m['close'].iloc[-1]
    assert first_1m_bar['volume'] == expected_5s_slice_1m['volume'].sum()
    assert first_1m_bar['vwap'] == expected_5s_slice_1m['vwap'].iloc[-1] # Changed to 'last'

    # --- Verify first 5-minute bar (09:30:00 - 09:34:55) ---
    # Corresponds to first 60 rows of 5s data (index 0 to 59)
    first_5m_bar = intraday_5m_df.iloc[0]
    expected_5s_slice_5m = intraday_5s_df.iloc[0:60]

    assert first_5m_bar['open'] == expected_5s_slice_5m['open'].iloc[0]
    assert first_5m_bar['high'] == expected_5s_slice_5m['high'].max()
    assert first_5m_bar['low'] == expected_5s_slice_5m['low'].min()
    assert first_5m_bar['close'] == expected_5s_slice_5m['close'].iloc[-1]
    assert first_5m_bar['volume'] == expected_5s_slice_5m['volume'].sum()
    assert first_5m_bar['vwap'] == expected_5s_slice_5m['vwap'].iloc[-1] # Changed to 'last'

def test_missing_intraday_key(caplog):
    """
    Ensures the function handles inputs where the 'intraday_5s' key is missing.
    """
    data = {'daily': pd.DataFrame([1, 2, 3])}
    with caplog.at_level(logging.WARNING): # Changed logger.WARNING to logging.WARNING
        aggregated = aggregate_data(data)
        assert "Missing or empty 'intraday_5s' DataFrame" in caplog.text
    assert aggregated == data
    assert len(aggregated) == 1

def test_empty_intraday_dataframe(caplog):
    """
    Ensures the function handles an empty 'intraday_5s' DataFrame.
    """
    data = {'intraday_5s': pd.DataFrame(), 'daily': pd.DataFrame([1, 2, 3])}
    with caplog.at_level(logging.WARNING): # Changed logger.WARNING to logging.WARNING
        aggregated = aggregate_data(data)
        assert "Missing or empty 'intraday_5s' DataFrame" in caplog.text
    assert aggregated == data
    assert len(aggregated) == 2

def test_partial_final_bar_aggregation(sample_market_data):
    """
    Verifies that data that doesn't fill a complete final bar is still aggregated correctly.
    Truncates the source DataFrame to 7.5 minutes of data (90 rows, ending at 09:37:25).
    """
    intraday_5s_df = sample_market_data['intraday_5s'].iloc[0:90] # 7.5 minutes of data
    sample_market_data['intraday_5s'] = intraday_5s_df

    aggregated = aggregate_data(sample_market_data)

    assert 'intraday_5m' in aggregated
    intraday_5m_df = aggregated['intraday_5m']

    # Should still have 2 5-minute bars: 09:30-09:34 and 09:35-09:39 (partial)
    assert len(intraday_5m_df) == 2

    # --- Verify second (partial) 5-minute bar (09:35:00 - 09:37:25) ---
    # Corresponds to 5s data from index 60 to 89 (30 rows)
    second_5m_bar = intraday_5m_df.iloc[1]
    expected_5s_slice_partial_5m = intraday_5s_df.iloc[60:90]

    assert second_5m_bar['open'] == expected_5s_slice_partial_5m['open'].iloc[0]
    assert second_5m_bar['high'] == expected_5s_slice_partial_5m['high'].max()
    assert second_5m_bar['low'] == expected_5s_slice_partial_5m['low'].min()
    assert second_5m_bar['close'] == expected_5s_slice_partial_5m['close'].iloc[-1]
    assert second_5m_bar['volume'] == expected_5s_slice_partial_5m['volume'].sum()
    assert second_5m_bar['vwap'] == expected_5s_slice_partial_5m['vwap'].iloc[-1] # Changed to 'last'
