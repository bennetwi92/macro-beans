"""
Figure out WHY mean reversion has good trade stats (52% win rate, +1.24% avg)
but still loses 96.6% of capital. Track capital trade-by-trade.
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
    """Load and prepare data with indicators"""
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

def backtest_with_capital_tracking(symbols, data_dir, start_date, end_date):
    """Backtest and track capital after every trade"""

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
    max_positions = 5
    position_size_pct = 0.20

    trade_num = 0

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

            if pnl_pct >= 0.03:
                exit = True
                exit_reason = "profit_target"
            elif pnl_pct <= -0.03:
                exit = True
                exit_reason = "stop_loss"
            elif days_held >= 5:
                exit = True
                exit_reason = "max_hold"

            if exit:
                exit_price = current_price * 0.999
                pnl = shares * (exit_price - entry_price) - 2
                capital_before = capital
                capital += pnl

                trade_num += 1

                trades.append({
                    'trade_num': trade_num,
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'shares': shares,
                    'position_value': shares * entry_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'rsi': rsi,
                    'days': days_held,
                    'capital_before': capital_before,
                    'capital_after': capital
                })

                closed_symbols.append(symbol)

        for symbol in closed_symbols:
            del open_positions[symbol]

        # Check for new entries
        if len(open_positions) < max_positions and capital > 100:  # Need minimum capital
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

    return pd.DataFrame(trades)

def main():
    """Diagnose why good trade stats lead to capital destruction"""

    print("="*80)
    print("CAPITAL DESTRUCTION ANALYSIS")
    print("Mean Reversion on Mega-Cap Tech (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA)")
    print("="*80)

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    df = backtest_with_capital_tracking(symbols, data_dir, '2022-01-01', '2026-02-01')

    if df.empty:
        print("\nNo trades executed!")
        return

    print(f"\nTotal Trades: {len(df)}")
    print(f"Initial Capital: $10,000")
    print(f"Final Capital: ${df.iloc[-1]['capital_after']:,.0f}")
    print(f"Total Return: {(df.iloc[-1]['capital_after']/10000 - 1)*100:+.1f}%")

    winners = df[df['pnl'] > 0]
    print(f"\nWin Rate: {len(winners)/len(df)*100:.1f}% ({len(winners)}/{len(df)} trades)")
    print(f"Average Trade: {df['pnl_pct'].mean():+.2f}%")
    print(f"Average Winner: {winners['pnl_pct'].mean():+.2f}%")
    print(f"Average Loser: {df[df['pnl'] <= 0]['pnl_pct'].mean():+.2f}%")

    # Show all trades with capital tracking
    print("\n" + "="*80)
    print("TRADE-BY-TRADE CAPITAL TRACKING")
    print("="*80)
    print(f"\n{'#':<4} {'Symbol':<6} {'Date':<12} {'Days':<5} {'P&L%':<8} {'$P&L':<10} {'CapBefore':<12} {'CapAfter':<12} {'PosSize':<10}")
    print("-" * 95)

    for _, trade in df.iterrows():
        result_icon = "✓" if trade['pnl'] > 0 else "✗"
        print(f"{trade['trade_num']:<4.0f} {trade['symbol']:<6} {trade['exit_date'].date()!s:<12} "
              f"{trade['days']:<5.0f} {trade['pnl_pct']:>+6.1f}% {trade['pnl']:>+9.0f} "
              f"${trade['capital_before']:>10,.0f} ${trade['capital_after']:>10,.0f} "
              f"${trade['position_value']:>8,.0f} {result_icon}")

    # Identify the killer trades
    print("\n" + "="*80)
    print("KEY INSIGHTS")
    print("="*80)

    # Biggest losers
    biggest_losers = df.nsmallest(5, 'pnl')
    print("\nTop 5 Biggest $ Losers:")
    for _, trade in biggest_losers.iterrows():
        print(f"  Trade #{trade['trade_num']:.0f} - {trade['symbol']}: ${trade['pnl']:,.0f} "
              f"({trade['pnl_pct']:+.1f}%) on {trade['exit_date'].date()}")
        print(f"    Position: ${trade['position_value']:,.0f}, Capital before: ${trade['capital_before']:,.0f}, after: ${trade['capital_after']:,.0f}")

    # Capital milestones
    print("\nCapital Milestones:")
    milestones = [9000, 5000, 1000, 500, 100]
    for milestone in milestones:
        below = df[df['capital_after'] < milestone]
        if not below.empty:
            first = below.iloc[0]
            print(f"  Fell below ${milestone:,}: Trade #{first['trade_num']:.0f} - {first['symbol']} on {first['exit_date'].date()}")

    # Position sizing over time
    print("\nPosition Sizing Evolution:")
    early = df.head(5)
    late = df.tail(5)
    print(f"  First 5 trades - Avg position: ${early['position_value'].mean():,.0f}")
    print(f"  Last 5 trades - Avg position: ${late['position_value'].mean():,.0f}")
    print(f"  Position size shrank by: {(1 - late['position_value'].mean()/early['position_value'].mean())*100:.1f}%")

    # Equity curve
    df['cumulative_pnl'] = df['pnl'].cumsum()
    print("\n" + "="*80)
    print("THE PROBLEM")
    print("="*80)

    print("\nThe paradox explained:")
    print("1. Trade statistics look good (52% win rate, +1.24% avg)")
    print("2. BUT: Capital compounds DOWN faster than it compounds UP")
    print("3. Early losses destroy the capital base")
    print("4. Later wins are on a tiny capital base")
    print("\nExample:")
    print("  - Start with $10,000")
    print("  - Lose 50% → $5,000")
    print("  - Win 50% → $7,500 (NOT back to $10,000!)")
    print("  - You need +100% to recover from -50%")

    # Calculate what win rate is needed
    avg_win = winners['pnl_pct'].mean() / 100
    avg_loss = abs(df[df['pnl'] <= 0]['pnl_pct'].mean() / 100)

    # Kelly criterion
    win_rate = len(winners) / len(df)
    required_win_rate = avg_loss / (avg_win + avg_loss)

    print(f"\nMath:")
    print(f"  Average win: +{avg_win*100:.2f}%")
    print(f"  Average loss: -{avg_loss*100:.2f}%")
    print(f"  Current win rate: {win_rate*100:.1f}%")
    print(f"  Required win rate for breakeven: {required_win_rate*100:.1f}%")
    print(f"  Shortfall: {(required_win_rate - win_rate)*100:.1f} percentage points")

    print("\n" + "="*80)
    print("SOLUTIONS")
    print("="*80)
    print("\n1. REDUCE POSITION SIZE")
    print("   - Current: 20% of capital per trade")
    print("   - Try: 5-10% per trade")
    print("   - This reduces impact of losses on capital base")

    print("\n2. TIGHTER STOPS")
    print("   - Current: -3% stop loss")
    print("   - Try: -1.5% or -2% stops")
    print("   - Reduce avg loss to match avg win better")

    print("\n3. WIDER TARGETS")
    print("   - Current: +3% profit target")
    print("   - Try: +5% or +6% targets")
    print("   - Let winners run to overcome compounding math")

    print("\n4. TRADE FREQUENCY")
    print("   - Current: 19 trades over 4 years (very few)")
    print("   - More trades = more chances to recover")
    print("   - Consider relaxing entry conditions")

if __name__ == "__main__":
    main()
