"""
Test mean reversion vs momentum on mega-cap liquid tech stocks
If mean reversion loses 99%, try the OPPOSITE (momentum/trend following)

Focus: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
import os
import warnings
warnings.filterwarnings('ignore')

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
    indicator_value: float

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
    """Load and prepare data with indicators"""
    filepath = os.path.join(data_dir, f'{symbol}.csv')
    if not os.path.exists(filepath):
        return None

    df = pd.read_csv(filepath, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(None)

    if len(df) < 250:
        return None

    # Calculate all indicators we might need
    df['RSI_2'] = calculate_rsi(df['Close'], 2)
    df['RSI_5'] = calculate_rsi(df['Close'], 5)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    df['High_10d'] = df['High'].rolling(10).max()
    df['High_20d'] = df['High'].rolling(20).max()
    df['Pullback_pct'] = ((df['High_10d'] - df['Close']) / df['High_10d']) * 100
    df['Distance_to_High'] = ((df['High_20d'] - df['Close']) / df['Close']) * 100
    df['MA20_distance'] = abs((df['Close'] - df['MA20']) / df['MA20']) * 100

    # Trend indicators
    df['Uptrend'] = (df['Close'] > df['MA50']) & (df['MA50'] > df['MA200'])
    df['Strong_Uptrend'] = (df['Close'] > df['MA20']) & (df['MA20'] > df['MA50']) & (df['MA50'] > df['MA200'])

    # Distance above MA50 (for momentum)
    df['Above_MA50_pct'] = ((df['Close'] - df['MA50']) / df['MA50']) * 100

    return df

def backtest_mean_reversion(symbols: List[str], data_dir: str, start_date: str, end_date: str) -> Tuple[List[Trade], float]:
    """
    MEAN REVERSION STRATEGY (Original failing strategy)
    Entry: RSI(2) < 30, in uptrend, 3-6% pullback, near MA20
    Exit: +3% profit OR -3% stop OR 5 days
    """

    universe = {}
    for symbol in symbols:
        df = prepare_data(symbol, data_dir)
        if df is not None:
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(df) > 100:
                # Mean reversion entry signal
                df['Entry_Signal'] = (
                    (df['RSI_2'] < 30) &
                    (df['Uptrend']) &
                    (df['Pullback_pct'] >= 3) &
                    (df['Pullback_pct'] <= 6) &
                    (df['MA20_distance'] <= 1.5)
                )
                universe[symbol] = df

    return run_backtest(universe, "mean_reversion", 10000, stop_pct=0.03, target_pct=0.03, max_days=5)

def backtest_momentum(symbols: List[str], data_dir: str, start_date: str, end_date: str) -> Tuple[List[Trade], float]:
    """
    MOMENTUM STRATEGY (Inverse of mean reversion)
    Entry: RSI(2) > 70, in strong uptrend, near 20-day highs, above MAs
    Exit: +3% profit OR -3% stop OR 5 days

    This is the OPPOSITE of the mean reversion strategy:
    - Instead of buying oversold (RSI<30), buy overbought (RSI>70)
    - Instead of buying pullbacks, buy strength (near highs)
    - Instead of buying near MA20 support, buy when above MAs
    """

    universe = {}
    for symbol in symbols:
        df = prepare_data(symbol, data_dir)
        if df is not None:
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(df) > 100:
                # Momentum entry signal (INVERSE of mean reversion)
                df['Entry_Signal'] = (
                    (df['RSI_2'] > 70) &  # Overbought instead of oversold
                    (df['Strong_Uptrend']) &  # Strong uptrend
                    (df['Distance_to_High'] <= 3) &  # Near 20-day highs (not pullback)
                    (df['Above_MA50_pct'] >= 2)  # Well above MA50 (not near support)
                )
                universe[symbol] = df

    return run_backtest(universe, "momentum", 10000, stop_pct=0.03, target_pct=0.03, max_days=5)

def backtest_breakout(symbols: List[str], data_dir: str, start_date: str, end_date: str) -> Tuple[List[Trade], float]:
    """
    BREAKOUT STRATEGY (Alternative momentum approach)
    Entry: Price breaks above 20-day high, strong uptrend, RSI 50-80
    Exit: +3% profit OR -3% stop OR 5 days
    """

    universe = {}
    for symbol in symbols:
        df = prepare_data(symbol, data_dir)
        if df is not None:
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(df) > 100:
                # Breakout signal
                df['New_High'] = df['Close'] >= df['High_20d'].shift(1) * 0.995  # Within 0.5% of new high
                df['Entry_Signal'] = (
                    (df['New_High']) &
                    (df['Strong_Uptrend']) &
                    (df['RSI_5'] > 50) &  # Not oversold
                    (df['RSI_5'] < 80)  # Not extremely overbought
                )
                universe[symbol] = df

    return run_backtest(universe, "breakout", 10000, stop_pct=0.03, target_pct=0.03, max_days=5)

def run_backtest(universe: dict, strategy_name: str, initial_capital: float,
                 stop_pct: float, target_pct: float, max_days: int) -> Tuple[List[Trade], float]:
    """Generic backtesting engine"""

    trades = []
    open_positions = {}
    capital = initial_capital
    max_positions = 5
    position_size_pct = 0.20

    all_dates = set()
    for df in universe.values():
        all_dates.update(df.index)
    all_dates = sorted(list(all_dates))

    for date in all_dates:
        # Check exits
        closed_symbols = []
        for symbol, (entry_date, entry_price, shares, indicator) in open_positions.items():
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
                exit_price = current_price * 0.999  # Slippage
                pnl = shares * (exit_price - entry_price) - 2  # Commission

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
                    indicator_value=indicator
                ))

                capital += pnl
                closed_symbols.append(symbol)

        for symbol in closed_symbols:
            del open_positions[symbol]

        # Check for new entries
        if len(open_positions) < max_positions:
            candidates = []

            for symbol, df in universe.items():
                if symbol in open_positions or date not in df.index:
                    continue

                if df.loc[date, 'Entry_Signal']:
                    indicator = df.loc[date, 'RSI_2'] if 'RSI_2' in df.columns else df.loc[date, 'RSI_5']
                    price = df.loc[date, 'Close']
                    candidates.append((symbol, indicator, price))

            # Sort by indicator (lowest RSI for mean reversion, highest for momentum)
            if strategy_name == "mean_reversion":
                candidates.sort(key=lambda x: x[1])  # Lowest RSI first
            else:
                candidates.sort(key=lambda x: -x[1])  # Highest RSI first (for momentum)

            for i in range(min(len(candidates), max_positions - len(open_positions))):
                symbol, indicator, price = candidates[i]
                entry_price = price * 1.001  # Slippage
                position_size = capital * position_size_pct
                shares = int(position_size / entry_price)

                if shares > 0 and shares * entry_price <= capital * 0.95:
                    open_positions[symbol] = (date, entry_price, shares, indicator)
                    capital -= shares * entry_price + 1  # Commission

    return trades, capital

def analyze_strategy(name: str, trades: List[Trade], initial_capital: float, final_capital: float):
    """Print strategy results"""

    print(f"\n{'='*80}")
    print(f"{name.upper()} STRATEGY RESULTS")
    print(f"{'='*80}")

    if not trades:
        print("\nNo trades executed.")
        return {
            'name': name,
            'trades': 0,
            'win_rate': 0,
            'return': -100,
            'avg_trade': 0,
            'profit_factor': 0,
            'sharpe': 0
        }

    df = pd.DataFrame([{
        'symbol': t.symbol,
        'entry_date': t.entry_date,
        'exit_date': t.exit_date,
        'pnl': t.pnl,
        'pnl_pct': t.pnl_pct * 100,
        'exit_reason': t.exit_reason,
        'indicator': t.indicator_value,
        'days': (t.exit_date - t.entry_date).days
    } for t in trades])

    winners = df[df['pnl'] > 0]
    losers = df[df['pnl'] <= 0]
    win_rate = len(winners) / len(df) * 100
    total_return = (final_capital / initial_capital - 1) * 100

    print(f"\nBasic Stats:")
    print(f"  Total Trades: {len(df)}")
    print(f"  Winners: {len(winners)} ({win_rate:.1f}%)")
    print(f"  Losers: {len(losers)} ({100-win_rate:.1f}%)")

    print(f"\nReturns:")
    print(f"  Initial Capital: ${initial_capital:,.0f}")
    print(f"  Final Capital: ${final_capital:,.0f}")
    print(f"  Total Return: {total_return:+.1f}%")
    print(f"  Average Trade: {df['pnl_pct'].mean():+.2f}%")

    if len(winners) > 0:
        print(f"  Average Winner: {winners['pnl_pct'].mean():+.2f}%")
    if len(losers) > 0:
        print(f"  Average Loser: {losers['pnl_pct'].mean():+.2f}%")

    # Profit factor
    profit_factor = 0
    if len(losers) > 0 and losers['pnl'].sum() != 0:
        profit_factor = abs(winners['pnl'].sum() / losers['pnl'].sum())
        print(f"  Profit Factor: {profit_factor:.2f}")

    # Sharpe
    sharpe = 0
    if df['pnl_pct'].std() > 0:
        sharpe = (df['pnl_pct'].mean() / df['pnl_pct'].std()) * np.sqrt(252 / df['days'].mean())
        print(f"  Sharpe Ratio: {sharpe:.2f}")

    # Trade distribution by stock
    print(f"\nTrades by Stock:")
    stock_counts = df['symbol'].value_counts()
    for symbol, count in stock_counts.items():
        stock_trades = df[df['symbol'] == symbol]
        stock_win_rate = len(stock_trades[stock_trades['pnl'] > 0]) / len(stock_trades) * 100
        stock_pnl = stock_trades['pnl'].sum()
        print(f"  {symbol}: {count} trades, {stock_win_rate:.0f}% win rate, ${stock_pnl:+.0f} total P&L")

    # Exit reasons
    print(f"\nExit Reasons:")
    for reason in df['exit_reason'].unique():
        count = len(df[df['exit_reason'] == reason])
        avg_pnl = df[df['exit_reason'] == reason]['pnl_pct'].mean()
        print(f"  {reason}: {count} trades ({count/len(df)*100:.0f}%), {avg_pnl:+.2f}% avg")

    # Sample trades
    print(f"\nSample Trades (first 10):")
    for _, t in df.head(10).iterrows():
        result = "WIN" if t['pnl'] > 0 else "LOSS"
        print(f"  {t['symbol']}: {t['entry_date'].date()} -> {t['exit_date'].date()} "
              f"({t['days']}d) {t['pnl_pct']:+.1f}% [{result}]")

    return {
        'name': name,
        'trades': len(df),
        'win_rate': win_rate,
        'return': total_return,
        'avg_trade': df['pnl_pct'].mean(),
        'profit_factor': profit_factor,
        'sharpe': sharpe,
        'final_capital': final_capital
    }

def main():
    """Compare mean reversion vs momentum on mega-cap tech"""

    print("="*80)
    print("MEGA-CAP TECH: MEAN REVERSION vs MOMENTUM")
    print("Testing on: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA")
    print("="*80)

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    # Check which symbols have data
    available = [s for s in symbols if os.path.exists(os.path.join(data_dir, f'{s}.csv'))]
    print(f"\nAvailable symbols: {', '.join(available)}")

    start_date = '2022-01-01'
    end_date = '2026-02-01'

    # Test all three strategies
    print(f"\n{'='*80}")
    print("RUNNING BACKTESTS...")
    print(f"{'='*80}")

    print("\n1. Testing MEAN REVERSION (buy weakness)...")
    mr_trades, mr_capital = backtest_mean_reversion(available, data_dir, start_date, end_date)
    mr_results = analyze_strategy("Mean Reversion", mr_trades, 10000, mr_capital)

    print("\n2. Testing MOMENTUM (buy strength - INVERSE)...")
    mom_trades, mom_capital = backtest_momentum(available, data_dir, start_date, end_date)
    mom_results = analyze_strategy("Momentum", mom_trades, 10000, mom_capital)

    print("\n3. Testing BREAKOUT (buy new highs)...")
    bo_trades, bo_capital = backtest_breakout(available, data_dir, start_date, end_date)
    bo_results = analyze_strategy("Breakout", bo_trades, 10000, bo_capital)

    # Comparison
    print("\n" + "="*80)
    print("STRATEGY COMPARISON")
    print("="*80)

    results_df = pd.DataFrame([mr_results, mom_results, bo_results])

    print(f"\n{'Strategy':<20} {'Trades':>8} {'Win%':>8} {'Return%':>10} {'Avg Trade%':>12} {'Sharpe':>8}")
    print("-" * 80)
    for _, row in results_df.iterrows():
        print(f"{row['name']:<20} {row['trades']:>8.0f} {row['win_rate']:>7.1f}% {row['return']:>9.1f}% {row['avg_trade']:>11.2f}% {row['sharpe']:>8.2f}")

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)

    best = results_df.loc[results_df['return'].idxmax()]

    if best['return'] > 10:
        print(f"\n✓ WINNER: {best['name']} strategy")
        print(f"  Return: {best['return']:+.1f}%")
        print(f"  Win Rate: {best['win_rate']:.1f}%")
        print(f"  {best['trades']:.0f} trades with Sharpe {best['sharpe']:.2f}")
        print(f"\n  The INVERSE approach works! The market is trending, not mean reverting.")
    elif best['return'] > 0:
        print(f"\n⚠ {best['name']} shows modest positive returns ({best['return']:+.1f}%)")
        print(f"  Consider paper trading before deploying capital")
    else:
        print(f"\n✗ All strategies fail on mega-cap tech during this period")
        print(f"  Best: {best['name']} with {best['return']:+.1f}% return")
        print(f"\n  Possible reasons:")
        print(f"    • 2022 was a severe bear market (strategies may work in other regimes)")
        print(f"    • Time period includes major volatility")
        print(f"    • May need longer holding periods or different exit rules")

    print(f"\n  Mean Reversion Return: {mr_results['return']:+.1f}%")
    print(f"  Momentum Return: {mom_results['return']:+.1f}%")
    improvement = mom_results['return'] - mr_results['return']
    print(f"  Improvement from inverting: {improvement:+.1f} percentage points")

if __name__ == "__main__":
    main()
