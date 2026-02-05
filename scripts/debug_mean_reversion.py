#!/usr/bin/env python3
"""Debug script to identify the Series comparison issue"""

import pandas as pd
import numpy as np
import yfinance as yf
from scripts.mean_reversion_v2_proper import StrategyConfig, MeanReversionStrategy

# Download minimal data
data = yf.download('AAPL', start='2022-01-01', end='2024-12-31', progress=False)
print(f"Data shape: {data.shape}")
print(f"Data columns: {data.columns.tolist()}")

# Create strategy
config = StrategyConfig()
strategy = MeanReversionStrategy(config)

# Try the backtest
try:
    trades, balance = strategy.backtest_symbol('AAPL', data.copy(), 10000)
    print(f"Success! Generated {len(trades)} trades")
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
