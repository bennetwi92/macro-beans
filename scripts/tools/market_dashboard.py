#!/usr/bin/env python3
"""
Daily Market Dashboard
A terminal-based dashboard displaying key technical indicators for a predefined universe of stocks.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
import pytz

# Stock universe organized by tiers
TICKERS = {
    "Tier 1": ["SPY", "QQQ", "TSLA", "NVDA", "AAPL"],
    "Tier 2": ["AMD", "F", "BAC", "MSFT", "AMZN"],
    "Tier 3": ["META", "GM", "SMCI", "GOOGL", "INTC", "XOM", "JPM", "IWM", "AVGO", "SLV"]
}

# Indicator parameters
EMA_PERIODS = [20, 50, 200]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ADX_PERIOD = 14


def is_market_closed():
    """Check if the market is currently closed."""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)

    # Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
    market_open = time(9, 30)
    market_close = time(16, 0)

    is_weekend = now.weekday() >= 5  # Saturday = 5, Sunday = 6
    is_after_close = now.time() >= market_close

    return is_weekend or is_after_close


def get_stock_name(ticker):
    """Get the company/fund name for a ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        # Try different fields for the name
        name = info.get('longName') or info.get('shortName') or ticker
        # Shorten very long names
        if len(name) > 30:
            name = name[:27] + "..."
        return name
    except Exception:
        return ticker


def fetch_stock_data(ticker, period="1y"):
    """Fetch historical stock data from yfinance."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)

        if df.empty:
            return None

        # Only include complete days (market closed)
        # Remove today's data if market is still open
        if not is_market_closed():
            df = df.iloc[:-1]

        return df
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None


def calculate_ema(series, period):
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_rsi(series, period=14):
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(series, fast=12, slow=26, signal=9):
    """Calculate MACD line, signal line, and histogram."""
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_adx(high, low, close, period=14):
    """Calculate Average Directional Index (ADX)."""
    # Calculate True Range components
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    # True Range is the maximum of the three
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)

    # Calculate directional movement
    high_diff = high.diff()
    low_diff = -low.diff()

    # Plus DM and Minus DM
    plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0), index=high.index)
    minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0), index=low.index)

    # Smooth using Wilder's smoothing (exponential with alpha = 1/period)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr

    # Calculate DX
    di_sum = plus_di + minus_di
    di_diff = abs(plus_di - minus_di)

    # Avoid division by zero
    dx = pd.Series(np.where(di_sum != 0, 100 * di_diff / di_sum, 0), index=close.index)

    # ADX is the smoothed DX
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx


def calculate_indicators(df):
    """Calculate technical indicators for the stock data."""
    if df is None or len(df) < 200:
        return None

    indicators = {}

    # Get the last two days of data
    current = df.iloc[-1]
    previous = df.iloc[-2]

    # Previous day close
    indicators['prev_close'] = previous['Close']
    indicators['prev_close_prev'] = df.iloc[-3]['Close'] if len(df) >= 3 else None

    # EMAs
    for period in EMA_PERIODS:
        ema = calculate_ema(df['Close'], period)
        indicators[f'ema_{period}'] = ema.iloc[-1]
        indicators[f'ema_{period}_prev'] = ema.iloc[-2]

    # RSI
    rsi = calculate_rsi(df['Close'], RSI_PERIOD)
    indicators['rsi'] = rsi.iloc[-1]
    indicators['rsi_prev'] = rsi.iloc[-2]

    # MACD (we only want histogram)
    try:
        macd_line, signal_line, histogram = calculate_macd(
            df['Close'],
            fast=MACD_FAST,
            slow=MACD_SLOW,
            signal=MACD_SIGNAL
        )
        indicators['macd_hist'] = histogram.iloc[-1]
        indicators['macd_hist_prev'] = histogram.iloc[-2]
    except Exception:
        indicators['macd_hist'] = None
        indicators['macd_hist_prev'] = None

    # ADX
    try:
        adx = calculate_adx(df['High'], df['Low'], df['Close'], ADX_PERIOD)
        indicators['adx'] = adx.iloc[-1]
        indicators['adx_prev'] = adx.iloc[-2]
    except Exception:
        indicators['adx'] = None
        indicators['adx_prev'] = None

    return indicators


def get_change_arrow(current, previous):
    """Return an arrow indicating direction of change."""
    if current is None or previous is None:
        return "→"

    if current > previous:
        return "↑"
    elif current < previous:
        return "↓"
    else:
        return "→"


def format_value_with_change(current, previous, decimals=2, use_color=True,
                             current_price=None, threshold_type=None):
    """
    Format a value with its change arrow and apply color coding.

    Args:
        current: Current value
        previous: Previous value
        decimals: Number of decimal places
        use_color: Whether to apply color coding
        current_price: Current stock price (for EMA comparison)
        threshold_type: Type of threshold ('rsi', 'adx', 'macd', 'ema')
    """
    if current is None:
        return Text("N/A", style="dim")

    arrow = get_change_arrow(current, previous)
    formatted = f"{current:.{decimals}f} {arrow}"

    if not use_color:
        return Text(formatted)

    # Determine color based on threshold type
    color = "white"

    if threshold_type == 'rsi':
        if current > 70:
            color = "red"
        elif current < 30:
            color = "green"
        else:
            color = "yellow"

    elif threshold_type == 'adx':
        if current > 25:
            color = "green bold"
        else:
            color = "yellow"

    elif threshold_type == 'macd':
        if current > 0:
            color = "green"
        else:
            color = "red"

    elif threshold_type == 'ema' and current_price is not None:
        if current_price > current:
            color = "green"
        else:
            color = "red"

    return Text(formatted, style=color)


def create_dashboard_table(stock_data):
    """Create a Rich table with all stock data and indicators."""
    table = Table(
        title="📊 Daily Market Dashboard",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        title_style="bold cyan",
        border_style="bright_blue"
    )

    # Add columns
    table.add_column("Ticker", style="cyan bold", justify="left", width=8)
    table.add_column("Name", style="white", justify="left", width=32)
    table.add_column("Prev Close", justify="right", width=12)
    table.add_column("EMA 20", justify="right", width=12)
    table.add_column("EMA 50", justify="right", width=12)
    table.add_column("EMA 200", justify="right", width=12)
    table.add_column("RSI", justify="right", width=12)
    table.add_column("MACD Hist", justify="right", width=12)
    table.add_column("ADX", justify="right", width=12)

    # Add rows for each tier
    first_tier = True
    for tier_name, tickers in TICKERS.items():
        # Add visual separator before tier (except for first tier)
        if not first_tier:
            table.add_row("", "", "", "", "", "", "", "", "", end_section=True)

        first_tier = False

        # Add tier header row with prominent styling
        table.add_row(
            Text(tier_name, style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
            Text("", style="bold black on bright_yellow"),
        )

        # Add rows for each stock in this tier
        for ticker in tickers:
            data = stock_data.get(ticker)
            name = stock_data.get(f"{ticker}_name", ticker)

            if data is None:
                table.add_row(
                    ticker,
                    Text(name, style="dim"),
                    Text("N/A", style="dim"),
                    Text("N/A", style="dim"),
                    Text("N/A", style="dim"),
                    Text("N/A", style="dim"),
                    Text("N/A", style="dim"),
                    Text("N/A", style="dim"),
                    Text("N/A", style="dim")
                )
                continue

            prev_close = data['prev_close']

            table.add_row(
                ticker,
                Text(name, style="white dim"),
                format_value_with_change(
                    data['prev_close'],
                    data['prev_close_prev'],
                    decimals=2,
                    use_color=False
                ),
                format_value_with_change(
                    data['ema_20'],
                    data['ema_20_prev'],
                    decimals=2,
                    current_price=prev_close,
                    threshold_type='ema'
                ),
                format_value_with_change(
                    data['ema_50'],
                    data['ema_50_prev'],
                    decimals=2,
                    current_price=prev_close,
                    threshold_type='ema'
                ),
                format_value_with_change(
                    data['ema_200'],
                    data['ema_200_prev'],
                    decimals=2,
                    current_price=prev_close,
                    threshold_type='ema'
                ),
                format_value_with_change(
                    data['rsi'],
                    data['rsi_prev'],
                    decimals=2,
                    threshold_type='rsi'
                ),
                format_value_with_change(
                    data['macd_hist'],
                    data['macd_hist_prev'],
                    decimals=4,
                    threshold_type='macd'
                ),
                format_value_with_change(
                    data['adx'],
                    data['adx_prev'],
                    decimals=2,
                    threshold_type='adx'
                )
            )

    return table


def create_legend():
    """Create a legend explaining the color coding."""
    legend_text = Text()
    legend_text.append("Color Guide: ", style="bold white")
    legend_text.append("EMAs: ", style="bold white")
    legend_text.append("Green", style="green")
    legend_text.append(" = Price above EMA, ", style="white")
    legend_text.append("Red", style="red")
    legend_text.append(" = Price below EMA | ", style="white")

    legend_text.append("RSI: ", style="bold white")
    legend_text.append("Red", style="red")
    legend_text.append(" > 70 (overbought), ", style="white")
    legend_text.append("Green", style="green")
    legend_text.append(" < 30 (oversold), ", style="white")
    legend_text.append("Yellow", style="yellow")
    legend_text.append(" = neutral | ", style="white")

    legend_text.append("MACD: ", style="bold white")
    legend_text.append("Green", style="green")
    legend_text.append(" > 0, ", style="white")
    legend_text.append("Red", style="red")
    legend_text.append(" < 0 | ", style="white")

    legend_text.append("ADX: ", style="bold white")
    legend_text.append("Green", style="green bold")
    legend_text.append(" > 25 (strong trend)", style="white")

    return Panel(legend_text, title="📖 Legend", border_style="bright_yellow", box=box.ROUNDED)


def main():
    """Main function to run the market dashboard."""
    console = Console()

    # Display header
    header = Text()
    header.append("\n🚀 MACRO BEANS - Market Scanner\n", style="bold bright_cyan")
    header.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", style="dim")
    console.print(header)

    # Check if market is closed
    if not is_market_closed():
        console.print("⚠️  [yellow]Warning: Market is still open. Data may include incomplete trading day.[/yellow]\n")

    # Fetch and process data for each ticker
    console.print("📡 Fetching market data...\n", style="bold")

    stock_data = {}
    for tier_name, tickers in TICKERS.items():
        console.print(f"  [{tier_name}]", style="bright_yellow bold")
        for ticker in tickers:
            console.print(f"    • Loading {ticker}...", style="dim")
            # Fetch stock name
            name = get_stock_name(ticker)
            stock_data[f"{ticker}_name"] = name
            # Fetch historical data and calculate indicators
            df = fetch_stock_data(ticker)
            indicators = calculate_indicators(df)
            stock_data[ticker] = indicators

    console.print("\n")

    # Create and display the table
    table = create_dashboard_table(stock_data)
    console.print(table)

    console.print("\n")

    # Display legend
    legend = create_legend()
    console.print(legend)

    console.print("\n")


if __name__ == "__main__":
    main()
