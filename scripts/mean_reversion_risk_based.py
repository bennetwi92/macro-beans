"""
Mean Reversion with PROPER Risk-Based Position Sizing
Risk 1% of account per trade (not fixed % of capital)
$0 commissions (IBKR Lite), $0.05/share slippage
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

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

def prepare_data(symbol: str, data_dir: str) -> pd.DataFrame:
    """Load and prepare data"""
    filepath = os.path.join(data_dir, f'{symbol}.csv')
    if not os.path.exists(filepath):
        return None

    df = pd.read_csv(filepath, index_col=0, parse_dates=True)
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

def backtest_risk_based(symbols, data_dir, start_date, end_date,
                       risk_pct=0.01, stop_pct=0.03, target_pct=0.03,
                       max_positions=5, slippage_per_share=0.05):
    """
    Backtest with risk-based position sizing
    Position Size = (Account Balance × Risk%) / (Entry - Stop)
    """

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
    max_days = 5

    all_dates = set()
    for df in universe.values():
        all_dates.update(df.index)
    all_dates = sorted(list(all_dates))

    for date in all_dates:
        # Exit trades
        closed_symbols = []
        for symbol, (entry_date, entry_price, shares, stop_price) in open_positions.items():
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
            elif days_held >= max_days:
                exit = True
                exit_reason = "max_hold"

            if exit:
                # Apply slippage
                exit_price = current_price - slippage_per_share
                gross_pnl = shares * (exit_price - entry_price)
                slippage_cost = shares * slippage_per_share * 2  # Round trip
                net_pnl = gross_pnl - slippage_cost  # No commission!

                trades.append({
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'stop_price': stop_price,
                    'shares': shares,
                    'position_value': shares * entry_price,
                    'gross_pnl': gross_pnl,
                    'slippage_cost': slippage_cost,
                    'net_pnl': net_pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'days': days_held,
                    'capital_before': capital,
                })

                capital += net_pnl
                closed_symbols.append(symbol)

        for symbol in closed_symbols:
            del open_positions[symbol]

        # Enter new trades
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

                # Risk-based position sizing (KEY CHANGE!)
                entry_price = price + slippage_per_share
                stop_price = entry_price * (1 - stop_pct)

                risk_amount = capital * risk_pct  # Risk 1% of capital
                risk_per_share = entry_price - stop_price  # $ risk per share

                if risk_per_share <= 0:
                    continue

                shares = int(risk_amount / risk_per_share)

                # Cap at 95% of capital
                max_shares = int(capital * 0.95 / entry_price)
                shares = min(shares, max_shares)

                if shares > 0:
                    open_positions[symbol] = (date, entry_price, shares, stop_price)
                    capital -= shares * entry_price  # Lock capital

    return trades, capital

def analyze_results(name, trades, initial_capital, final_capital):
    """Analyze results"""

    if not trades:
        return {
            'name': name,
            'trades': 0,
            'win_rate': 0,
            'return': -100,
            'final': 0
        }

    df = pd.DataFrame(trades)
    winners = df[df['net_pnl'] > 0]
    win_rate = len(winners) / len(df) * 100
    total_return = (final_capital / initial_capital - 1) * 100

    total_gross = df['gross_pnl'].sum()
    total_slippage = df['slippage_cost'].sum()
    total_net = df['net_pnl'].sum()

    return {
        'name': name,
        'trades': len(df),
        'win_rate': win_rate,
        'return': total_return,
        'final': final_capital,
        'gross_pnl': total_gross,
        'slippage': total_slippage,
        'net_pnl': total_net,
        'avg_position': df['position_value'].mean()
    }

def main():
    """Test risk-based position sizing"""

    print("="*80)
    print("RISK-BASED POSITION SIZING TEST")
    print("Position Size = (Capital × 1%) / (Entry - Stop)")
    print("$0 commissions (IBKR Lite), $0.05/share slippage")
    print("="*80)

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    # Test different configurations
    configs = [
        ("Risk-Based 1% (3% stop)", 0.01, 0.03, 0.03),
        ("Risk-Based 1% (2% stop - tighter)", 0.01, 0.02, 0.03),
        ("Risk-Based 2% (3% stop - more aggressive)", 0.02, 0.03, 0.03),
        ("Risk-Based 0.5% (3% stop - conservative)", 0.005, 0.03, 0.03),
    ]

    results = []

    for name, risk, stop, target in configs:
        print(f"\nTesting: {name}...")
        trades, final = backtest_risk_based(
            symbols, data_dir, '2022-01-01', '2026-02-01',
            risk_pct=risk, stop_pct=stop, target_pct=target,
            max_positions=5, slippage_per_share=0.05
        )
        result = analyze_results(name, trades, 10000, final)
        results.append(result)

    # Display
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)

    df_results = pd.DataFrame(results)

    print(f"\n{'Configuration':<45} {'Trades':>7} {'Win%':>7} {'Return':>10} {'Avg Pos':>10}")
    print("-" * 90)

    for _, row in df_results.iterrows():
        print(f"{row['name']:<45} {row['trades']:>7.0f} {row['win_rate']:>6.1f}% "
              f"{row['return']:>9.1f}% ${row['avg_position']:>9,.0f}")

    # Best config details
    best = df_results.loc[df_results['return'].idxmax()]

    print("\n" + "="*80)
    print("BEST CONFIGURATION")
    print("="*80)

    print(f"\n{best['name']}")
    print(f"  Total Return: {best['return']:+.1f}%")
    print(f"  Final Capital: ${best['final']:,.0f}")
    print(f"  Trades: {best['trades']:.0f}")
    print(f"  Win Rate: {best['win_rate']:.1f}%")
    print(f"  Average Position Size: ${best['avg_position']:,.0f}")

    if best['trades'] > 0:
        print(f"\n  P&L Breakdown:")
        print(f"    Gross P&L: ${best['gross_pnl']:+,.0f}")
        print(f"    Slippage: -${best['slippage']:,.0f}")
        print(f"    Net P&L: ${best['net_pnl']:+,.0f}")

    print("\n" + "="*80)
    print("VERDICT")
    print("="*80)

    if best['return'] > 15:
        print(f"\n✓ PROFITABLE STRATEGY")
        print(f"  Risk-based position sizing works!")
        print(f"  Annualized return: ~{best['return']/4:.1f}% per year")
    elif best['return'] > 0:
        print(f"\n⚠ MARGINAL PROFITABILITY")
        print(f"  {best['return']:+.1f}% over 4 years (~{best['return']/4:.1f}%/year)")
        print(f"  May not beat buy-and-hold")
    else:
        print(f"\n✗ STRATEGY STILL FAILS")
        print(f"  Best return: {best['return']:+.1f}%")
        print(f"  Even with proper risk-based sizing and $0 commissions")
        print(f"\n  The mean reversion strategy doesn't work on mega-cap tech 2022-2026")
        print(f"  Time to pivot to a different approach")

if __name__ == "__main__":
    main()
