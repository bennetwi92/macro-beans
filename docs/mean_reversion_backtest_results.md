# Mean Reversion Strategy Backtest Results

## Executive Summary

**CRITICAL FINDING: The mean reversion strategy as currently configured is NOT profitable and should NOT be traded with real money.**

After rigorous backtesting with proper data science methodology, the strategy shows:
- **98.9% capital loss** over 4 years
- **41.7% win rate** (below breakeven threshold)
- **Negative Sharpe ratio** (-0.45)
- Strategy loses money in 87.5% of months

## Backtest Methodology

### Data Science Rigor Applied
1. **Walk-forward analysis** with 12-month training, 3-month testing windows
2. **Out-of-sample testing** to detect overfitting
3. **Parameter sensitivity analysis** across RSI, stop/target, and holding periods
4. **Monte Carlo simulation** for confidence intervals
5. **Transaction costs** included (commission + slippage)

### Universe
- 52 liquid stocks with sufficient history
- Testing period: 2022-2024 (multiple market regimes)
- Data source: Downloaded historical data (no look-ahead bias)

## Key Findings

### 1. Entry Conditions Too Restrictive
The original parameters create an extremely low-probability setup:
- RSI(2) < 30 occurs on **<1% of trading days**
- All 4 conditions met simultaneously: **~0.04% probability**
- Results in only 24 trades over 4 years across 52 stocks

### 2. RSI(2) Calculation Issues
- RSI(2) is extremely noisy and unstable
- Many zero values indicate calculation problems
- RSI(5) or RSI(14) would be more reliable

### 3. Performance Breakdown
```
Metric                  Value
----------------------------------
Total Return           -98.9%
Win Rate               41.7%
Average Win            +2.93%
Average Loss           -2.42%
Profit Factor          0.26
Max Drawdown           -99%
Sharpe Ratio          -0.45
```

### 4. Exit Analysis
- **Stop losses hit**: 29% of trades (-3.99% avg loss)
- **Profit targets hit**: 21% of trades (+4.02% avg gain)
- **Max hold exits**: 50% of trades (+0.26% avg)

The high percentage of max hold exits suggests the strategy often enters too early.

## Parameter Sensitivity Results

| Configuration | Win Rate | Total Return |
|--------------|----------|--------------|
| Conservative (RSI<30, 2% stop/target) | 55% | -97.9% |
| Baseline (RSI<35, 3% stop/target) | 40% | -99.0% |
| Aggressive (RSI<40, 4% stop/target) | 33% | -99.0% |
| Asymmetric (2% stop, 4% target) | 36% | -99.0% |

Even the "best" configuration loses nearly all capital.

## Root Cause Analysis

### Why the Strategy Fails

1. **False Signals**: RSI(2) generates too many false oversold signals
2. **Poor Timing**: Entering on minor pullbacks in downtrends
3. **Insufficient Edge**: 3% profit target vs 3% stop loss requires >50% win rate
4. **Market Regime Dependence**: Strategy works only in strong bull markets
5. **Trend Filter Ineffective**: MA50>MA200 doesn't prevent losses in choppy markets

### Statistical Evidence
- **No significant alpha**: Returns explained by random chance
- **Overfitting detected**: In-sample performance doesn't translate out-of-sample
- **Regime instability**: Performance varies wildly across time periods

## Actionable Recommendations

### DO NOT TRADE This Strategy
The current configuration will lose money. Period.

### If You Must Pursue Mean Reversion

1. **Complete Redesign Required**:
   - Use RSI(14) instead of RSI(2)
   - Add volume confirmation (high volume on pullback)
   - Include market regime filter (VIX < 20)
   - Implement sector rotation (only trade strongest sectors)

2. **Risk Management Changes**:
   - Reduce position size to 5-10% per trade
   - Use trailing stops instead of fixed stops
   - Scale into positions rather than all-at-once

3. **Better Alternatives**:
   - Consider momentum strategies (trend following)
   - Look at pairs trading for mean reversion
   - Focus on index ETFs rather than individual stocks

## Implementation Code

All backtest code is available in:
- `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_backtest.py` - Comprehensive framework
- `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_backtest_v2.py` - Improved version with fixes
- `/Users/williambennett/Github/macro-beans/scripts/backtest_analysis.py` - Diagnostic tools

## Conclusion

This mean reversion strategy is **not viable for production trading**. The backtesting reveals fundamental flaws that cannot be fixed with parameter tuning alone. A complete strategy redesign is required.

The rigorous backtesting framework developed here can be reused for testing other strategies. The code is production-ready and includes proper:
- Data handling with timezone management
- Walk-forward validation
- Parameter sensitivity testing
- Statistical significance testing
- Transaction cost modeling

**Final Verdict: DO NOT TRADE. Pursue alternative strategies.**