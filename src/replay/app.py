import streamlit as st
import pandas as pd
from datetime import date
from src.logging import get_logger
from src.market_data.collector import fetch_market_data
from src.aggregation.aggregator import aggregate_data
from src.broker.connection import ContractNotFoundError, ConnectionTimeoutError, DataRequestError
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import time

# Initialize logger
log = get_logger("replay_app")

# Set Streamlit page configuration
st.set_page_config(
    page_title="Trading Replay Tool",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Historical Data Replay")

# Initialize session state for aggregated_data if not already present
if 'aggregated_data' not in st.session_state:
    st.session_state.aggregated_data = None

# Initialize n_bars in session state
if 'n_bars' not in st.session_state:
    st.session_state.n_bars = 45

# Initialize playback session state variables
if 'playback_active' not in st.session_state:
    st.session_state.playback_active = False
if 'current_playback_index' not in st.session_state:
    st.session_state.current_playback_index = 0
if 'playback_speed' not in st.session_state:
    st.session_state.playback_speed = 1 # 1x, 5x, 15x
if 'full_intraday_data' not in st.session_state:
    st.session_state.full_intraday_data = pd.DataFrame() # Store DataFrame directly
if 'last_update_time' not in st.session_state:
    st.session_state.last_update_time = time.time() # Timestamp for controlling playback speed

# Helper function to create candlestick charts
def create_candlestick_chart(df: pd.DataFrame, title: str, n_bars: int, show_vwap: bool = False) -> go.Figure:
    """
    Generates a Plotly candlestick chart with optional VWAP and Volume.

    Args:
        df (pd.DataFrame): DataFrame with OHLCV and optionally 'vwap' columns.
        title (str): Title of the chart.
        n_bars (int): The number of most recent bars to display.
        show_vwap (bool): Whether to display the VWAP line.

    Returns:
        go.Figure: Plotly Figure object.
    """
    # Slice the DataFrame to show only the last n_bars
    df_display = df.tail(min(n_bars, len(df)))

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,  # Reduced spacing
                        row_heights=[0.7, 0.3])

    # Candlestick trace
    fig.add_trace(go.Candlestick(x=df_display.index,
                                 open=df_display['open'],
                                 high=df_display['high'],
                                 low=df_display['low'],
                                 close=df_display['close'],
                                 name='Candlesticks',
                                 increasing_line_color='green',
                                 decreasing_line_color='red'),
                  row=1, col=1)

    # Volume trace - conditional coloring per bar
    colors = ['green' if close > open_ else 'red' for close, open_ in zip(df_display['close'], df_display['open'])]
    fig.add_trace(go.Bar(x=df_display.index, y=df_display['volume'], name='Volume',
                         marker_color=colors),
                  row=2, col=1)

    # VWAP trace
    if show_vwap and 'vwap' in df_display.columns:
        fig.add_trace(go.Scatter(x=df_display.index, y=df_display['vwap'], name='VWAP',
                                 line=dict(color='lightblue', width=2)),
                      row=1, col=1)

    fig.update_layout(title_text=title,
                      xaxis_rangeslider_visible=False,
                      xaxis_tickformat='%H:%M:%S' if df_display.index.hour.any() else '%Y-%m-%d',
                      height=400,
                      margin=dict(l=20, r=20, t=40, b=20), # Adjust margins for better fit
                      showlegend=False) # Remove legend

    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    return fig

@st.cache_data(ttl=3600) # Cache data for 1 hour
def cached_fetch_market_data(symbol: str, trade_date: date):
    log.info(f"Fetching market data for {symbol} on {trade_date} (cached)...")
    return fetch_market_data(symbol=symbol, trade_date=trade_date)

@st.cache_data(ttl=3600) # Cache data for 1 hour
def cached_aggregate_data(market_data: dict[str, pd.DataFrame]):
    log.info("Aggregating data (cached)...")
    return aggregate_data(market_data)

def live_aggregate_intraday_data(df_5s: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Aggregates 5-second intraday data into 1-minute and 5-minute bars.

    Args:
        df_5s (pd.DataFrame): DataFrame with 5-second OHLCV and vwap data.

    Returns:
        dict[str, pd.DataFrame]: Dictionary containing 'intraday_1m' and 'intraday_5m' DataFrames.
    """
    if df_5s.empty:
        return {'intraday_1m': pd.DataFrame(), 'intraday_5m': pd.DataFrame()}

    # Define aggregation rules
    aggregation_rules = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'vwap': 'last'
    }

    # Aggregate to 1-minute bars
    intraday_1m = df_5s.resample('1min').apply(aggregation_rules).dropna()

    # Aggregate to 5-minute bars
    intraday_5m = df_5s.resample('5min').apply(aggregation_rules).dropna()

    return {'intraday_1m': intraday_1m, 'intraday_5m': intraday_5m}

def on_slider_change():
    # This callback is only triggered by manual slider interaction
    st.session_state.current_playback_index = st.session_state.playback_slider
    st.session_state.playback_active = False # Pause playback when manually jumping
    log.info(f"Jumped to index {st.session_state.playback_slider}.")

# Input fields
with st.sidebar:
    st.header("Data Selection")
    symbol = st.text_input("Enter Stock Symbol", value="SPY")
    trade_date = st.date_input("Select Trading Date", value=date(2025, 11, 12))
    load_button = st.button("Load Data")

# Sidebar for n_bars control
with st.sidebar:
    st.header("Chart Display Settings")
    current_n_bars = st.session_state.n_bars
    
    new_n_bars = st.number_input(
        "Number of Bars to Display",
        min_value=10,
        max_value=500,
        value=current_n_bars,
        step=1
    )

    if st.button("Apply"):
        if new_n_bars != current_n_bars:
            st.session_state.n_bars = new_n_bars
            st.rerun() # Rerun to apply the new n_bars value

    # Playback controls
    if not st.session_state.full_intraday_data.empty:
        st.subheader("Intraday Playback Controls")
        
        if st.button("Play", disabled=st.session_state.playback_active):
            st.session_state.playback_active = True
            log.info("Playback started.")
            st.rerun()
        if st.button("Pause", disabled=not st.session_state.playback_active):
            st.session_state.playback_active = False
            log.info("Playback paused.")
            st.rerun()
        if st.button("Reset"):
            st.session_state.playback_active = False
            st.session_state.current_playback_index = 0
            log.info("Playback reset.")
            st.rerun()

        speed_options = {1: "1x", 5: "5x", 15: "15x"}
        selected_speed_key = st.radio(
            "Speed",
            options=list(speed_options.keys()),
            format_func=lambda x: speed_options[x],
            index=list(speed_options.keys()).index(st.session_state.playback_speed),
            horizontal=False, # Changed to False for vertical stacking
            key="playback_speed_radio"
        )
        if selected_speed_key != st.session_state.playback_speed:
            st.session_state.playback_speed = selected_speed_key
            log.info(f"Playback speed set to {selected_speed_key}x.")
            st.rerun()

if load_button:
    if not symbol:
        st.error("Please enter a stock symbol.")
        log.warning("Load Data clicked with empty symbol.")
        st.session_state.aggregated_data = None
    elif not trade_date:
        st.error("Please select a trading date.")
        log.warning("Load Data clicked with empty date.")
        st.session_state.aggregated_data = None
    else:
        with st.spinner(f"Fetching and aggregating data for {symbol} on {trade_date}..."):
            log.info(f"Load Data button clicked for Symbol: {symbol}, Date: {trade_date}")
            try:
                market_data = cached_fetch_market_data(symbol=symbol, trade_date=trade_date)

                if market_data["intraday_5s"].empty:
                    st.warning(f"No intraday 5s data found for {symbol} on {trade_date}. "
                               f"Please try another date or symbol with available intraday data.")
                    log.warning(f"No intraday 5s data for {symbol} on {trade_date}.")
                    st.session_state.aggregated_data = None
                    st.session_state.full_intraday_data = pd.DataFrame() # Clear full data
                else:
                    log.info("Market data fetched successfully. Aggregating data...")
                    aggregated_data = cached_aggregate_data(market_data)
                    st.session_state.aggregated_data = aggregated_data
                    st.session_state.full_intraday_data = aggregated_data['intraday_5s'] # Store full 5s data
                    st.session_state.current_playback_index = 0 # Reset index on new data
                    st.session_state.playback_active = False # Stop playback on new data
                    st.success("Data loaded and aggregated successfully!")

            except (ContractNotFoundError, ConnectionTimeoutError, DataRequestError) as e:
                st.error(f"Error fetching data: {e}. "
                         f"Please ensure TWS/IB Gateway is running and configured correctly, "
                         f"and that the symbol/date are valid.")
                log.error(f"Error fetching data for {symbol} on {trade_date}: {e}")
                st.session_state.aggregated_data = None
                st.session_state.full_intraday_data = pd.DataFrame() # Clear full data
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}. Please check the logs for more details.")
                log.exception(f"Unexpected error for {symbol} on {trade_date}.")
                st.session_state.aggregated_data = None
                st.session_state.full_intraday_data = pd.DataFrame() # Clear full data



# Display charts if data is available in session state
if st.session_state.full_intraday_data is not None and not st.session_state.full_intraday_data.empty:
    full_intraday_5s_data = st.session_state.full_intraday_data
    n_bars_to_display = st.session_state.n_bars

    st.subheader("Aggregated Market Data Charts")

    # Determine the data slice for current playback
    current_5s_slice = full_intraday_5s_data.iloc[:st.session_state.current_playback_index + 1]

    # Live aggregate 1m and 5m data from the current 5s slice
    live_aggregated_data = live_aggregate_intraday_data(current_5s_slice)

    col1, col2 = st.columns(2)

    with col1:
        if not current_5s_slice.empty:
            st.plotly_chart(create_candlestick_chart(current_5s_slice, "Intraday 5-Second", n_bars_to_display, show_vwap=True), use_container_width=True)
        else:
            st.info("No 5-second intraday data to display.")

        if 'intraday_5m' in live_aggregated_data and not live_aggregated_data['intraday_5m'].empty:
            st.plotly_chart(create_candlestick_chart(live_aggregated_data['intraday_5m'], "Intraday 5-Minute", n_bars_to_display, show_vwap=True), use_container_width=True)
        else:
            st.info("No 5-minute intraday data to display.")

    with col2:
        if 'intraday_1m' in live_aggregated_data and not live_aggregated_data['intraday_1m'].empty:
            st.plotly_chart(create_candlestick_chart(live_aggregated_data['intraday_1m'], "Intraday 1-Minute", n_bars_to_display, show_vwap=True), use_container_width=True)
        else:
            st.info("No 1-minute intraday data to display.")

        # Daily data remains static, fetched once
        if st.session_state.aggregated_data is not None and 'daily' in st.session_state.aggregated_data and not st.session_state.aggregated_data['daily'].empty:
            st.plotly_chart(create_candlestick_chart(st.session_state.aggregated_data['daily'], "Daily Data", n_bars_to_display, show_vwap=False), use_container_width=True)
        else:
            st.info("No daily data to display.")

    # Playback loop
    if st.session_state.playback_active:
        log.debug(f"Playback active. Current index: {st.session_state.current_playback_index}")
        
        # Calculate delay per single 5s bar based on desired speed
        # 1x speed: 1 bar (5s) every 5 seconds -> delay_per_bar = 5 seconds
        # 5x speed: 1 bar (5s) every 1 second -> delay_per_bar = 1 second
        delay_per_bar = 5.0 / st.session_state.playback_speed
        
        current_time = time.time()
        time_elapsed = current_time - st.session_state.last_update_time

        if time_elapsed >= delay_per_bar: # Check if enough time has passed for ONE bar
            # Advance only one bar at a time
            next_index = st.session_state.current_playback_index + 1 
            if next_index >= len(full_intraday_5s_data):
                st.session_state.current_playback_index = len(full_intraday_5s_data) - 1
                st.session_state.playback_active = False
                log.info("Playback finished.")
            else:
                st.session_state.current_playback_index = next_index
                st.session_state.last_update_time = current_time # Update last update time
                log.debug(f"Calling st.rerun() for next frame. Next index: {st.session_state.current_playback_index}")
        
        # Always rerun if playback is active to keep checking the time_elapsed condition
        st.rerun() # Force rerun to update chart

    # Slider for jumping to time
    max_index = len(st.session_state.full_intraday_data) - 1
    if max_index >= 0:
        def on_slider_change():
            # This callback is only triggered by manual slider interaction
            st.session_state.current_playback_index = st.session_state.playback_slider
            st.session_state.playback_active = False # Pause playback when manually jumping
            log.info(f"Jumped to index {st.session_state.playback_slider}.")

        st.slider(
            "Jump to Time",
            min_value=0,
            max_value=max_index,
            value=st.session_state.current_playback_index,
            step=1,
            key="playback_slider",
            disabled=st.session_state.playback_active, # Disable slider during active playback
            on_change=on_slider_change
        )

        # Display current timestamp
        current_timestamp = st.session_state.full_intraday_data.index[st.session_state.current_playback_index].strftime('%Y-%m-%d %H:%M:%S')
        st.write(f"**Current Playback Time:** {current_timestamp}")
    else:
        st.info("No intraday data available for playback controls.")
elif st.session_state.aggregated_data is not None: # Only show other charts if data is loaded but playback is not active
    aggregated_data = st.session_state.aggregated_data
    n_bars_to_display = st.session_state.n_bars

    st.subheader("Aggregated Market Data Charts")

    col1, col2 = st.columns(2)

    with col1:
        if 'intraday_5s' in aggregated_data and not aggregated_data['intraday_5s'].empty:
            st.plotly_chart(create_candlestick_chart(aggregated_data['intraday_5s'], "Intraday 5-Second", n_bars_to_display, show_vwap=True), use_container_width=True)
        else:
            st.info("No 5-second intraday data to display.")

        if 'intraday_5m' in aggregated_data and not aggregated_data['intraday_5m'].empty:
            st.plotly_chart(create_candlestick_chart(aggregated_data['intraday_5m'], "Intraday 5-Minute", n_bars_to_display, show_vwap=True), use_container_width=True)
        else:
            st.info("No 5-minute intraday data to display.")

    with col2:
        if 'intraday_1m' in aggregated_data and not aggregated_data['intraday_1m'].empty:
            st.plotly_chart(create_candlestick_chart(aggregated_data['intraday_1m'], "Intraday 1-Minute", n_bars_to_display, show_vwap=True), use_container_width=True)
        else:
            st.info("No 1-minute intraday data to display.")

        if 'daily' in aggregated_data and not aggregated_data['daily'].empty:
            st.plotly_chart(create_candlestick_chart(aggregated_data['daily'], "Daily Data", n_bars_to_display, show_vwap=False), use_container_width=True)
        else:
            st.info("No daily data to display.")

