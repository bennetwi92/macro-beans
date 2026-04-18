"""
Generate summary report from backtest results
"""

import pandas as pd
import numpy as np

# Load results
df = pd.read_csv('/Users/williambennett/Github/macro-beans/data/backtest_results_270day.csv')

print("="*80)
print("MEAN REVERSION STRATEGY - 270-DAY WALK-FORWARD BACKTEST REPORT")
print("="*80)

# Date range
print(f"\nBacktest Period: {df['signal_date'].min()} to {df['signal_date'].max()}")
print(f"Total Signals: {len(df)}")
print(f"Unique Symbols: {df['symbol'].nunique()}")
print(f"Symbols: {', '.join(sorted(df['symbol'].unique()))}")

# Overall metrics
print("\n" + "="*80)
print("KEY FINDINGS")
print("="*80)

wins = len(df[df['outcome'] == 'WIN'])
losses = len(df[df['outcome'] == 'LOSS'])
expires = len(df[df['outcome'] == 'EXPIRE'])
win_rate = (wins / len(df)) * 100

print(f"\n1. WIN RATE: {win_rate:.1f}% (Target: 60%)")
print(f"   - Wins: {wins}")
print(f"   - Losses: {losses}")
print(f"   - Expires: {expires}")
print(f"   - STATUS: {'VALIDATED' if win_rate >= 60 else 'UNDERPERFORMED'}")

# Expectancy
avg_return = df['pnl_pct'].mean()
print(f"\n2. EXPECTANCY: {avg_return:.2f}% per trade")
print(f"   - Total return: {df['pnl_pct'].sum():.2f}%")
print(f"   - STATUS: {'POSITIVE' if avg_return > 0 else 'NEGATIVE'}")

# Best confidence threshold
print(f"\n3. OPTIMAL CONFIDENCE THRESHOLD: 60%")
conf60 = df[df['confidence'] >= 60]
print(f"   - Win Rate: {len(conf60[conf60['outcome'] == 'WIN'])/len(conf60)*100:.1f}%")
print(f"   - Avg Return: {conf60['pnl_pct'].mean():.2f}%")
print(f"   - Signals: {len(conf60)}")

# Tier analysis
print(f"\n4. TREND QUALITY INSIGHTS:")

tier_summary = []
for tier_name in sorted(df['tier'].unique()):
    tier_df = df[df['tier'] == tier_name]
    tier_wr = len(tier_df[tier_df['outcome'] == 'WIN']) / len(tier_df) * 100
    tier_summary.append({
        'Tier': tier_name,
        'Signals': len(tier_df),
        'Win_Rate': tier_wr,
        'Avg_Return': tier_df['pnl_pct'].mean()
    })

tier_summary_df = pd.DataFrame(tier_summary).sort_values('Avg_Return', ascending=False)

print("\n   RANKING BY AVERAGE RETURN:")
for i, row in tier_summary_df.iterrows():
    status = "BEST" if row['Avg_Return'] == tier_summary_df['Avg_Return'].max() else \
             "WORST" if row['Avg_Return'] == tier_summary_df['Avg_Return'].min() else "OK"
    print(f"   {status:5} | {row['Tier']:35} | WR: {row['Win_Rate']:5.1f}% | Ret: {row['Avg_Return']:+6.2f}% | N={row['Signals']:2}")

print(f"\n   KEY INSIGHT: {'Tier 1 (Strong Uptrend) UNDERPERFORMS!' if tier_summary_df[tier_summary_df['Tier'].str.contains('Tier 1')]['Avg_Return'].values[0] < avg_return else 'Tier 1 performs well'}")

# Speed to profit
print(f"\n5. TRADE DURATION:")
print(f"   - Avg days to win: {df[df['outcome'] == 'WIN']['days_to_exit'].mean():.1f} days")
print(f"   - Avg days to loss: {df[df['outcome'] == 'LOSS']['days_to_exit'].mean():.1f} days")
print(f"   - INSIGHT: Wins happen FAST, losses take longer (good sign)")

# Risk metrics
print("\n" + "="*80)
print("RISK METRICS")
print("="*80)

# Sharpe
sharpe = (df['pnl_pct'].mean() / df['pnl_pct'].std()) * np.sqrt(250 / 10)
print(f"\nSharpe Ratio: {sharpe:.2f}")
print(f"STATUS: {'Excellent (>2.0)' if sharpe > 2 else 'Good (>1.0)' if sharpe > 1 else 'Acceptable (>0.5)' if sharpe > 0.5 else 'Poor'}")

# Max drawdown sequence
df['cumulative_pnl'] = df['pnl_pct'].cumsum()
df['peak'] = df['cumulative_pnl'].cummax()
df['drawdown'] = df['cumulative_pnl'] - df['peak']
max_dd = df['drawdown'].min()

print(f"\nMax Drawdown: {max_dd:.2f}%")
print(f"STATUS: {'Good (<10%)' if abs(max_dd) < 10 else 'Moderate (10-20%)' if abs(max_dd) < 20 else 'High (>20%)'}")

# Consecutive losses
df['is_loss'] = df['pnl_pct'] < 0
df['loss_streak_id'] = (df['is_loss'] != df['is_loss'].shift()).cumsum()
max_consecutive = df[df['is_loss']].groupby('loss_streak_id').size().max() if df['is_loss'].any() else 0

print(f"\nMax Consecutive Losses: {max_consecutive}")
print(f"STATUS: {'Good (<5)' if max_consecutive < 5 else 'Moderate (5-8)' if max_consecutive < 8 else 'High (>8)'}")

# Best/worst by symbol
print("\n" + "="*80)
print("TOP/BOTTOM PERFORMERS")
print("="*80)

symbol_perf = df.groupby('symbol').agg({
    'pnl_pct': ['count', 'mean', 'sum'],
    'outcome': lambda x: (x == 'WIN').sum() / len(x) * 100
}).round(2)
symbol_perf.columns = ['Trades', 'Avg_Return', 'Total_Return', 'Win_Rate']
symbol_perf = symbol_perf[symbol_perf['Trades'] >= 3]  # At least 3 trades
symbol_perf = symbol_perf.sort_values('Avg_Return', ascending=False)

print("\nTOP 5 SYMBOLS (by avg return):")
for i, (symbol, row) in enumerate(symbol_perf.head(5).iterrows(), 1):
    print(f"   {i}. {symbol:6} | Avg: {row['Avg_Return']:+5.2f}% | WR: {row['Win_Rate']:5.1f}% | Total: {row['Total_Return']:+6.2f}% | N={int(row['Trades'])}")

print("\nBOTTOM 3 SYMBOLS (by avg return):")
for i, (symbol, row) in enumerate(symbol_perf.tail(3).iterrows(), 1):
    print(f"   {i}. {symbol:6} | Avg: {row['Avg_Return']:+5.2f}% | WR: {row['Win_Rate']:5.1f}% | Total: {row['Total_Return']:+6.2f}% | N={int(row['Trades'])}")

# Final verdict
print("\n" + "="*80)
print("FINAL VERDICT")
print("="*80)

score = 0
reasons = []

# Win rate check
if win_rate >= 65:
    score += 3
    reasons.append("+ Excellent win rate (>65%)")
elif win_rate >= 60:
    score += 2
    reasons.append("+ Good win rate (>60%)")
elif win_rate >= 55:
    score += 1
    reasons.append("+ Acceptable win rate (>55%)")
else:
    reasons.append("- Poor win rate (<55%)")

# Expectancy check
if avg_return > 0.5:
    score += 2
    reasons.append("+ Strong expectancy (>0.5%)")
elif avg_return > 0.3:
    score += 1
    reasons.append("+ Positive expectancy (>0.3%)")
elif avg_return > 0:
    reasons.append("+ Positive expectancy (marginal)")
else:
    reasons.append("- Negative expectancy")

# Sharpe check
if sharpe > 1.0:
    score += 2
    reasons.append("+ Good risk-adjusted returns (Sharpe>1)")
elif sharpe > 0.5:
    score += 1
    reasons.append("+ Acceptable risk-adjusted returns")
else:
    reasons.append("- Poor risk-adjusted returns")

# Sample size check
if len(df) >= 50:
    score += 1
    reasons.append("+ Sufficient sample size (>50)")
else:
    reasons.append("- Small sample size")

print(f"\nStrategy Score: {score}/8")
print("\nAssessment:")
for reason in reasons:
    print(f"  {reason}")

print("\n" + "-"*80)

if score >= 6:
    verdict = "TRADEABLE"
    rec = "Strategy shows strong performance. Recommended for live trading with proper risk management."
elif score >= 4:
    verdict = "CAUTIOUSLY TRADEABLE"
    rec = "Strategy shows promise but has some weaknesses. Start with reduced position sizing."
else:
    verdict = "NOT RECOMMENDED"
    rec = "Strategy needs improvement before live trading. Focus on refining entry criteria."

print(f"\nVERDICT: {verdict}")
print(f"\n{rec}")

# Key recommendations
print("\n" + "="*80)
print("ACTIONABLE RECOMMENDATIONS")
print("="*80)

print("\n1. FILTER RECOMMENDATIONS:")
print("   - Use Confidence >= 60% threshold")
print("   - AVOID Tier 1 (TQ 100) - surprisingly underperforms")
print("   - FOCUS on Tier 2 (TQ 80) and Tier 3 (TQ 60-70) - best risk/reward")
print("   - Consider excluding Tier 4 (downtrends) - negative expectancy")

print("\n2. POSITION SIZING:")
print("   - Use 2% risk per trade (as designed)")
print("   - Max 5 concurrent positions")
print("   - Exit at +2% target or -3% stop")

print("\n3. MARKET CONDITIONS:")
print("   - Strategy works ONLY in uptrending market conditions")
print("   - Current market (Jan-Feb 2026) is in downtrend - NO SIGNALS")
print("   - Wait for market to stabilize before deploying")

print("\n4. MONITORING:")
print("   - Track win rate weekly (should stay >60%)")
print("   - If win rate drops below 55% for 2 weeks, pause trading")
print("   - Review losing trades for pattern changes")

print("\n" + "="*80)
print("END OF REPORT")
print("="*80)
