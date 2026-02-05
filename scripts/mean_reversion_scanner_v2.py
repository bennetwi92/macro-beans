#!/usr/bin/env python3
"""
Real-Time Mean Reversion Scanner V2
==================================
Scans for mean reversion setups with optimized parameters (RSI2<30).

Usage:
    python mean_reversion_scanner_v2.py
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict
import warnings
warnings.filterwarnings('ignore')

class MeanReversionScannerV2:
    """Scanner for mean reversion setups using optimized parameters"""

    def __init__(self):
        # Use optimized parameters from backtest
        self.rsi_period = 2  # RSI(2) was best performer
        self.rsi_threshold = 30  # < 30 extreme oversold
        self.pullback_min = 0.02  # Min 2% pullback
        self.pullback_max = 0.08  # Max 8% pullback
        self.ma_fast = 20  # MA20
        self.ma_slow = 50  # MA50
        self.ma_long = 200  # MA200
        self.ma_distance_max = 0.02  # Within 2% of MA20

    def calculate_rsi(self, prices: pd.Series, period: int) -> float:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high_low = data['High'] - data['Low']
        high_close = abs(data['High'] - data['Close'].shift())
        low_close = abs(data['Low'] - data['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        atr = ranges.max(axis=1).rolling(period).mean()
        return atr.iloc[-1]

    def check_setup(self, symbol: str, lookback_days: int = 300) -> Dict:
        """Check if symbol has a mean reversion setup"""
        try:
            # Download data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)
            data = yf.download(symbol, start=start_date, end=end_date, progress=False)

            if len(data) < self.ma_long + 10:
                return None

            # Flatten MultiIndex if needed
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            # Calculate indicators
            data['RSI'] = self.calculate_rsi(data['Close'], self.rsi_period)
            data[f'MA{self.ma_fast}'] = data['Close'].rolling(self.ma_fast).mean()
            data[f'MA{self.ma_slow}'] = data['Close'].rolling(self.ma_slow).mean()
            data[f'MA{self.ma_long}'] = data['Close'].rolling(self.ma_long).mean()
            data['ATR'] = self.calculate_atr(data)

            # Get latest values
            latest = data.iloc[-1]
            current_price = float(latest['Close'])
            current_rsi = float(latest['RSI'])
            ma20 = float(latest[f'MA{self.ma_fast}'])
            ma50 = float(latest[f'MA{self.ma_slow}'])
            ma200 = float(latest[f'MA{self.ma_long}'])
            atr = float(latest['ATR'])

            # Check conditions
            # 1. RSI < 30
            rsi_check = current_rsi < self.rsi_threshold

            # 2. Uptrend (price > MA50 > MA200)
            uptrend_check = current_price > ma50 and ma50 > ma200

            # 3. Pullback (2-8% from recent high)
            recent_high = data['High'].iloc[-10:].max()
            pullback_pct = (recent_high - current_price) / recent_high
            pullback_check = self.pullback_min <= pullback_pct <= self.pullback_max

            # 4. Near MA20 (within 2%)
            ma_distance = abs(current_price - ma20) / current_price
            ma20_check = ma_distance <= self.ma_distance_max

            # Calculate stop and position size
            stop_distance = 1.5 * atr
            stop_price = current_price - stop_distance
            stop_pct = (stop_distance / current_price) * 100

            # Check if ALL conditions met
            setup_valid = rsi_check and uptrend_check and pullback_check and ma20_check

            return {
                'symbol': symbol,
                'setup_valid': setup_valid,
                'current_price': current_price,
                'rsi': current_rsi,
                'ma20': ma20,
                'ma50': ma50,
                'ma200': ma200,
                'atr': atr,
                'pullback_pct': pullback_pct * 100,
                'ma_distance_pct': ma_distance * 100,
                'stop_price': stop_price,
                'stop_pct': stop_pct,
                'rsi_check': '✓' if rsi_check else '✗',
                'uptrend_check': '✓' if uptrend_check else '✗',
                'pullback_check': '✓' if pullback_check else '✗',
                'ma20_check': '✓' if ma20_check else '✗',
                'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            return None

    def scan_symbols(self, symbols: List[str]) -> pd.DataFrame:
        """Scan multiple symbols and return results"""
        results = []

        print(f"\n{'='*80}")
        print(f"Mean Reversion Scanner V2 - Optimized Parameters")
        print(f"{'='*80}")
        print(f"Strategy: RSI({self.rsi_period}) < {self.rsi_threshold}")
        print(f"Filters: Price>MA50>MA200, 2-8% pullback, near MA20")
        print(f"Scanned at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        for symbol in symbols:
            print(f"Scanning {symbol}...", end=' ')
            result = self.check_setup(symbol)

            if result:
                results.append(result)
                status = "✓ SETUP!" if result['setup_valid'] else "○"
                print(f"{status} (RSI={result['rsi']:.1f})")
            else:
                print("✗ Error/No data")

        if not results:
            print("\nNo results found.")
            return pd.DataFrame()

        # Create DataFrame
        df = pd.DataFrame(results)

        # Sort by setup_valid (True first), then by RSI (lowest first)
        df = df.sort_values(['setup_valid', 'rsi'], ascending=[False, True])

        return df

    def print_results(self, df: pd.DataFrame):
        """Print formatted scan results"""
        if df.empty:
            print("\nNo symbols scanned.")
            return

        print(f"\n{'='*80}")
        print("SCAN RESULTS")
        print(f"{'='*80}\n")

        # Separate valid setups from non-setups
        valid_setups = df[df['setup_valid'] == True]
        other_symbols = df[df['setup_valid'] == False]

        if not valid_setups.empty:
            print("🎯 VALID SETUPS (Ready to Trade):")
            print(f"{'='*80}")
            for _, row in valid_setups.iterrows():
                print(f"\n{row['symbol']} - ${row['current_price']:.2f}")
                print(f"  RSI({self.rsi_period}):      {row['rsi']:.1f} (< 30 required)")
                print(f"  Pullback:    {row['pullback_pct']:.1f}% from recent high")
                print(f"  MA Distance: {row['ma_distance_pct']:.1f}% from MA20")
                print(f"  Stop Price:  ${row['stop_price']:.2f} (-{row['stop_pct']:.1f}%)")
                print(f"  ---")
                print(f"  Entry:       ${row['current_price']:.2f}")
                print(f"  Stop:        ${row['stop_price']:.2f}")
                print(f"  Target:      ${row['current_price'] * 1.03:.2f} (+3%)")
                print(f"  Risk/Reward: 1:1.5 (approx)")
        else:
            print("⚠️  NO VALID SETUPS FOUND")

        # Show near-miss symbols
        print(f"\n{'='*80}")
        print("Other Symbols Scanned:")
        print(f"{'='*80}")

        summary = other_symbols[[
            'symbol', 'current_price', 'rsi', 'pullback_pct',
            'rsi_check', 'uptrend_check', 'pullback_check', 'ma20_check'
        ]].copy()

        summary.columns = ['Symbol', 'Price', 'RSI', 'Pullback%',
                          'RSI<30', 'Uptrend', 'Pullback', 'MA20']

        print(summary.to_string(index=False, float_format=lambda x: f'{x:.1f}'))

        # Summary stats
        print(f"\n{'='*80}")
        print(f"Summary: {len(valid_setups)} valid setups out of {len(df)} symbols scanned")
        print(f"{'='*80}\n")

def main():
    """Main scanner execution"""
    # Define watchlist (mega-cap tech from backtest)
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    # You can add more symbols if desired:
    # symbols += ['GOOG', 'JPM', 'V', 'MA', 'DIS', 'NFLX', 'CRM', 'AMD']

    # Create scanner
    scanner = MeanReversionScannerV2()

    # Scan symbols
    results = scanner.scan_symbols(symbols)

    # Print results
    scanner.print_results(results)

    # Save results to CSV
    if not results.empty:
        output_file = '/Users/williambennett/Github/macro-beans/data/mean_reversion_scan_latest.csv'
        results.to_csv(output_file, index=False)
        print(f"💾 Results saved to: {output_file}\n")

if __name__ == "__main__":
    main()
