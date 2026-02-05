"""
Backtest with FIXED RSI calculation using original strategy parameters
Tests the original strategy (RSI(2) < 30) with proper Wilder's smoothing
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List
from datetime import datetime
import os
import warnings
warnings.filterwarnings('ignore')

@dataclass
class BacktestConfig:
    """Original strategy parameters with fixed RSI"""
    initial_capital: float = 10000
    position_size_pct: float = 0.20
    max_positions: int = 5

    # Original parameters
    rsi_period: int = 2
    rsi_threshold: float = 30
    pullback_min: float = 3
    pullback_max: float = 6
    ma20_distance: float = 1.5

    # Exit parameters
    stop_loss_pct: float = 0.03
    profit_target_pct: float = 0.03
    max_hold_days: int = 5

    # Costs
    commission_per_trade: float = 1.0
    slippage_pct: float = 0.001

@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: str
    rsi_at_entry: float

class FixedBacktester:

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'

    def calculate_rsi(self, prices: pd.Series, period: int = 2) -> pd.Series:
        """Calculate RSI using Wilder's smoothing (FIXED VERSION)"""
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

    def prepare_data(self, symbol: str) -> pd.DataFrame:
        """Load and prepare data with indicators"""
        filepath = os.path.join(self.data_dir, f'{symbol}.csv')
        if not os.path.exists(filepath):
            return None

        df = pd.read_csv(filepath, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)

        if len(df) < 250:
            return None

        # Calculate indicators with FIXED RSI
        df['RSI'] = self.calculate_rsi(df['Close'], self.config.rsi_period)
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        df['MA200'] = df['Close'].rolling(200).mean()

        # Pullback calculation
        df['High_10d'] = df['High'].rolling(10).max()
        df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100

        # Distance to MA20
        df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100

        # Trend condition
        df['Uptrend'] = (df['Close'] > df['MA50']) & (df['MA50'] > df['MA200'])

        # Entry signal
        df['Entry_Signal'] = (
            (df['RSI'] < self.config.rsi_threshold) &
            (df['Uptrend']) &
            (df['Pullback_pct'] >= self.config.pullback_min) &
            (df['Pullback_pct'] <= self.config.pullback_max) &
            (df['MA20_distance'] <= self.config.ma20_distance)
        )

        return df

    def run_backtest(self, start_date: str = '2022-01-01', end_date: str = '2026-02-01'):
        """Run backtest across all stocks"""

        print("Loading and preparing data with FIXED RSI calculation...")
        universe = {}
        for file in os.listdir(self.data_dir):
            if file.endswith('.csv'):
                symbol = file.replace('.csv', '')
                df = self.prepare_data(symbol)
                if df is not None:
                    df = df[(df.index >= start_date) & (df.index <= end_date)]
                    if len(df) > 100:
                        universe[symbol] = df

        print(f"Backtesting {len(universe)} stocks from {start_date} to {end_date}")

        trades = []
        open_positions = {}
        capital = self.config.initial_capital

        # Get all trading dates
        all_dates = set()
        for df in universe.values():
            all_dates.update(df.index)
        all_dates = sorted(list(all_dates))

        # Simulate trading
        for date in all_dates:

            # Check exits first
            closed_symbols = []
            for symbol, (entry_date, entry_price, shares, rsi_entry) in open_positions.items():
                if date not in universe[symbol].index:
                    continue

                current_price = universe[symbol].loc[date, 'Close']
                days_held = (date - entry_date).days
                pnl_pct = (current_price - entry_price) / entry_price

                exit = False
                exit_reason = ""

                if pnl_pct >= self.config.profit_target_pct:
                    exit = True
                    exit_reason = "profit_target"
                elif pnl_pct <= -self.config.stop_loss_pct:
                    exit = True
                    exit_reason = "stop_loss"
                elif days_held >= self.config.max_hold_days:
                    exit = True
                    exit_reason = "max_hold"

                if exit:
                    exit_price = current_price * (1 - self.config.slippage_pct)
                    pnl = shares * (exit_price - entry_price) - self.config.commission_per_trade * 2

                    trades.append(Trade(
                        symbol=symbol,
                        entry_date=entry_date,
                        exit_date=date,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        shares=shares,
                        pnl=pnl,
                        pnl_pct=(exit_price - entry_price) / entry_price,
                        exit_reason=exit_reason,
                        rsi_at_entry=rsi_entry
                    ))

                    capital += pnl
                    closed_symbols.append(symbol)

            for symbol in closed_symbols:
                del open_positions[symbol]

            # Check for new entries
            if len(open_positions) < self.config.max_positions:
                candidates = []

                for symbol, df in universe.items():
                    if symbol in open_positions or date not in df.index:
                        continue

                    if df.loc[date, 'Entry_Signal']:
                        rsi = df.loc[date, 'RSI']
                        price = df.loc[date, 'Close']
                        candidates.append((symbol, rsi, price))

                candidates.sort(key=lambda x: x[1])

                for i in range(min(len(candidates), self.config.max_positions - len(open_positions))):
                    symbol, rsi, price = candidates[i]

                    entry_price = price * (1 + self.config.slippage_pct)
                    position_size = capital * self.config.position_size_pct
                    shares = int(position_size / entry_price)

                    if shares > 0 and shares * entry_price <= capital * 0.95:
                        open_positions[symbol] = (date, entry_price, shares, rsi)
                        capital -= shares * entry_price + self.config.commission_per_trade

        return trades, capital

    def analyze_results(self, trades: List[Trade], initial_capital: float, final_capital: float):
        """Generate comprehensive statistics"""

        if not trades:
            print("\n" + "="*80)
            print("NO TRADES EXECUTED!")
            print("="*80)
            print("\nThe strategy conditions are too restrictive.")
            print("No trades were generated during the backtest period.")
            return

        df = pd.DataFrame([{
            'symbol': t.symbol,
            'entry_date': t.entry_date,
            'exit_date': t.exit_date,
            'pnl': t.pnl,
            'pnl_pct': t.pnl_pct * 100,
            'exit_reason': t.exit_reason,
            'rsi_entry': t.rsi_at_entry,
            'days_held': (t.exit_date - t.entry_date).days
        } for t in trades])

        winners = df[df['pnl'] > 0]
        losers = df[df['pnl'] <= 0]

        print("\n" + "="*80)
        print("BACKTEST RESULTS - ORIGINAL STRATEGY WITH FIXED RSI")
        print("="*80)

        print(f"\nStrategy Configuration:")
        print(f"  RSI({self.config.rsi_period}) < {self.config.rsi_threshold}")
        print(f"  Pullback: {self.config.pullback_min}-{self.config.pullback_max}%")
        print(f"  MA20 Distance: ±{self.config.ma20_distance}%")
        print(f"  Stop/Target: ±{self.config.stop_loss_pct*100}%")
        print(f"  Max Hold: {self.config.max_hold_days} days")

        print(f"\nPerformance Summary:")
        print(f"  Period: {df['entry_date'].min().date()} to {df['exit_date'].max().date()}")
        print(f"  Total Trades: {len(df)}")
        print(f"  Winners: {len(winners)} ({len(winners)/len(df)*100:.1f}%)")
        print(f"  Losers: {len(losers)} ({len(losers)/len(df)*100:.1f}%)")

        print(f"\nReturns:")
        print(f"  Initial Capital: ${initial_capital:,.0f}")
        print(f"  Final Capital: ${final_capital:,.0f}")
        total_return = (final_capital/initial_capital - 1)*100
        print(f"  Total Return: ${final_capital - initial_capital:,.2f} ({total_return:.1f}%)")
        print(f"  Average Trade: ${df['pnl'].mean():.2f} ({df['pnl_pct'].mean():.2f}%)")
        print(f"  Best Trade: ${df['pnl'].max():.2f} ({df['pnl_pct'].max():.2f}%)")
        print(f"  Worst Trade: ${df['pnl'].min():.2f} ({df['pnl_pct'].min():.2f}%)")

        if len(winners) > 0:
            print(f"  Average Winner: ${winners['pnl'].mean():.2f} ({winners['pnl_pct'].mean():.2f}%)")
        if len(losers) > 0:
            print(f"  Average Loser: ${losers['pnl'].mean():.2f} ({losers['pnl_pct'].mean():.2f}%)")

        if len(losers) > 0 and losers['pnl'].sum() != 0:
            profit_factor = abs(winners['pnl'].sum() / losers['pnl'].sum())
            print(f"  Profit Factor: {profit_factor:.2f}")

        print(f"\nExit Analysis:")
        exit_summary = df.groupby('exit_reason').agg({
            'pnl': ['count', 'sum'],
            'pnl_pct': 'mean'
        })

        for reason in exit_summary.index:
            count = exit_summary.loc[reason, ('pnl', 'count')]
            total_pnl = exit_summary.loc[reason, ('pnl', 'sum')]
            avg_pct = exit_summary.loc[reason, ('pnl_pct', 'mean')]
            print(f"  {reason}: {count:.0f} trades, ${total_pnl:.2f} total, {avg_pct:.2f}% avg")

        print(f"\nTiming:")
        print(f"  Average Hold Period: {df['days_held'].mean():.1f} days")
        trades_per_month = len(df) / ((df['exit_date'].max() - df['entry_date'].min()).days / 30)
        print(f"  Trades per Month: {trades_per_month:.1f}")

        print(f"\nRSI at Entry:")
        print(f"  Average: {df['rsi_entry'].mean():.1f}")
        print(f"  Median: {df['rsi_entry'].median():.1f}")
        print(f"  Min: {df['rsi_entry'].min():.1f}")
        print(f"  Max: {df['rsi_entry'].max():.1f}")
        if len(winners) > 0:
            print(f"  Winners Avg RSI: {winners['rsi_entry'].mean():.1f}")
        if len(losers) > 0:
            print(f"  Losers Avg RSI: {losers['rsi_entry'].mean():.1f}")

        # Risk metrics
        cumulative_returns = (df.sort_values('exit_date')['pnl'].cumsum() + initial_capital)
        drawdowns = (cumulative_returns - cumulative_returns.expanding().max()) / cumulative_returns.expanding().max()

        print(f"\nRisk Metrics:")
        print(f"  Max Drawdown: {drawdowns.min()*100:.1f}%")
        if df['pnl_pct'].std() > 0:
            sharpe = (df['pnl_pct'].mean() / df['pnl_pct'].std()) * np.sqrt(252 / df['days_held'].mean())
            print(f"  Sharpe Ratio: {sharpe:.2f}")

        # Show sample trades
        print(f"\nSample Trades (first 10):")
        for _, trade in df.head(10).iterrows():
            result = "WIN" if trade['pnl'] > 0 else "LOSS"
            print(f"  {trade['symbol']}: {trade['entry_date'].date()} -> {trade['exit_date'].date()} "
                  f"({trade['days_held']}d) RSI={trade['rsi_entry']:.1f} {trade['pnl_pct']:+.1f}% [{result}]")

def main():
    """Run backtest with original parameters and fixed RSI"""

    print("="*80)
    print("MEAN REVERSION BACKTEST - FIXED RSI CALCULATION")
    print("Testing original strategy: RSI(2) < 30")
    print("="*80)

    config = BacktestConfig()
    backtester = FixedBacktester(config)

    # Run full backtest
    trades, final_capital = backtester.run_backtest('2022-01-01', '2026-02-01')

    # Analyze results
    backtester.analyze_results(trades, config.initial_capital, final_capital)

    # Test on different time periods
    print("\n" + "="*80)
    print("TIME PERIOD ANALYSIS")
    print("="*80)

    periods = [
        ('2022 (Bear Market)', '2022-01-01', '2022-12-31'),
        ('2023 (Recovery)', '2023-01-01', '2023-12-31'),
        ('2024-2025', '2024-01-01', '2025-12-31'),
    ]

    for period_name, start, end in periods:
        trades, final = backtester.run_backtest(start, end)
        if trades:
            win_rate = len([t for t in trades if t.pnl > 0]) / len(trades) * 100
            total_return = (final / config.initial_capital - 1) * 100
            print(f"\n{period_name}: {len(trades)} trades, {win_rate:.1f}% win rate, {total_return:+.1f}% return")
        else:
            print(f"\n{period_name}: No trades generated")

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\nWith the FIXED RSI calculation:")
    if trades:
        win_rate = len([t for t in trades if t.pnl > 0]) / len(trades) * 100
        if win_rate > 55 and (final_capital / config.initial_capital - 1) > 0.1:
            print("✓ Strategy shows promise with proper RSI calculation")
            print("✓ Consider live paper trading to validate")
        elif win_rate > 50:
            print("⚠ Strategy is marginally profitable")
            print("⚠ May need parameter optimization")
        else:
            print("✗ Strategy still underperforms even with fixed RSI")
            print("✗ Recommend exploring alternative approaches")
    else:
        print("✗ No trades generated - strategy is too restrictive")
        print("✗ Must relax parameters or try different approach")

if __name__ == "__main__":
    main()
