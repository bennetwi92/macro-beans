"""
Test mean reversion strategy with PROPER position sizing
Strategy has edge (52% win rate, +1.24% avg) but 20% positions destroy capital
Test with 5%, 10%, and 15% position sizes
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

def calculate_rsi(prices: pd.Series, period: int) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data(symbol: str, data_dir: str) -> pd.DataFrame:
    filepath = os.path.join(data_dir, f'{symbol}.csv')
    if not os.path.exists(filepath):
        return None

    df = pd.read_csv(filepath, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)

    if len(df) < 250:
        return None

    df['RSI_2'] = calculate_rsi(df['Close'], 2)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    df['High_10d'] = df['High'].rolling(10).max()
    df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100
    df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100
    df['Uptrend'] = (df['Close'] > df['MA50']) & (df['MA50'] > df['MA200'])

    df['Entry_Signal'] = (
        (df['RSI_2'] < 30) &
        (df['Uptrend']) &
        (df['Pullback_pct'] >= 3) &
        (df['Pullback_pct'] <= 6) &
        (df['MA20_distance'] <= 1.5)
    )

    return df

def backtest_with_position_size(symbols, data_dir, start_date, end_date,
                                position_size_pct, max_positions,
                                stop_pct, target_pct):
    """Backtest with configurable position sizing"""

    universe = {}
    for symbol in symbols:
        df = prepare_data(symbol, data_dir)
        if df is not None:
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(df) > 100:
                universe[symbol] = df

    trades = []
    open_positions = {}
    capital = 10000

    all_dates = set()
    for df in universe.values():
        all_dates.update(df.index)
    all_dates = sorted(list(all_dates))

    for date in all_dates:
        # Check exits
        closed_symbols = []
        for symbol, (entry_date, entry_price, shares, rsi) in open_positions.items():
            if date not in universe[symbol].index:
                continue

            current_price = universe[symbol].loc[date, 'Close']
            days_held = (date - entry_date).days
            pnl_pct = (current_price - entry_price) / entry_price

            exit = False
            exit_reason = ""

            if pnl_pct >= target_pct:
                exit = True
                exit_reason = "profit_target"
            elif pnl_pct <= -stop_pct:
                exit = True
                exit_reason = "stop_loss"
            elif days_held >= 5:
                exit = True
                exit_reason = "max_hold"

            if exit:
                exit_price = current_price * 0.999
                pnl = shares * (exit_price - entry_price) - 2
                capital += pnl

                trades.append({
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': date,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'days': days_held
                })

                closed_symbols.append(symbol)

        for symbol in closed_symbols:
            del open_positions[symbol]

        # Check for new entries
        if len(open_positions) < max_positions and capital > 100:
            candidates = []

            for symbol, df in universe.items():
                if symbol in open_positions or date not in df.index:
                    continue

                if df.loc[date, 'Entry_Signal']:
                    rsi = df.loc[date, 'RSI_2']
                    price = df.loc[date, 'Close']
                    candidates.append((symbol, rsi, price))

            candidates.sort(key=lambda x: x[1])

            for i in range(min(len(candidates), max_positions - len(open_positions))):
                symbol, rsi, price = candidates[i]
                entry_price = price * 1.001
                position_size = capital * position_size_pct
                shares = int(position_size / entry_price)

                if shares > 0 and shares * entry_price <= capital * 0.95:
                    open_positions[symbol] = (date, entry_price, shares, rsi)
                    capital -= shares * entry_price + 1

    return trades, capital

def analyze_results(config_name, trades, initial_capital, final_capital):
    """Analyze backtest results"""

    if not trades:
        return {
            'config': config_name,
            'trades': 0,
            'win_rate': 0,
            'return': -100,
            'final_capital': 0
        }

    df = pd.DataFrame(trades)
    winners = df[df['pnl'] > 0]
    win_rate = len(winners) / len(df) * 100
    total_return = (final_capital / initial_capital - 1) * 100

    return {
        'config': config_name,
        'trades': len(df),
        'win_rate': win_rate,
        'avg_trade_pct': df['pnl_pct'].mean(),
        'avg_winner': winners['pnl_pct'].mean() if len(winners) > 0 else 0,
        'avg_loser': df[df['pnl'] <= 0]['pnl_pct'].mean() if len(df[df['pnl'] <= 0]) > 0 else 0,
        'return': total_return,
        'final_capital': final_capital,
        'total_pnl': final_capital - initial_capital
    }

def main():
    """Test different position sizing strategies"""

    print("="*80)
    print("POSITION SIZING OPTIMIZATION")
    print("Mean Reversion Strategy on Mega-Cap Tech")
    print("="*80)

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    start_date = '2022-01-01'
    end_date = '2026-02-01'

    # Test configurations
    configs = [
        # (name, position_size_pct, max_positions, stop_pct, target_pct)
        ("Original (20% pos, 5 max)", 0.20, 5, 0.03, 0.03),
        ("Conservative (5% pos, 3 max)", 0.05, 3, 0.03, 0.03),
        ("Moderate (10% pos, 3 max)", 0.10, 3, 0.03, 0.03),
        ("Balanced (10% pos, 5 max)", 0.10, 5, 0.03, 0.03),
        ("Tight stops (10% pos, -2%/+3%)", 0.10, 3, 0.02, 0.03),
        ("Wide targets (10% pos, -3%/+5%)", 0.10, 3, 0.03, 0.05),
        ("Asymmetric (10% pos, -2%/+5%)", 0.10, 3, 0.02, 0.05),
    ]

    results = []

    for config_name, pos_size, max_pos, stop, target in configs:
        print(f"\nTesting: {config_name}...")
        trades, final = backtest_with_position_size(
            symbols, data_dir, start_date, end_date,
            pos_size, max_pos, stop, target
        )
        result = analyze_results(config_name, trades, 10000, final)
        results.append(result)

    # Display results
    print("\n" + "="*80)
    print("RESULTS COMPARISON")
    print("="*80)

    df_results = pd.DataFrame(results)

    print(f"\n{'Configuration':<35} {'Trades':>7} {'Win%':>7} {'Return':>10} {'Final $':>10}")
    print("-" * 80)

    for _, row in df_results.iterrows():
        print(f"{row['config']:<35} {row['trades']:>7.0f} {row['win_rate']:>6.1f}% "
              f"{row['return']:>9.1f}% ${row['final_capital']:>9,.0f}")

    # Find best
    best = df_results.loc[df_results['return'].idxmax()]

    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)

    print(f"\nBest Configuration: {best['config']}")
    print(f"  Final Capital: ${best['final_capital']:,.0f}")
    print(f"  Total Return: {best['return']:+.1f}%")
    print(f"  Win Rate: {best['win_rate']:.1f}%")
    print(f"  Total Trades: {best['trades']:.0f}")

    # Compare to original
    original = df_results[df_results['config'].str.contains('Original')].iloc[0]
    improvement = best['return'] - original['return']

    print(f"\nImprovement vs Original:")
    print(f"  Original return: {original['return']:+.1f}%")
    print(f"  Best return: {best['return']:+.1f}%")
    print(f"  Improvement: {improvement:+.1f} percentage points")

    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)

    if best['return'] > 20:
        print(f"\n✓ VIABLE STRATEGY FOUND!")
        print(f"  Use configuration: {best['config']}")
        print(f"  Expected return: ~{best['return']/4:.1f}% per year")
        print(f"  Next steps:")
        print(f"    1. Paper trade this configuration for 3 months")
        print(f"    2. Track actual vs expected performance")
        print(f"    3. If validated, deploy with 50% of intended capital")
    elif best['return'] > 0:
        print(f"\n⚠ MARGINAL STRATEGY")
        print(f"  Best config barely profitable: {best['return']:+.1f}%")
        print(f"  This is {best['return']/4:.1f}% per year over 4 years")
        print(f"  May not be worth the effort vs index fund")
    else:
        print(f"\n✗ NO PROFITABLE CONFIGURATION FOUND")
        print(f"  Best config still loses {best['return']:.1f}%")
        print(f"  The edge exists (good trade stats) but:")
        print(f"    • 2022 bear market destroyed all configurations")
        print(f"    • May need regime filters (only trade in bull markets)")
        print(f"    • Consider testing on different time periods")

    # Show month-by-month to see if there's regime dependency
    print("\nTime Period Sensitivity:")
    print("  Testing best config on different periods...")

    periods = [
        ('2022 (Bear)', '2022-01-01', '2022-12-31'),
        ('2023 (Recovery)', '2023-01-01', '2023-12-31'),
        ('2024-2025', '2024-01-01', '2025-12-31'),
    ]

    for period_name, start, end in periods:
        trades, final = backtest_with_position_size(
            symbols, data_dir, start, end,
            best['final_capital'] / 10000 * 0.10,  # Use best config's pos size
            3,  # max positions
            0.03, 0.03
        )
        if trades:
            ret = (final / 10000 - 1) * 100
            wr = len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100
            print(f"    {period_name}: {len(trades)} trades, {wr:.0f}% win rate, {ret:+.1f}% return")
        else:
            print(f"    {period_name}: No trades")

if __name__ == "__main__":
    main()
