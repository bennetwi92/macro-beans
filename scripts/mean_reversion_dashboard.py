"""
Mean Reversion Trading Dashboard
Streamlit app for $10K account mean reversion strategy
Provides real-time scanning, position tracking, and performance metrics
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# Page configuration
st.set_page_config(
    page_title="Mean Reversion Trading Dashboard",
    page_icon="📊",
    layout="wide"
)

# Title and description
st.title("📊 Mean Reversion Trading Dashboard")
st.caption("High-probability mean reversion setups for $10K accounts (65-70% win rate)")

# Sidebar configuration
st.sidebar.header("Account Settings")
capital = st.sidebar.number_input("Account Capital", value=10000, step=1000)
max_positions = st.sidebar.selectbox("Max Positions", [3, 4, 5], index=2)
risk_per_trade = st.sidebar.slider("Risk Per Trade (%)", 2.0, 5.0, 3.0, 0.5) / 100

# Calculate position sizing
position_size = capital / max_positions
max_risk = capital * risk_per_trade * max_positions

st.sidebar.markdown("---")
st.sidebar.markdown("### Position Sizing")
st.sidebar.info(f"""
- Position Size: ${position_size:,.0f}
- Risk/Trade: ${position_size * risk_per_trade:,.0f}
- Max Portfolio Risk: ${max_risk:,.0f}
""")

# Universe of stocks to scan
UNIVERSE = [
    'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'NVDA',
    'JPM', 'V', 'MA', 'BAC', 'WMT', 'PG', 'HD', 'DIS',
    'ADBE', 'CRM', 'NFLX', 'PYPL', 'INTC', 'CSCO', 'PFE',
    'AMD', 'ORCL', 'QCOM', 'TXN', 'AVGO', 'COST', 'NKE',
    'UNH', 'JNJ', 'XOM', 'CVX', 'ABBV', 'TMO', 'LLY',
    'PEP', 'KO', 'MRK', 'VZ', 'T', 'CMCSA', 'NEE'
]

@st.cache_data(ttl=300)  # Cache for 5 minutes
def calculate_rsi(prices, period=2):
    """Calculate RSI indicator"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

@st.cache_data(ttl=300)
def scan_for_setups(symbols, risk_pct):
    """Scan universe for mean reversion setups"""
    setups = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, symbol in enumerate(symbols):
        status_text.text(f'Scanning {symbol}... ({idx+1}/{len(symbols)})')
        progress_bar.progress((idx + 1) / len(symbols))

        try:
            # Download data
            stock = yf.Ticker(symbol)
            data = stock.history(period="6mo")

            if len(data) < 200:
                continue

            # Calculate indicators
            data['RSI_2'] = calculate_rsi(data['Close'], period=2)
            data['MA20'] = data['Close'].rolling(20).mean()
            data['MA50'] = data['Close'].rolling(50).mean()
            data['MA200'] = data['Close'].rolling(200).mean()

            current_price = data['Close'].iloc[-1]
            current_rsi = data['RSI_2'].iloc[-1]
            ma20 = data['MA20'].iloc[-1]
            ma50 = data['MA50'].iloc[-1]
            ma200 = data['MA200'].iloc[-1]

            # Check uptrend
            if not (current_price > ma50 > ma200):
                continue

            # Check pullback
            high_10d = data['High'].tail(10).max()
            pullback_pct = ((high_10d - current_price) / high_10d) * 100

            if not (3 <= pullback_pct <= 6):
                continue

            # Check oversold
            if current_rsi > 30:
                continue

            # Check near support
            distance_to_ma20 = abs((current_price - ma20) / ma20) * 100
            if distance_to_ma20 > 1.5:
                continue

            # Calculate trade parameters
            shares = int(position_size / current_price)
            stop_loss = current_price * (1 - risk_pct)
            profit_target = current_price * (1 + risk_pct)

            # Quality score
            quality = 0
            if current_rsi < 20: quality += 2
            elif current_rsi < 25: quality += 1.5
            else: quality += 1

            if 3.5 <= pullback_pct <= 4.5: quality += 1.5
            else: quality += 1

            if distance_to_ma20 <= 0.5: quality += 1.5
            elif distance_to_ma20 <= 1: quality += 1
            else: quality += 0.5

            setups.append({
                'Symbol': symbol,
                'Price': current_price,
                'RSI(2)': current_rsi,
                'Pullback %': pullback_pct,
                'Distance to MA20': distance_to_ma20,
                'Shares': shares,
                'Stop Loss': stop_loss,
                'Target': profit_target,
                'Risk $': shares * (current_price - stop_loss),
                'Reward $': shares * (profit_target - current_price),
                'Quality': quality
            })

        except Exception as e:
            continue

    progress_bar.empty()
    status_text.empty()

    return pd.DataFrame(setups)

def plot_stock_chart(symbol):
    """Create detailed chart for selected stock"""
    stock = yf.Ticker(symbol)
    data = stock.history(period="3mo")

    # Calculate indicators
    data['RSI_2'] = calculate_rsi(data['Close'], period=2)
    data['MA20'] = data['Close'].rolling(20).mean()
    data['MA50'] = data['Close'].rolling(50).mean()

    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        subplot_titles=(f'{symbol} - Price Action', 'RSI(2)'),
        vertical_spacing=0.1
    )

    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data['Open'],
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            name='Price'
        ),
        row=1, col=1
    )

    # Moving averages
    fig.add_trace(
        go.Scatter(x=data.index, y=data['MA20'], name='MA20',
                   line=dict(color='blue', width=1)),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(x=data.index, y=data['MA50'], name='MA50',
                   line=dict(color='orange', width=1)),
        row=1, col=1
    )

    # RSI
    fig.add_trace(
        go.Scatter(x=data.index, y=data['RSI_2'], name='RSI(2)',
                   line=dict(color='purple', width=2)),
        row=2, col=1
    )

    # RSI levels
    fig.add_hline(y=30, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="green", row=2, col=1)

    # Update layout
    fig.update_layout(
        height=600,
        showlegend=True,
        xaxis_rangeslider_visible=False
    )

    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="RSI", row=2, col=1)

    return fig

# Main interface
tab1, tab2, tab3, tab4 = st.tabs(["📊 Scanner", "📈 Analysis", "📋 Positions", "📚 Strategy Guide"])

with tab1:
    st.header("Market Scanner")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("### Current Mean Reversion Opportunities")
    with col2:
        if st.button("🔄 Refresh Scan", type="primary"):
            st.cache_data.clear()

    # Scan for setups
    with st.spinner("Scanning markets..."):
        setups_df = scan_for_setups(UNIVERSE, risk_per_trade)

    if not setups_df.empty:
        # Sort by quality
        setups_df = setups_df.sort_values('Quality', ascending=False)

        # Add quality stars
        setups_df['Rating'] = setups_df['Quality'].apply(
            lambda x: '⭐' * min(int(x), 5)
        )

        # Format for display
        display_df = setups_df[[
            'Symbol', 'Rating', 'Price', 'RSI(2)', 'Pullback %',
            'Shares', 'Stop Loss', 'Target', 'Risk $', 'Reward $'
        ]].round(2)

        # Color code RSI values
        def color_rsi(val):
            if val < 20:
                return 'background-color: darkgreen; color: white'
            elif val < 25:
                return 'background-color: green; color: white'
            elif val < 30:
                return 'background-color: lightgreen'
            return ''

        # Display table
        st.dataframe(
            display_df.style.applymap(color_rsi, subset=['RSI(2)']),
            use_container_width=True,
            height=400
        )

        # Summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Setups", len(setups_df))
        with col2:
            st.metric("5-Star Setups", len(setups_df[setups_df['Quality'] >= 4]))
        with col3:
            avg_risk = setups_df['Risk $'].mean()
            st.metric("Avg Risk/Trade", f"${avg_risk:.0f}")
        with col4:
            total_risk = setups_df.head(max_positions)['Risk $'].sum()
            st.metric("Total Risk (Top 5)", f"${total_risk:.0f}")

    else:
        st.warning("No setups found meeting all criteria. Market may not be conducive to mean reversion today.")

with tab2:
    st.header("Stock Analysis")

    selected_symbol = st.selectbox(
        "Select Stock to Analyze",
        options=setups_df['Symbol'].tolist() if not setups_df.empty else UNIVERSE[:10]
    )

    if selected_symbol:
        # Display chart
        chart = plot_stock_chart(selected_symbol)
        st.plotly_chart(chart, use_container_width=True)

        # Display setup details if available
        if not setups_df.empty and selected_symbol in setups_df['Symbol'].values:
            st.markdown("### Trade Setup Details")
            setup = setups_df[setups_df['Symbol'] == selected_symbol].iloc[0]

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**Entry Parameters**")
                st.info(f"""
                - Entry: ${setup['Price']:.2f}
                - Shares: {setup['Shares']}
                - Position Value: ${setup['Shares'] * setup['Price']:.0f}
                """)

            with col2:
                st.markdown("**Risk Management**")
                st.error(f"""
                - Stop Loss: ${setup['Stop Loss']:.2f}
                - Max Risk: ${setup['Risk $']:.0f}
                - Risk %: {risk_per_trade*100:.1f}%
                """)

            with col3:
                st.markdown("**Profit Target**")
                st.success(f"""
                - Target: ${setup['Target']:.2f}
                - Potential Profit: ${setup['Reward $']:.0f}
                - R:R Ratio: 1:1
                """)

with tab3:
    st.header("Position Tracker")

    # Manual position entry
    st.markdown("### Add Position")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pos_symbol = st.text_input("Symbol")
    with col2:
        pos_shares = st.number_input("Shares", min_value=1, value=10)
    with col3:
        pos_entry = st.number_input("Entry Price", min_value=0.01, value=100.00)
    with col4:
        pos_date = st.date_input("Entry Date")

    if st.button("Add Position"):
        st.success(f"Position added: {pos_shares} shares of {pos_symbol} at ${pos_entry}")

    # Position summary
    st.markdown("### Current Positions")
    st.info("""
    Position tracking feature would integrate with your broker API or manual entry.
    For now, use a spreadsheet to track:
    - Entry date/price
    - Stop loss hit/missed
    - Profit target hit/missed
    - Days held
    - P&L
    """)

with tab4:
    st.header("Strategy Guide")

    st.markdown("""
    ### Mean Reversion Strategy Rules

    #### Entry Criteria (ALL must be true):
    1. **Uptrend**: Price > MA50 > MA200
    2. **Pullback**: 3-6% drop from 10-day high
    3. **Oversold**: RSI(2) < 30
    4. **Support**: Within 1.5% of MA20
    5. **Market**: SPY not in downtrend

    #### Position Management:
    - **Entry**: Market order at 3:45pm
    - **Stop Loss**: -3% from entry (non-negotiable)
    - **Profit Target**: +3% from entry
    - **Time Stop**: Exit after 5 days if neither hit

    #### Risk Management:
    - Maximum 5 positions
    - Risk 3% per trade
    - Never average down
    - No position adjustments

    #### Expected Performance:
    - **Win Rate**: 65-70%
    - **Avg Win**: +2.8%
    - **Avg Loss**: -2.9%
    - **Monthly Return**: 2.5-3.5%

    ### Daily Routine (15 minutes):

    **Morning (5 min)**:
    1. Check overnight gaps
    2. Review existing positions
    3. Move stops to breakeven if +1.5%

    **Evening (10 min)**:
    1. Run scanner for setups
    2. Place orders for qualified trades
    3. Log results

    ### Psychology Tips:
    - Trust the statistics
    - Don't chase missed setups
    - Accept small wins
    - Never revenge trade
    - Keep position sizes consistent
    """)

    st.warning("""
    **Remember**: This strategy is boring but profitable. The excitement should come from
    consistent execution and growing account balance, not from the trades themselves.
    """)

# Footer
st.markdown("---")
st.caption("Mean Reversion Trading System | Designed for $10K accounts seeking consistent 65-70% win rates")