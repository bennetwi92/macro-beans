"""
Debug script to see why no signals are being generated
"""

import pandas as pd
import os
from datetime import datetime, timedelta
import numpy as np

DATA_DIR = 'data/stock_history'

def calculate_rsi(prices, period=2):
    """Calculate RSI using Wilder's smoothing"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


# Check a few stocks
symbols = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA']

end_date = datetime.now()
start_date = end_date - timedelta(days=90)

print(f"Scanning period: {start_date.date()} to {end_date.date()}")
print("="*80)

for symbol in symbols:
    filepath = os.path.join(DATA_DIR, f"{symbol}.csv")
    data = pd.read_csv(filepath, index_col=0, parse_dates=True)
    data.index = pd.to_datetime(data.index, utc=True).tz_localize(None)

    # Get last 90 days
    recent_data = data[data.index >= start_date].copy()

    # Calculate indicators
    recent_data['RSI_2'] = calculate_rsi(recent_data['Close'], period=2)
    recent_data['MA20'] = recent_data['Close'].rolling(20).mean()
    recent_data['MA50'] = recent_data['Close'].rolling(50).mean()
    recent_data['MA200'] = recent_data['Close'].rolling(200).mean()

    # Check for oversold signals (RSI < 30)
    oversold_days = recent_data[recent_data['RSI_2'] < 30]

    print(f"\n{symbol}:")
    print(f"  Total days: {len(recent_data)}")
    print(f"  RSI < 30 days: {len(oversold_days)}")
    print(f"  Min RSI: {recent_data['RSI_2'].min():.1f}")
    print(f"  Current RSI: {recent_data['RSI_2'].iloc[-1]:.1f}")

    if len(oversold_days) > 0:
        print(f"  Oversold dates:")
        for date, row in oversold_days.tail(5).iterrows():
            # Check conditions
            in_uptrend = row['Close'] > row['MA50'] and row['MA50'] > row['MA200']

            high_10d = recent_data.loc[:date, 'High'].tail(10).max()
            pullback_pct = ((high_10d - row['Close']) / high_10d) * 100
            valid_pullback = 3 <= pullback_pct <= 6

            dist_to_ma20 = abs((row['Close'] - row['MA20']) / row['MA20']) * 100

            print(f"    {date.date()}: RSI={row['RSI_2']:.1f}, Uptrend={in_uptrend}, " +
                  f"Pullback={pullback_pct:.1f}% (valid={valid_pullback}), " +
                  f"Dist_MA20={dist_to_ma20:.1f}%")

print("\n" + "="*80)
print("CONCLUSION:")
print("If very few oversold signals, market is strong (no mean reversion setups)")
print("This is expected in a bull market - wait for pullbacks")
