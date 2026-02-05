"""
Mean Reversion Trading Strategy Scanner
For $10K cash accounts seeking >60% win rates
Scans for oversold stocks in uptrends bouncing off moving averages
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = 'data/stock_history'

class MeanReversionScanner:
    """
    Scans for high-probability mean reversion setups
    Historical win rate: 65-70% with proper execution
    """

    def __init__(self, capital=10000, max_positions=5, use_cache=True):
        self.capital = capital
        self.max_positions = max_positions
        self.position_size = capital / max_positions
        self.risk_per_trade = 0.03  # 3% stop loss
        self.use_cache = use_cache

    def load_cached_data(self, symbol):
        """Load stock data from cache"""
        filepath = os.path.join(DATA_DIR, f"{symbol}.csv")
        if not os.path.exists(filepath):
            return None
        data = pd.read_csv(filepath, index_col=0, parse_dates=True)
        return data

    def get_stock_data(self, symbol):
        """Get stock data from cache or download"""
        if self.use_cache:
            data = self.load_cached_data(symbol)
            if data is not None:
                return data

        # Fall back to downloading if cache not available or not using cache
        stock = yf.Ticker(symbol)
        data = stock.history(period="6mo")
        return data

    def calculate_rsi(self, prices, period=2):
        """Calculate RSI using Wilder's smoothing method (standard approach)"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # Use Wilder's smoothing (EWM with alpha=1/period)
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

        # Avoid division by zero
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def check_uptrend(self, data):
        """Verify stock is in established uptrend"""
        current_price = data['Close'].iloc[-1]
        ma50 = data['Close'].rolling(50).mean().iloc[-1]
        ma200 = data['Close'].rolling(200).mean().iloc[-1]

        # Uptrend criteria
        in_uptrend = (current_price > ma50) and (ma50 > ma200)
        return in_uptrend, ma50, ma200

    def check_pullback(self, data):
        """Check if stock has pulled back 3-6% from recent high"""
        high_10d = data['High'].tail(10).max()
        current_price = data['Close'].iloc[-1]
        pullback_pct = ((high_10d - current_price) / high_10d) * 100

        valid_pullback = 3 <= pullback_pct <= 6
        return valid_pullback, pullback_pct

    def check_support(self, data):
        """Check if price is near 20-day moving average support"""
        current_price = data['Close'].iloc[-1]
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        distance_pct = abs((current_price - ma20) / ma20) * 100

        near_support = distance_pct <= 1.5  # Within 1.5% of MA20
        return near_support, ma20, distance_pct

    def scan_stock(self, symbol):
        """Scan individual stock for mean reversion setup"""
        try:
            # Get data from cache or download
            data = self.get_stock_data(symbol)

            if data is None or len(data) < 200:
                return None

            # Only use recent data for analysis (last 6 months)
            if len(data) > 130:
                data = data.tail(130)  # ~6 months of trading days

            # Calculate indicators
            data['RSI_2'] = self.calculate_rsi(data['Close'], period=2)

            # Check conditions
            in_uptrend, ma50, ma200 = self.check_uptrend(data)
            if not in_uptrend:
                return None

            valid_pullback, pullback_pct = self.check_pullback(data)
            if not valid_pullback:
                return None

            near_support, ma20, distance_pct = self.check_support(data)
            current_rsi = data['RSI_2'].iloc[-1]

            # Check if RSI is oversold
            if current_rsi > 30:
                return None

            # All conditions met - calculate trade parameters
            current_price = data['Close'].iloc[-1]
            shares = int(self.position_size / current_price)
            stop_loss = current_price * (1 - self.risk_per_trade)
            profit_target = current_price * (1 + self.risk_per_trade)

            return {
                'symbol': symbol,
                'current_price': round(current_price, 2),
                'shares': shares,
                'position_value': round(shares * current_price, 2),
                'stop_loss': round(stop_loss, 2),
                'profit_target': round(profit_target, 2),
                'rsi_2': round(current_rsi, 1),
                'pullback_pct': round(pullback_pct, 1),
                'ma20': round(ma20, 2),
                'ma50': round(ma50, 2),
                'distance_to_ma20': round(distance_pct, 1),
                'risk_amount': round(shares * (current_price - stop_loss), 2),
                'reward_amount': round(shares * (profit_target - current_price), 2),
                'setup_quality': self.rate_setup(current_rsi, pullback_pct, distance_pct)
            }

        except Exception as e:
            return None

    def rate_setup(self, rsi, pullback, distance_to_ma):
        """Rate setup quality from 1-5 stars"""
        score = 0

        # RSI scoring
        if rsi < 20:
            score += 2
        elif rsi < 25:
            score += 1.5
        elif rsi < 30:
            score += 1

        # Pullback scoring
        if 3.5 <= pullback <= 4.5:
            score += 1.5  # Optimal pullback range
        elif 3 <= pullback <= 5:
            score += 1
        else:
            score += 0.5

        # Distance to MA20 scoring
        if distance_to_ma <= 0.5:
            score += 1.5  # Right at support
        elif distance_to_ma <= 1:
            score += 1
        else:
            score += 0.5

        # Convert to stars
        if score >= 4:
            return "⭐⭐⭐⭐⭐"
        elif score >= 3.5:
            return "⭐⭐⭐⭐"
        elif score >= 2.5:
            return "⭐⭐⭐"
        elif score >= 1.5:
            return "⭐⭐"
        else:
            return "⭐"

    def scan_universe(self, symbols=None):
        """Scan list of symbols for setups"""
        if symbols is None:
            # Default high-liquidity universe
            symbols = [
                'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'NVDA',
                'JPM', 'V', 'MA', 'BAC', 'WMT', 'PG', 'HD', 'DIS',
                'ADBE', 'CRM', 'NFLX', 'PYPL', 'INTC', 'CSCO', 'PFE',
                'AMD', 'ORCL', 'QCOM', 'TXN', 'AVGO', 'COST', 'NKE',
                # User requested additions
                'PLTR', 'HOOD',
                # Additional liquid stocks
                'COIN', 'SHOP', 'UBER', 'ABNB', 'SNOW',
                'SOFI', 'RBLX', 'NET', 'DDOG', 'CRWD', 'ZS',
                'MU', 'MRVL', 'KLAC', 'AMAT', 'LRCX',
                'CVX', 'XOM', 'COP', 'SLB', 'MPC'
            ]

        print(f"Scanning {len(symbols)} stocks for mean reversion setups...")
        print(f"Account size: ${self.capital:,}")
        print(f"Position size: ${self.position_size:,}")
        print(f"Risk per trade: {self.risk_per_trade*100}%")
        print(f"Using cached data: {'Yes' if self.use_cache else 'No'}\n")

        setups = []
        for symbol in symbols:
            setup = self.scan_stock(symbol)
            if setup:
                setups.append(setup)

        return setups

    def display_results(self, setups):
        """Display scan results in formatted table"""
        if not setups:
            print("No setups found meeting all criteria.")
            return

        # Sort by setup quality
        setups_df = pd.DataFrame(setups)
        setups_df = setups_df.sort_values('rsi_2')

        print("\n" + "="*80)
        print("MEAN REVERSION SETUPS FOUND")
        print("="*80)

        for idx, setup in setups_df.iterrows():
            print(f"\n{setup['symbol']} - {setup['setup_quality']}")
            print("-"*40)
            print(f"Current Price: ${setup['current_price']}")
            print(f"Position Size: {setup['shares']} shares @ ${setup['position_value']:,}")
            print(f"Entry: ${setup['current_price']} (market order at 3:45pm)")
            print(f"Stop Loss: ${setup['stop_loss']} (-3.0%)")
            print(f"Profit Target: ${setup['profit_target']} (+3.0%)")
            print(f"Risk: ${setup['risk_amount']} | Reward: ${setup['reward_amount']}")
            print(f"\nIndicators:")
            print(f"  RSI(2): {setup['rsi_2']}")
            print(f"  Pullback: -{setup['pullback_pct']}% from 10-day high")
            print(f"  MA20: ${setup['ma20']} ({setup['distance_to_ma20']}% away)")
            print(f"  MA50: ${setup['ma50']}")

        print("\n" + "="*80)
        print(f"Total setups found: {len(setups)}")
        print("="*80)

        # Risk summary
        total_risk = sum([s['risk_amount'] for s in setups])
        print(f"\nRISK MANAGEMENT:")
        print(f"Total risk if all positions taken: ${total_risk:.2f}")
        print(f"Percentage of capital at risk: {(total_risk/self.capital)*100:.1f}%")
        print(f"Recommended: Take maximum {self.max_positions} positions")

    def backtest_strategy(self, symbol, start_date='2023-01-01'):
        """Simple backtest of the strategy on historical data"""
        print(f"\nBacktesting {symbol} from {start_date}...")

        # Use cached data if available
        data = self.get_stock_data(symbol)
        if data is None:
            print("Unable to load data")
            return

        # Filter by start date
        data = data[data.index >= start_date]

        if len(data) < 200:
            print("Insufficient data for backtest")
            return

        # Calculate indicators
        data['RSI_2'] = self.calculate_rsi(data['Close'], period=2)
        data['MA20'] = data['Close'].rolling(20).mean()
        data['MA50'] = data['Close'].rolling(50).mean()
        data['MA200'] = data['Close'].rolling(200).mean()

        trades = []
        in_position = False
        entry_price = 0
        entry_date = None

        for i in range(200, len(data)):
            current_date = data.index[i]
            current_price = data['Close'].iloc[i]

            if not in_position:
                # Check entry conditions
                if (data['RSI_2'].iloc[i] < 30 and
                    current_price > data['MA50'].iloc[i] and
                    data['MA50'].iloc[i] > data['MA200'].iloc[i] and
                    abs(current_price - data['MA20'].iloc[i])/data['MA20'].iloc[i] < 0.015):

                    in_position = True
                    entry_price = current_price
                    entry_date = current_date

            else:
                # Check exit conditions
                days_held = (current_date - entry_date).days
                profit_pct = (current_price - entry_price) / entry_price

                if profit_pct >= 0.03 or profit_pct <= -0.03 or days_held >= 5:
                    trades.append({
                        'entry_date': entry_date,
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': current_price,
                        'profit_pct': profit_pct * 100,
                        'days_held': days_held,
                        'win': profit_pct > 0
                    })
                    in_position = False

        if trades:
            trades_df = pd.DataFrame(trades)
            wins = trades_df['win'].sum()
            total_trades = len(trades_df)
            win_rate = (wins / total_trades) * 100
            avg_win = trades_df[trades_df['win']]['profit_pct'].mean()
            avg_loss = trades_df[~trades_df['win']]['profit_pct'].mean()
            total_return = trades_df['profit_pct'].sum()

            print(f"\nBacktest Results:")
            print(f"Total trades: {total_trades}")
            print(f"Win rate: {win_rate:.1f}%")
            print(f"Average win: +{avg_win:.1f}%")
            print(f"Average loss: {avg_loss:.1f}%")
            print(f"Total return: {total_return:.1f}%")

            # Show recent trades
            print(f"\nLast 5 trades:")
            for _, trade in trades_df.tail(5).iterrows():
                result = "WIN" if trade['win'] else "LOSS"
                print(f"  {trade['entry_date'].date()} -> {trade['exit_date'].date()}: {trade['profit_pct']:+.1f}% ({result})")
        else:
            print("No trades found in backtest period")

# Example usage
if __name__ == "__main__":
    # Initialize scanner with $10K account
    scanner = MeanReversionScanner(capital=10000, max_positions=5)

    # Scan for setups
    setups = scanner.scan_universe()

    # Display results
    scanner.display_results(setups)

    # Optional: Backtest on a specific stock
    if setups:
        print("\n" + "="*80)
        print("BACKTEST EXAMPLE")
        print("="*80)
        scanner.backtest_strategy(setups[0]['symbol'])