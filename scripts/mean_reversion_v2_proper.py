#!/usr/bin/env python3
"""
Mean Reversion Strategy V2 - Production Ready
===========================================
Proper risk-based position sizing with IBKR Lite assumptions.

Key Changes:
- Risk 1% of account per trade (not fixed % of capital)
- $0 commissions for IBKR Lite
- $0.05/share slippage
- Optimized strategy parameters
"""

import pandas as pd
import numpy as np
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Configuration
@dataclass
class StrategyConfig:
    """Strategy configuration with optimizable parameters"""
    # Account settings
    initial_capital: float = 10_000
    risk_per_trade: float = 0.01  # Risk 1% per trade
    max_positions: int = 5  # Maximum concurrent positions

    # Entry conditions
    rsi_period: int = 5  # Changed from 2 to 5 (less extreme)
    rsi_threshold: float = 35  # Changed from 30 to 35 (more signals)
    pullback_min: float = 0.02  # Minimum 2% pullback
    pullback_max: float = 0.08  # Maximum 8% pullback
    ma_fast: int = 20  # Fast MA for trend
    ma_slow: int = 50  # Slow MA for trend
    ma_long: int = 200  # Long MA for major trend

    # Exit conditions
    profit_target: float = 0.03  # 3% profit target
    stop_loss: float = 0.02  # 2% stop loss (tighter than before)
    max_hold_days: int = 7  # Maximum holding period
    use_trailing_stop: bool = True  # Enable trailing stop
    trailing_stop_pct: float = 0.015  # 1.5% trailing stop

    # Costs (IBKR Lite)
    commission_per_share: float = 0.0  # Free for IBKR Lite
    slippage_per_share: float = 0.05  # 5 cents per share

@dataclass
class Trade:
    """Single trade record"""
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    stop_price: float
    risk_amount: float
    gross_pnl: float
    slippage_cost: float
    net_pnl: float
    exit_reason: str
    hold_days: int
    return_pct: float

class MeanReversionStrategy:
    """Production-ready mean reversion strategy with proper risk management"""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.trades: List[Trade] = []
        self.equity_curve = []

    def calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_position_size(self, entry_price: float, stop_price: float,
                               account_balance: float) -> int:
        """
        Calculate position size based on 1% risk rule.
        Position Size = (Account Balance × Risk %) / (Entry - Stop)
        """
        risk_amount = account_balance * self.config.risk_per_trade
        risk_per_share = abs(entry_price - stop_price)

        if risk_per_share <= 0:
            return 0

        shares = int(risk_amount / risk_per_share)

        # Ensure we don't exceed account balance
        max_shares_by_capital = int(account_balance * 0.95 / entry_price)  # Use max 95% of capital
        shares = min(shares, max_shares_by_capital)

        # Minimum position size (avoid tiny positions)
        if shares < 1:
            return 0

        return shares

    def check_entry_conditions(self, data: pd.DataFrame, idx: int) -> bool:
        """Check if entry conditions are met"""
        row = data.iloc[idx]

        # Skip if any indicators are NaN
        if pd.isna(row['RSI']) or pd.isna(row[f'MA{self.config.ma_slow}']) or pd.isna(row[f'MA{self.config.ma_long}']):
            return False

        # 1. RSI condition
        if row['RSI'] >= self.config.rsi_threshold:
            return False

        # 2. Uptrend condition (price > MA50 > MA200)
        close_val = float(row['Close'])
        ma_slow_val = float(row[f'MA{self.config.ma_slow}'])
        ma_long_val = float(row[f'MA{self.config.ma_long}'])

        if not (close_val > ma_slow_val and ma_slow_val > ma_long_val):
            return False

        # 3. Pullback condition
        recent_high = data['High'].iloc[max(0, idx-10):idx+1].max()
        pullback_pct = (recent_high - close_val) / recent_high

        if not (self.config.pullback_min <= pullback_pct <= self.config.pullback_max):
            return False

        # 4. Near MA20 condition (within 2%)
        ma_fast_val = float(row[f'MA{self.config.ma_fast}'])
        ma_distance = abs(close_val - ma_fast_val) / close_val
        if ma_distance > 0.02:
            return False

        return True

    def backtest_symbol(self, symbol: str, data: pd.DataFrame,
                       account_balance: float) -> Tuple[List[Trade], float]:
        """Backtest strategy on a single symbol"""
        # Flatten MultiIndex columns if they exist (from yfinance)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        # Make a copy to avoid SettingWithCopyWarning
        data = data.copy()

        # Calculate indicators
        data['RSI'] = self.calculate_rsi(data['Close'], self.config.rsi_period)
        data[f'MA{self.config.ma_fast}'] = data['Close'].rolling(self.config.ma_fast).mean()
        data[f'MA{self.config.ma_slow}'] = data['Close'].rolling(self.config.ma_slow).mean()
        data[f'MA{self.config.ma_long}'] = data['Close'].rolling(self.config.ma_long).mean()

        # ATR for dynamic stops (optional)
        high_low = data['High'] - data['Low']
        high_close = abs(data['High'] - data['Close'].shift())
        low_close = abs(data['Low'] - data['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        data['ATR'] = ranges.max(axis=1).rolling(14).mean()

        trades = []
        position = None
        highest_price = None

        for idx in range(self.config.ma_long, len(data)):
            current_date = data.index[idx]
            current_price = float(data['Close'].iloc[idx])  # Convert to float

            # Check for exit if in position
            if position is not None:
                exit_triggered = False
                exit_reason = ""
                exit_price = current_price

                # Update highest price for trailing stop
                if self.config.use_trailing_stop:
                    if highest_price is None or current_price > highest_price:
                        highest_price = current_price

                # Check profit target
                if current_price >= position['entry_price'] * (1 + self.config.profit_target):
                    exit_triggered = True
                    exit_reason = "Profit Target"

                # Check stop loss
                elif current_price <= position['stop_price']:
                    exit_triggered = True
                    exit_reason = "Stop Loss"
                    exit_price = position['stop_price']

                # Check trailing stop
                elif self.config.use_trailing_stop and highest_price:
                    trailing_stop = highest_price * (1 - self.config.trailing_stop_pct)
                    if current_price <= trailing_stop:
                        exit_triggered = True
                        exit_reason = "Trailing Stop"
                        exit_price = trailing_stop

                # Check max hold period
                elif (current_date - position['entry_date']).days >= self.config.max_hold_days:
                    exit_triggered = True
                    exit_reason = "Max Hold Period"

                if exit_triggered:
                    # Calculate P&L
                    gross_pnl = (exit_price - position['entry_price']) * position['shares']
                    slippage_cost = self.config.slippage_per_share * position['shares'] * 2  # Entry + exit
                    net_pnl = gross_pnl - slippage_cost

                    trade = Trade(
                        symbol=symbol,
                        entry_date=position['entry_date'],
                        exit_date=current_date,
                        entry_price=position['entry_price'],
                        exit_price=exit_price,
                        shares=position['shares'],
                        stop_price=position['stop_price'],
                        risk_amount=position['risk_amount'],
                        gross_pnl=gross_pnl,
                        slippage_cost=slippage_cost,
                        net_pnl=net_pnl,
                        exit_reason=exit_reason,
                        hold_days=(current_date - position['entry_date']).days,
                        return_pct=(exit_price / position['entry_price'] - 1) * 100
                    )
                    trades.append(trade)
                    account_balance += net_pnl
                    position = None
                    highest_price = None

            # Check for entry if no position
            elif self.check_entry_conditions(data, idx):
                # Calculate position size with proper risk management
                entry_price = current_price

                # Use ATR-based stop if available, otherwise fixed percentage
                if pd.notna(data['ATR'].iloc[idx]):
                    stop_distance = 1.5 * data['ATR'].iloc[idx]  # 1.5x ATR stop
                    stop_price = entry_price - stop_distance
                else:
                    stop_price = entry_price * (1 - self.config.stop_loss)

                shares = self.calculate_position_size(entry_price, stop_price, account_balance)

                if shares > 0:
                    risk_amount = account_balance * self.config.risk_per_trade
                    position = {
                        'entry_date': current_date,
                        'entry_price': entry_price,
                        'stop_price': stop_price,
                        'shares': shares,
                        'risk_amount': risk_amount
                    }
                    highest_price = entry_price

        return trades, account_balance

    def run_backtest(self, symbols: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """Run backtest across multiple symbols"""
        print(f"\n{'='*60}")
        print(f"Mean Reversion Strategy V2 - Production Backtest")
        print(f"{'='*60}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Initial Capital: ${self.config.initial_capital:,.0f}")
        print(f"Risk Per Trade: {self.config.risk_per_trade*100:.1f}%")
        print(f"Strategy: RSI({self.config.rsi_period}) < {self.config.rsi_threshold}")
        print(f"{'='*60}\n")

        all_trades = []

        for symbol in symbols:
            print(f"Loading {symbol}...", end='')
            try:
                # Load from cached CSV
                csv_path = f'/Users/williambennett/Github/macro-beans/data/stock_history/{symbol}.csv'
                if not os.path.exists(csv_path):
                    print(f" File not found")
                    continue

                data = pd.read_csv(csv_path, index_col=0, parse_dates=True)

                # Ensure index is DatetimeIndex and convert timezone-aware to naive
                data.index = pd.to_datetime(data.index, utc=True).tz_convert(None)

                # Filter by date range
                data = data[(data.index >= start_date) & (data.index <= end_date)]

                if len(data) < self.config.ma_long + 10:
                    print(f" Insufficient data")
                    continue
                print(f" OK ({len(data)} days)")

                # Run backtest for this symbol
                symbol_trades, _ = self.backtest_symbol(
                    symbol, data, self.config.initial_capital
                )
                all_trades.extend(symbol_trades)

            except Exception as e:
                import traceback
                print(f" Error: {e}")
                if "Series" in str(e):
                    traceback.print_exc()
                continue

        # Sort trades by entry date for sequential processing
        all_trades.sort(key=lambda x: x.entry_date)

        # Recalculate with proper account balance tracking
        account_balance = self.config.initial_capital
        final_trades = []
        open_positions = {}
        daily_balance = {}

        # Create date range for tracking
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')

        for date in all_dates:
            # Check for exits
            for symbol in list(open_positions.keys()):
                trade = open_positions[symbol]
                if trade.exit_date <= date:
                    account_balance += trade.net_pnl
                    final_trades.append(trade)
                    del open_positions[symbol]

            # Check for new entries (limit concurrent positions)
            if len(open_positions) < self.config.max_positions:
                for trade in all_trades:
                    if trade.entry_date == date and trade.symbol not in open_positions:
                        if len(open_positions) < self.config.max_positions:
                            # Recalculate position size with current balance
                            shares = self.calculate_position_size(
                                trade.entry_price,
                                trade.stop_price,
                                account_balance
                            )
                            if shares > 0:
                                # Update trade with new position size
                                trade.shares = shares
                                trade.gross_pnl = (trade.exit_price - trade.entry_price) * shares
                                trade.slippage_cost = self.config.slippage_per_share * shares * 2
                                trade.net_pnl = trade.gross_pnl - trade.slippage_cost

                                open_positions[trade.symbol] = trade

            daily_balance[date] = account_balance

        # Close any remaining positions
        for trade in open_positions.values():
            account_balance += trade.net_pnl
            final_trades.append(trade)

        self.trades = final_trades

        # Create results DataFrame
        if final_trades:
            results_df = pd.DataFrame([
                {
                    'Symbol': t.symbol,
                    'Entry Date': t.entry_date.strftime('%Y-%m-%d'),
                    'Exit Date': t.exit_date.strftime('%Y-%m-%d'),
                    'Entry Price': t.entry_price,
                    'Exit Price': t.exit_price,
                    'Shares': t.shares,
                    'Position Value': t.entry_price * t.shares,
                    'Risk Amount': t.risk_amount,
                    'Gross P&L': t.gross_pnl,
                    'Slippage': t.slippage_cost,
                    'Net P&L': t.net_pnl,
                    'Return %': t.return_pct,
                    'Exit Reason': t.exit_reason,
                    'Hold Days': t.hold_days
                }
                for t in final_trades
            ])
            results_df = results_df.sort_values('Entry Date')
        else:
            results_df = pd.DataFrame()

        return results_df

    def calculate_metrics(self, results_df: pd.DataFrame) -> Dict:
        """Calculate performance metrics"""
        if results_df.empty:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0
            }

        # Basic metrics
        total_trades = len(results_df)
        winners = results_df[results_df['Net P&L'] > 0]
        losers = results_df[results_df['Net P&L'] < 0]

        win_rate = len(winners) / total_trades if total_trades > 0 else 0

        # Profit factor
        gross_profits = winners['Net P&L'].sum() if len(winners) > 0 else 0
        gross_losses = abs(losers['Net P&L'].sum()) if len(losers) > 0 else 1
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else 0

        # Returns for Sharpe
        results_df['Cumulative P&L'] = results_df['Net P&L'].cumsum()
        results_df['Account Balance'] = self.config.initial_capital + results_df['Cumulative P&L']

        # Daily returns
        if len(results_df) > 1:
            returns = results_df['Net P&L'] / results_df['Account Balance'].shift(1)
            returns = returns.dropna()

            if len(returns) > 0 and returns.std() > 0:
                sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252)
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        # Maximum drawdown
        cumulative = self.config.initial_capital + results_df['Net P&L'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() if len(drawdown) > 0 else 0

        # Additional metrics
        avg_win = winners['Net P&L'].mean() if len(winners) > 0 else 0
        avg_loss = losers['Net P&L'].mean() if len(losers) > 0 else 0
        avg_position_size = results_df['Position Value'].mean()
        max_position_size = results_df['Position Value'].max()

        return {
            'total_trades': total_trades,
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': win_rate * 100,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown * 100,
            'total_net_pnl': results_df['Net P&L'].sum(),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_position_size': avg_position_size,
            'max_position_size': max_position_size,
            'total_slippage': results_df['Slippage'].sum(),
            'final_balance': self.config.initial_capital + results_df['Net P&L'].sum()
        }

    def print_summary(self, results_df: pd.DataFrame, metrics: Dict):
        """Print comprehensive backtest summary"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS SUMMARY")
        print("="*60)

        print(f"\n📊 Performance Metrics:")
        print(f"  Initial Capital:     ${self.config.initial_capital:,.0f}")
        print(f"  Final Balance:       ${metrics['final_balance']:,.0f}")
        print(f"  Total Net P&L:       ${metrics['total_net_pnl']:+,.2f}")
        print(f"  Total Return:        {(metrics['final_balance']/self.config.initial_capital - 1)*100:+.2f}%")

        print(f"\n📈 Trade Statistics:")
        print(f"  Total Trades:        {metrics['total_trades']}")
        print(f"  Winners:             {metrics['winners']}")
        print(f"  Losers:              {metrics['losers']}")
        print(f"  Win Rate:            {metrics['win_rate']:.1f}%")
        print(f"  Profit Factor:       {metrics['profit_factor']:.2f}")

        print(f"\n💰 P&L Analysis:")
        print(f"  Average Win:         ${metrics['avg_win']:+,.2f}")
        print(f"  Average Loss:        ${metrics['avg_loss']:+,.2f}")
        print(f"  Win/Loss Ratio:      {abs(metrics['avg_win']/metrics['avg_loss']) if metrics['avg_loss'] != 0 else 0:.2f}")

        print(f"\n📉 Risk Metrics:")
        print(f"  Sharpe Ratio:        {metrics['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:        {metrics['max_drawdown']:.2f}%")
        print(f"  Avg Position Size:   ${metrics['avg_position_size']:,.0f}")
        print(f"  Max Position Size:   ${metrics['max_position_size']:,.0f}")

        print(f"\n💸 Costs:")
        print(f"  Total Slippage:      ${metrics['total_slippage']:,.2f}")
        print(f"  Commissions:         $0.00 (IBKR Lite)")

        if not results_df.empty:
            # Monthly breakdown
            results_df['YearMonth'] = pd.to_datetime(results_df['Entry Date']).dt.to_period('M')
            monthly = results_df.groupby('YearMonth')['Net P&L'].sum()

            print(f"\n📅 Monthly P&L:")
            for period, pnl in monthly.items():
                print(f"  {period}: ${pnl:+,.2f}")

            # Exit reason breakdown
            print(f"\n🎯 Exit Reasons:")
            exit_stats = results_df.groupby('Exit Reason').agg({
                'Net P&L': ['count', 'sum', 'mean']
            }).round(2)
            exit_stats.columns = ['Count', 'Total P&L', 'Avg P&L']
            print(exit_stats.to_string(float_format=lambda x: f'${x:,.2f}'))

            # Top trades
            print(f"\n🏆 Top 5 Winning Trades:")
            top_trades = results_df.nlargest(5, 'Net P&L')[
                ['Symbol', 'Entry Date', 'Net P&L', 'Return %', 'Hold Days']
            ]
            for _, trade in top_trades.iterrows():
                print(f"  {trade['Symbol']} ({trade['Entry Date']}): "
                      f"${trade['Net P&L']:+,.2f} ({trade['Return %']:+.1f}% in {trade['Hold Days']} days)")

            print(f"\n💀 Top 5 Losing Trades:")
            worst_trades = results_df.nsmallest(5, 'Net P&L')[
                ['Symbol', 'Entry Date', 'Net P&L', 'Return %', 'Hold Days']
            ]
            for _, trade in worst_trades.iterrows():
                print(f"  {trade['Symbol']} ({trade['Entry Date']}): "
                      f"${trade['Net P&L']:+,.2f} ({trade['Return %']:+.1f}% in {trade['Hold Days']} days)")

def optimize_parameters():
    """Test different parameter combinations to find optimal settings"""
    print("\n" + "="*60)
    print("PARAMETER OPTIMIZATION")
    print("="*60)

    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    # Test different parameter combinations
    test_configs = [
        # Baseline (current)
        {'name': 'Baseline (RSI5<35)', 'rsi_period': 5, 'rsi_threshold': 35,
         'stop_loss': 0.02, 'profit_target': 0.03},

        # More aggressive entries
        {'name': 'Aggressive (RSI5<40)', 'rsi_period': 5, 'rsi_threshold': 40,
         'stop_loss': 0.02, 'profit_target': 0.03},

        # Original extreme
        {'name': 'Extreme (RSI2<30)', 'rsi_period': 2, 'rsi_threshold': 30,
         'stop_loss': 0.03, 'profit_target': 0.03},

        # Wider stops
        {'name': 'Wide Stop (RSI5<35)', 'rsi_period': 5, 'rsi_threshold': 35,
         'stop_loss': 0.03, 'profit_target': 0.04},

        # Tighter stops, quicker profits
        {'name': 'Scalping (RSI5<35)', 'rsi_period': 5, 'rsi_threshold': 35,
         'stop_loss': 0.015, 'profit_target': 0.02},
    ]

    results_summary = []

    for test in test_configs:
        print(f"\nTesting: {test['name']}")
        print("-" * 40)

        config = StrategyConfig(
            rsi_period=test['rsi_period'],
            rsi_threshold=test['rsi_threshold'],
            stop_loss=test['stop_loss'],
            profit_target=test['profit_target']
        )

        strategy = MeanReversionStrategy(config)
        results_df = strategy.run_backtest(symbols, '2022-01-01', '2024-12-31')

        if not results_df.empty:
            metrics = strategy.calculate_metrics(results_df)

            results_summary.append({
                'Config': test['name'],
                'Trades': metrics['total_trades'],
                'Win Rate': f"{metrics['win_rate']:.1f}%",
                'PF': f"{metrics['profit_factor']:.2f}",
                'Net P&L': f"${metrics['total_net_pnl']:+,.0f}",
                'Sharpe': f"{metrics['sharpe_ratio']:.2f}",
                'Max DD': f"{metrics['max_drawdown']:.1f}%"
            })

            print(f"  Trades: {metrics['total_trades']}, "
                  f"Win Rate: {metrics['win_rate']:.1f}%, "
                  f"P&L: ${metrics['total_net_pnl']:+,.0f}")
        else:
            print("  No trades generated")

    if results_summary:
        print("\n" + "="*60)
        print("OPTIMIZATION RESULTS COMPARISON")
        print("="*60)
        summary_df = pd.DataFrame(results_summary)
        print(summary_df.to_string(index=False))

    return results_summary

def main():
    """Main execution function"""
    # Run with optimized parameters
    config = StrategyConfig()  # Uses defaults: RSI(5)<35, 2% stop, 3% target
    strategy = MeanReversionStrategy(config)

    # Define symbols and period
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']
    start_date = '2022-01-01'
    end_date = '2024-12-31'

    # Run main backtest
    results_df = strategy.run_backtest(symbols, start_date, end_date)

    if not results_df.empty:
        # Calculate and print metrics
        metrics = strategy.calculate_metrics(results_df)
        strategy.print_summary(results_df, metrics)

        # Save results to CSV
        output_file = '/Users/williambennett/Github/macro-beans/data/mean_reversion_v2_results.csv'
        results_df.to_csv(output_file, index=False)
        print(f"\n💾 Results saved to: {output_file}")

        # Show first few trades
        print("\n📋 Sample Trades (First 10):")
        print(results_df.head(10).to_string(index=False))
    else:
        print("\n⚠️ No trades were generated with current parameters")

    # Run parameter optimization
    print("\n" + "="*60)
    print("Running parameter optimization...")
    print("="*60)
    optimize_parameters()

if __name__ == "__main__":
    main()