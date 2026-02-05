"""
Mean reversion backtest with CORRECT slippage: $0.05 per share (not 0.1%)
For mega-cap liquid tech, $0.05/share is realistic
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

def backtest_with_flat_slippage(symbols, data_dir, start_date, end_date,
                                position_size_pct, max_positions,
                                stop_pct, target_pct,
                                slippage_per_share=0.05, commission=1.0):
    """Backtest with $X per share slippage (realistic for liquid stocks)"""

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
                # Apply flat slippage per share
                exit_price = current_price - slippage_per_share
                pnl = shares * (exit_price - entry_price) - commission * 2  # Round trip commission

                trades.append({
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'shares': shares,
                    'pnl': pnl,
                    'pnl_pct': ((exit_price - entry_price) / entry_price) * 100,
                    'exit_reason': exit_reason,
                    'days': days_held,
                    'slippage_cost': shares * slippage_per_share * 2,  # Round trip
                    'commission_cost': commission * 2
                })

                capital += pnl
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

                # Apply flat slippage per share on entry
                entry_price = price + slippage_per_share
                position_size = capital * position_size_pct
                shares = int(position_size / entry_price)

                if shares > 0 and shares * entry_price <= capital * 0.95:
                    open_positions[symbol] = (date, entry_price, shares, rsi)
                    capital -= shares * entry_price + commission

    return trades, capital

def analyze_results(config_name, trades, initial_capital, final_capital):
    """Analyze backtest results with cost breakdown"""

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

    # Cost analysis
    total_slippage = df['slippage_cost'].sum()
    total_commission = df['commission_cost'].sum()
    gross_pnl = df['pnl'].sum() + total_slippage + total_commission

    return {
        'config': config_name,
        'trades': len(df),
        'win_rate': win_rate,
        'avg_trade_pct': df['pnl_pct'].mean(),
        'avg_winner': winners['pnl_pct'].mean() if len(winners) > 0 else 0,
        'avg_loser': df[df['pnl'] <= 0]['pnl_pct'].mean() if len(df[df['pnl'] <= 0]) > 0 else 0,
        'return': total_return,
        'final_capital': final_capital,
        'total_pnl': final_capital - initial_capital,
        'total_slippage': total_slippage,
        'total_commission': total_commission,
        'gross_pnl': gross_pnl
    }

def main():
    """Test with correct slippage assumptions"""

    print("="*80)
    print("MEAN REVERSION BACKTEST - CORRECT SLIPPAGE")
    print("Using $0.05/share slippage (realistic for liquid mega-cap tech)")
    print("="*80)

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    start_date = '2022-01-01'
    end_date = '2026-02-01'

    # Test configurations
    configs = [
        # (name, position_size_pct, max_positions, stop_pct, target_pct, slippage_per_share, commission)
        ("Original (20% pos, $0.05 slip)", 0.20, 5, 0.03, 0.03, 0.05, 1.0),
        ("Conservative (5% pos, $0.05 slip)", 0.05, 3, 0.03, 0.03, 0.05, 1.0),
        ("Moderate (10% pos, $0.05 slip)", 0.10, 3, 0.03, 0.03, 0.05, 1.0),
        ("Tight stops (10%, -2%/+3%)", 0.10, 3, 0.02, 0.03, 0.05, 1.0),
        ("Wide targets (10%, -3%/+5%)", 0.10, 3, 0.03, 0.05, 0.05, 1.0),
        ("Asymmetric (10%, -2%/+5%)", 0.10, 3, 0.02, 0.05, 0.05, 1.0),
        ("Zero commission (10% pos)", 0.10, 3, 0.03, 0.03, 0.05, 0.0),
    ]

    results = []

    for config_name, pos_size, max_pos, stop, target, slip, comm in configs:
        print(f"\nTesting: {config_name}...")
        trades, final = backtest_with_flat_slippage(
            symbols, data_dir, start_date, end_date,
            pos_size, max_pos, stop, target, slip, comm
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

    # Cost breakdown for best config
    best = df_results.loc[df_results['return'].idxmax()]

    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)

    print(f"\nBest Configuration: {best['config']}")
    print(f"  Final Capital: ${best['final_capital']:,.0f}")
    print(f"  Total Return: {best['return']:+.1f}%")
    print(f"  Win Rate: {best['win_rate']:.1f}%")
    print(f"  Total Trades: {best['trades']:.0f}")

    if best['trades'] > 0:
        print(f"\n  Cost Breakdown:")
        print(f"    Gross P&L: ${best['gross_pnl']:+,.0f}")
        print(f"    Slippage Cost: -${best['total_slippage']:,.0f}")
        print(f"    Commission Cost: -${best['total_commission']:,.0f}")
        print(f"    Net P&L: ${best['total_pnl']:+,.0f}")
        print(f"    Avg slippage per trade: ${best['total_slippage']/best['trades']:.2f}")
        print(f"    Avg commission per trade: ${best['total_commission']/best['trades']:.2f}")

    # Compare slippage impact
    original = df_results[df_results['config'].str.contains('Original')].iloc[0]
    improvement = best['return'] - original['return']

    print(f"\n  Improvement vs Original (20% positions):")
    print(f"    Original: {original['return']:+.1f}%")
    print(f"    Best: {best['return']:+.1f}%")
    print(f"    Improvement: {improvement:+.1f} percentage points")

    print("\n" + "="*80)
    print("VERDICT")
    print("="*80)

    if best['return'] > 20:
        print(f"\n✓ PROFITABLE STRATEGY")
        print(f"  Annualized return: ~{best['return']/4:.1f}% per year")
        print(f"  The reduced slippage ($0.05 vs 0.1%) made the difference!")
        print(f"\n  Next steps:")
        print(f"    1. Paper trade for 3 months to validate")
        print(f"    2. Start with 50% of intended capital")
        print(f"    3. Monitor execution quality vs backtest assumptions")
    elif best['return'] > 0:
        print(f"\n⚠ MARGINAL PROFITABILITY")
        print(f"  Return: {best['return']:+.1f}% over 4 years")
        print(f"  Annualized: ~{best['return']/4:.1f}% per year")
        print(f"  This may not beat SPY buy-and-hold")
    else:
        print(f"\n✗ STILL NOT PROFITABLE")
        print(f"  Best config: {best['return']:+.1f}% return")
        print(f"  Even with realistic $0.05 slippage, strategy fails")
        print(f"\n  Likely reasons:")
        print(f"    • 2022 bear market too severe")
        print(f"    • Mean reversion doesn't work in this environment")
        print(f"    • Need regime filters or different time period")

    # Test on just 2023-2025 (post bear market)
    print("\n" + "="*80)
    print("BULL MARKET ONLY TEST (2023-2025)")
    print("="*80)
    print("\nTesting if strategy works AFTER the 2022 bear market...")

    bull_trades, bull_final = backtest_with_flat_slippage(
        symbols, data_dir, '2023-01-01', '2026-02-01',
        0.10, 3, 0.03, 0.03, 0.05, 1.0  # Use moderate config
    )

    if bull_trades:
        bull_ret = (bull_final / 10000 - 1) * 100
        bull_wr = len([t for t in bull_trades if t['pnl'] > 0]) / len(bull_trades) * 100
        print(f"  2023-2025 Results:")
        print(f"    Return: {bull_ret:+.1f}%")
        print(f"    Win Rate: {bull_wr:.1f}%")
        print(f"    Trades: {len(bull_trades)}")

        if bull_ret > 10:
            print(f"\n  ✓ Strategy WORKS in bull markets!")
            print(f"    Consider adding regime filter: only trade when SPY > 200 MA")
        else:
            print(f"\n  ✗ Still fails even in bull market period")

if __name__ == "__main__":
    main()
