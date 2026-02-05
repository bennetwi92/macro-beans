"""
Side-by-side comparison of original vs optimized parameters
Shows why the original strategy fails and what works better
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List
import os
import warnings
warnings.filterwarnings('ignore')

@dataclass
class BacktestConfig:
    name: str
    initial_capital: float = 10000
    position_size_pct: float = 0.20
    max_positions: int = 5
    rsi_period: int = 2
    rsi_threshold: float = 30
    pullback_min: float = 3
    pullback_max: float = 6
    ma20_distance: float = 1.5
    stop_loss_pct: float = 0.03
    profit_target_pct: float = 0.03
    max_hold_days: int = 5
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

def calculate_rsi(prices: pd.Series, period: int) -> pd.Series:
    """Calculate RSI using Wilder's smoothing"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data(symbol: str, config: BacktestConfig, data_dir: str) -> pd.DataFrame:
    """Load and prepare data with indicators"""
    filepath = os.path.join(data_dir, f'{symbol}.csv')
    if not os.path.exists(filepath):
        return None

    df = pd.read_csv(filepath, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)

    if len(df) < 250:
        return None

    df['RSI'] = calculate_rsi(df['Close'], config.rsi_period)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    df['High_10d'] = df['High'].rolling(10).max()
    df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100
    df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100
    df['Uptrend'] = (df['Close'] > df['MA50']) & (df['MA50'] > df['MA200'])

    df['Entry_Signal'] = (
        (df['RSI'] < config.rsi_threshold) &
        (df['Uptrend']) &
        (df['Pullback_pct'] >= config.pullback_min) &
        (df['Pullback_pct'] <= config.pullback_max) &
        (df['MA20_distance'] <= config.ma20_distance)
    )

    return df

def run_backtest(config: BacktestConfig, start_date: str, end_date: str):
    """Run backtest with given configuration"""

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'

    universe = {}
    for file in os.listdir(data_dir):
        if file.endswith('.csv'):
            symbol = file.replace('.csv', '')
            df = prepare_data(symbol, config, data_dir)
            if df is not None:
                df = df[(df.index >= start_date) & (df.index <= end_date)]
                if len(df) > 100:
                    universe[symbol] = df

    trades = []
    open_positions = {}
    capital = config.initial_capital

    all_dates = set()
    for df in universe.values():
        all_dates.update(df.index)
    all_dates = sorted(list(all_dates))

    for date in all_dates:
        closed_symbols = []
        for symbol, (entry_date, entry_price, shares, rsi_entry) in open_positions.items():
            if date not in universe[symbol].index:
                continue

            current_price = universe[symbol].loc[date, 'Close']
            days_held = (date - entry_date).days
            pnl_pct = (current_price - entry_price) / entry_price

            exit = False
            exit_reason = ""

            if pnl_pct >= config.profit_target_pct:
                exit = True
                exit_reason = "profit_target"
            elif pnl_pct <= -config.stop_loss_pct:
                exit = True
                exit_reason = "stop_loss"
            elif days_held >= config.max_hold_days:
                exit = True
                exit_reason = "max_hold"

            if exit:
                exit_price = current_price * (1 - config.slippage_pct)
                pnl = shares * (exit_price - entry_price) - config.commission_per_trade * 2

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

        if len(open_positions) < config.max_positions:
            candidates = []

            for symbol, df in universe.items():
                if symbol in open_positions or date not in df.index:
                    continue

                if df.loc[date, 'Entry_Signal']:
                    rsi = df.loc[date, 'RSI']
                    price = df.loc[date, 'Close']
                    candidates.append((symbol, rsi, price))

            candidates.sort(key=lambda x: x[1])

            for i in range(min(len(candidates), config.max_positions - len(open_positions))):
                symbol, rsi, price = candidates[i]
                entry_price = price * (1 + config.slippage_pct)
                position_size = capital * config.position_size_pct
                shares = int(position_size / entry_price)

                if shares > 0 and shares * entry_price <= capital * 0.95:
                    open_positions[symbol] = (date, entry_price, shares, rsi)
                    capital -= shares * entry_price + config.commission_per_trade

    return trades, capital, len(universe)

def summarize_results(config: BacktestConfig, trades: List[Trade], final_capital: float, num_stocks: int):
    """Print summary statistics"""

    if not trades:
        return {
            'name': config.name,
            'trades': 0,
            'win_rate': 0,
            'total_return': -100,
            'avg_trade': 0,
            'sharpe': 0,
            'max_dd': 0,
            'trades_per_month': 0
        }

    df = pd.DataFrame([{
        'pnl': t.pnl,
        'pnl_pct': t.pnl_pct * 100,
        'exit_date': t.exit_date,
        'entry_date': t.entry_date,
        'days_held': (t.exit_date - t.entry_date).days
    } for t in trades])

    winners = df[df['pnl'] > 0]
    win_rate = len(winners) / len(df) * 100
    total_return = (final_capital / config.initial_capital - 1) * 100

    cumulative = (df.sort_values('exit_date')['pnl'].cumsum() + config.initial_capital)
    max_dd = ((cumulative - cumulative.expanding().max()) / cumulative.expanding().max()).min() * 100

    sharpe = 0
    if df['pnl_pct'].std() > 0:
        sharpe = (df['pnl_pct'].mean() / df['pnl_pct'].std()) * np.sqrt(252 / df['days_held'].mean())

    days = (df['exit_date'].max() - df['entry_date'].min()).days
    trades_per_month = len(df) / (days / 30) if days > 0 else 0

    return {
        'name': config.name,
        'trades': len(df),
        'win_rate': win_rate,
        'total_return': total_return,
        'avg_trade': df['pnl_pct'].mean(),
        'sharpe': sharpe,
        'max_dd': max_dd,
        'trades_per_month': trades_per_month,
        'num_stocks': num_stocks
    }

def main():
    print("="*80)
    print("MEAN REVERSION STRATEGY COMPARISON")
    print("Testing different parameter sets with FIXED RSI calculation")
    print("="*80)

    configs = [
        BacktestConfig(
            name="Original (RSI2<30)",
            rsi_period=2,
            rsi_threshold=30,
            pullback_min=3,
            pullback_max=6,
            ma20_distance=1.5
        ),
        BacktestConfig(
            name="Relaxed RSI (RSI2<40)",
            rsi_period=2,
            rsi_threshold=40,
            pullback_min=3,
            pullback_max=6,
            ma20_distance=1.5
        ),
        BacktestConfig(
            name="RSI5 Conservative",
            rsi_period=5,
            rsi_threshold=30,
            pullback_min=2,
            pullback_max=8,
            ma20_distance=2.5
        ),
        BacktestConfig(
            name="RSI5 Aggressive",
            rsi_period=5,
            rsi_threshold=40,
            pullback_min=2,
            pullback_max=10,
            ma20_distance=3.0
        ),
        BacktestConfig(
            name="RSI14 Standard",
            rsi_period=14,
            rsi_threshold=35,
            pullback_min=2,
            pullback_max=10,
            ma20_distance=3.0
        ),
    ]

    results = []

    for config in configs:
        print(f"\nTesting: {config.name}...")
        trades, final, num_stocks = run_backtest(config, '2022-01-01', '2026-02-01')
        summary = summarize_results(config, trades, final, num_stocks)
        results.append(summary)

    # Display comparison table
    print("\n" + "="*80)
    print("RESULTS COMPARISON")
    print("="*80)

    results_df = pd.DataFrame(results)

    print("\nStrategy Performance Summary:")
    print("-" * 80)
    print(f"{'Strategy':<25} {'Trades':>8} {'Win%':>8} {'Return%':>10} {'Avg Trade%':>12} {'Sharpe':>8}")
    print("-" * 80)

    for _, row in results_df.iterrows():
        print(f"{row['name']:<25} {row['trades']:>8.0f} {row['win_rate']:>7.1f}% {row['total_return']:>9.1f}% {row['avg_trade']:>11.2f}% {row['sharpe']:>8.2f}")

    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)

    best = results_df.loc[results_df['total_return'].idxmax()]

    print(f"\n1. Best Performing Strategy: {best['name']}")
    print(f"   - Total Return: {best['total_return']:.1f}%")
    print(f"   - Win Rate: {best['win_rate']:.1f}%")
    print(f"   - Number of Trades: {best['trades']:.0f}")

    print(f"\n2. Original Strategy (RSI2<30) Performance:")
    orig = results_df[results_df['name'] == 'Original (RSI2<30)'].iloc[0]
    print(f"   - Return: {orig['total_return']:.1f}%")
    print(f"   - Win Rate: {orig['win_rate']:.1f}%")
    print(f"   - VERDICT: {'VIABLE' if orig['total_return'] > 10 else 'NOT VIABLE'}")

    print("\n3. Parameter Impact:")
    print("   - Increasing RSI threshold (30→40):", end=" ")
    rsi2_30 = results_df[results_df['name'] == 'Original (RSI2<30)'].iloc[0]
    rsi2_40 = results_df[results_df['name'] == 'Relaxed RSI (RSI2<40)'].iloc[0]
    print(f"{rsi2_40['trades']/max(1, rsi2_30['trades']):.1f}x more trades, {rsi2_40['total_return']-rsi2_30['total_return']:+.1f}% return diff")

    print("   - Switching RSI2→RSI5:", end=" ")
    rsi5 = results_df[results_df['name'] == 'RSI5 Conservative'].iloc[0]
    print(f"{rsi5['win_rate']:.1f}% win rate")

    print("   - Using RSI14 (traditional):", end=" ")
    rsi14 = results_df[results_df['name'] == 'RSI14 Standard'].iloc[0]
    print(f"{rsi14['trades']:.0f} trades, {rsi14['total_return']:.1f}% return")

    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)

    if best['total_return'] > 20 and best['win_rate'] > 55:
        print(f"\n✓ RECOMMENDED: Use the '{best['name']}' configuration")
        print("  - Shows strong returns with acceptable win rate")
        print("  - Consider paper trading this variant")
    elif best['total_return'] > 0:
        print(f"\n⚠ CAUTION: '{best['name']}' shows positive but modest returns")
        print("  - Test in paper trading before risking capital")
        print("  - May need further optimization")
    else:
        print("\n✗ NO VIABLE CONFIGURATION FOUND")
        print("  - Mean reversion with these parameters doesn't work on this data")
        print("  - Consider alternative strategies:")
        print("    • Momentum/trend following")
        print("    • Different asset classes (options, futures)")
        print("    • Pairs trading")

if __name__ == "__main__":
    main()
