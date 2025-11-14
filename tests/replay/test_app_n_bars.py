import pytest
import streamlit as st
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime
from src.replay.app import create_candlestick_chart # Import the function to test its slicing logic
import sys

# Mock the entire streamlit module to prevent it from running during tests
# and to control its behavior.
@pytest.fixture(autouse=True)
def mock_streamlit_and_session_state():
    with patch('streamlit.session_state', new_callable=MagicMock) as mock_session_state:
        # Initialize n_bars and aggregated_data directly on the mock_session_state object
        mock_session_state.n_bars = 45
        mock_session_state.aggregated_data = None

        with patch('streamlit.set_page_config'), \
             patch('streamlit.title'), \
             patch('streamlit.header'), \
             patch('streamlit.subheader'), \
             patch('streamlit.columns', return_value=[MagicMock(), MagicMock(), MagicMock()]), \
             patch('streamlit.text_input', return_value="SPY"), \
             patch('streamlit.date_input', return_value=datetime(2025, 11, 12).date()), \
             patch('streamlit.button', return_value=False) as mock_button, \
             patch('streamlit.write'), \
             patch('streamlit.error'), \
             patch('streamlit.warning'), \
             patch('streamlit.info'), \
             patch('streamlit.spinner'), \
             patch('streamlit.plotly_chart'), \
             patch('streamlit.rerun') as mock_rerun, \
             patch('streamlit.number_input', return_value=45) as mock_number_input:
            yield mock_session_state, mock_number_input, mock_button, mock_rerun

# Test 1: Default value of n_bars in session state
def test_n_bars_default_value(mock_streamlit_and_session_state):
    mock_session_state, _, _, _ = mock_streamlit_and_session_state
    if 'src.replay.app' in sys.modules:
        del sys.modules['src.replay.app']
    import src.replay.app
    assert mock_session_state.n_bars == 45

# Test 2: n_bars updates when number_input changes and Apply button is clicked
def test_n_bars_update_on_apply_button(mock_streamlit_and_session_state):
    mock_session_state, mock_number_input, mock_button, mock_rerun = mock_streamlit_and_session_state
    
    # Set initial n_bars in session state
    mock_session_state.n_bars = 45
    
    # Simulate user changing number_input to 100
    mock_number_input.return_value = 100
    
    # Simulate Apply button click (assuming it's the second button)
    mock_button.side_effect = [False, True] # First button (Load Data) is False, second (Apply) is True
    
    if 'src.replay.app' in sys.modules:
        del sys.modules['src.replay.app']
    import src.replay.app
    
    assert mock_session_state.n_bars == 100
    mock_rerun.assert_called_once() # Ensure rerun was called

# Test 3: Chart slicing logic in create_candlestick_chart
def test_create_candlestick_chart_slicing():
    # Create a dummy DataFrame
    data = {
        'open': [i for i in range(1, 101)],
        'high': [i + 1 for i in range(1, 101)],
        'low': [i - 1 for i in range(1, 101)],
        'close': [i + 0.5 for i in range(1, 101)],
        'volume': [i * 10 for i in range(1, 101)],
        'vwap': [i + 0.2 for i in range(1, 101)]
    }
    index = pd.to_datetime(pd.date_range(start='2023-01-01', periods=100, freq='min'))
    df = pd.DataFrame(data, index=index)

    # Test with n_bars < len(df)
    n_bars_small = 10
    fig_small = create_candlestick_chart(df, "Test Chart", n_bars_small)
    # Check if the x-axis data (index) of the candlestick trace has the correct length
    assert len(fig_small.data[0].x) == n_bars_small
    assert len(fig_small.data[1].x) == n_bars_small # Volume trace

    # Test with n_bars > len(df)
    n_bars_large = 150
    fig_large = create_candlestick_chart(df, "Test Chart", n_bars_large)
    assert len(fig_large.data[0].x) == len(df)
    assert len(fig_large.data[1].x) == len(df)

    # Test with n_bars = len(df)
    n_bars_equal = 100
    fig_equal = create_candlestick_chart(df, "Test Chart", n_bars_equal)
    assert len(fig_equal.data[0].x) == len(df)
    assert len(fig_equal.data[1].x) == len(df)
