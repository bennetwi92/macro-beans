"""
Diagnose the mathematical paradox:
66.7% win rate, +$53 net P&L, yet -95% return

Track capital EXACTLY at every step to find where it's going
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

def backtest_with_detailed_tracking(symbols, data_dir, start_date, end_date):
    """Track EVERY dollar movement"""

    universe = {}
    for symbol in symbols:
        df = prepare_data(symbol, data_dir)
        if df is not None:
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(df) > 100:
                universe[symbol] = df

    trades = []
    open_positions = {}  # symbol -> (entry_date, entry_price, shares, stop_price, capital_locked)

    # CRITICAL: Track cash vs locked capital separately
    cash = 10000  # Available cash
    locked_in_positions = 0  # Capital tied up in open positions

    risk_pct = 0.005  # 0.5% risk (best from previous test)
    stop_pct = 0.03
    target_pct = 0.03
    max_positions = 5
    max_days = 5
    slippage = 0.05

    trade_num = 0

    all_dates = set()
    for df in universe.values():
        all_dates.update(df.index)
    all_dates = sorted(list(all_dates))

    print(f"{'Date':<12} {'Action':<10} {'Symbol':<7} {'$Cash':<12} {'$Locked':<12} {'$Total':<12} {'#Open':<6}")
    print("-" * 95)
    print(f"START:       {'---':<10} {'---':<7} ${cash:<11,.0f} ${locked_in_positions:<11,.0f} ${cash + locked_in_positions:<11,.0f} {len(open_positions):<6}")

    for date in all_dates:
        # EXIT trades
        for symbol, (entry_date, entry_price, shares, stop_price, capital_locked) in list(open_positions.items()):
            if date not in universe[symbol].index:
                continue

            current_price = universe[symbol].loc[date, 'Close']
            days_held = (date - entry_date).days
            pnl_pct = (current_price - entry_price) / entry_price

            exit = False
            exit_reason = ""

            if pnl_pct >= target_pct:
                exit = True
                exit_reason = "target"
            elif pnl_pct <= -stop_pct:
                exit = True
                exit_reason = "stop"
            elif days_held >= max_days:
                exit = True
                exit_reason = "time"

            if exit:
                trade_num += 1

                # Calculate P&L
                exit_price = current_price - slippage
                proceeds = shares * exit_price
                slippage_cost = shares * slippage * 2
                net_pnl = proceeds - capital_locked - slippage_cost

                # RELEASE CAPITAL
                cash += proceeds
                locked_in_positions -= capital_locked

                total_capital = cash + locked_in_positions

                result = "✓" if net_pnl > 0 else "✗"
                print(f"{date.date()!s:<12} EXIT #{trade_num:<5} {symbol:<7} ${cash:<11,.0f} ${locked_in_positions:<11,.0f} ${total_capital:<11,.0f} {len(open_positions)-1:<6} {result} ${net_pnl:+.0f}")

                trades.append({
                    'trade_num': trade_num,
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': date,
                    'capital_locked': capital_locked,
                    'proceeds': proceeds,
                    'net_pnl': net_pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': exit_reason,
                    'cash_after': cash,
                    'locked_after': locked_in_positions,
                    'total_after': total_capital
                })

                del open_positions[symbol]

        # ENTER new trades
        if len(open_positions) < max_positions and cash > 100:
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

                # Risk-based sizing
                entry_price = price + slippage
                stop_price = entry_price * (1 - stop_pct)

                total_capital = cash + locked_in_positions
                risk_amount = total_capital * risk_pct
                risk_per_share = entry_price - stop_price

                if risk_per_share <= 0:
                    continue

                shares = int(risk_amount / risk_per_share)
                capital_needed = shares * entry_price

                # Check if we have enough CASH
                if shares > 0 and capital_needed <= cash * 0.95:
                    # LOCK CAPITAL
                    cash -= capital_needed
                    locked_in_positions += capital_needed

                    open_positions[symbol] = (date, entry_price, shares, stop_price, capital_needed)

                    total_capital = cash + locked_in_positions
                    print(f"{date.date()!s:<12} ENTER      {symbol:<7} ${cash:<11,.0f} ${locked_in_positions:<11,.0f} ${total_capital:<11,.0f} {len(open_positions):<6} (${capital_needed:,.0f} locked)")

    # Final summary
    final_cash = cash
    final_locked = locked_in_positions
    final_total = final_cash + final_locked

    print("\n" + "="*80)
    print("FINAL ACCOUNTING")
    print("="*80)
    print(f"Cash Available: ${final_cash:,.0f}")
    print(f"Locked in Open Positions: ${final_locked:,.0f}")
    print(f"TOTAL CAPITAL: ${final_total:,.0f}")
    print(f"\nStarting Capital: $10,000")
    print(f"Ending Capital: ${final_total:,.0f}")
    print(f"Change: ${final_total - 10000:+,.0f} ({(final_total/10000 - 1)*100:+.1f}%)")

    if trades:
        df = pd.DataFrame(trades)
        print(f"\nTrades Executed: {len(df)}")
        print(f"Total P&L from Trades: ${df['net_pnl'].sum():+,.0f}")
        print(f"Winners: {len(df[df['net_pnl'] > 0])} ({len(df[df['net_pnl'] > 0])/len(df)*100:.1f}%)")

        print("\n" + "="*80)
        print("THE MYSTERY")
        print("="*80)
        print(f"Total P&L from trades: ${df['net_pnl'].sum():+,.0f}")
        print(f"Actual capital change: ${final_total - 10000:+,.0f}")
        print(f"Discrepancy: ${(final_total - 10000) - df['net_pnl'].sum():+,.0f}")

        if abs((final_total - 10000) - df['net_pnl'].sum()) > 10:
            print("\n⚠️  ACCOUNTING ERROR DETECTED!")
            print("Capital change doesn't match sum of trade P&L")
            print("Likely cause: Capital locked in open positions at end")
        else:
            print("\n✓ Accounting is correct")
            print("\nThe math paradox explained:")
            print("- You can have positive trade P&L...")
            print("- But if capital is locked in open positions...")
            print("- You can't access that capital for new trades!")

    return trades, final_total

def main():
    print("="*80)
    print("MATHEMATICAL PARADOX DIAGNOSIS")
    print("Tracking every dollar to understand the -95% return")
    print("="*80)
    print()

    data_dir = '/Users/williambennett/Github/macro-beans/data/stock_history'
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

    trades, final = backtest_with_detailed_tracking(
        symbols, data_dir, '2022-01-01', '2026-02-01'
    )

if __name__ == "__main__":
    main()
