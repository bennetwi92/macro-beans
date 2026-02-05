# Mean Reversion Model: Critical Analysis Findings

## Executive Summary

**VERDICT: The current model is NOT VIABLE for production trading.**

The mean reversion model shows:
- **31.3% win rate** with 1.5x ATR targets (worse than coin flip)
- **0.5649 AUC** (barely better than random guessing)
- **SEVERE calibration issues**: 60% predicted confidence → 35% actual win rate
- **Model is massively overconfident** at higher probability thresholds

## Key Findings

### 1. ATR Target Size is TOO AGGRESSIVE

| ATR Multiplier | Win Rate | Hit Target | Hit Stop | Expired | Avg Return |
|----------------|----------|------------|----------|---------|------------|
| **0.75x**      | **56.3%** | 56.3%      | 36.7%    | 7.0%    | 0.14%      |
| 1.0x           | 46.8%    | 46.8%      | 40.6%    | 12.6%   | 0.19%      |
| 1.25x          | 38.5%    | 38.5%      | 42.8%    | 18.8%   | 0.25%      |
| **1.5x (Current)** | **31.1%** | 31.1%  | 43.9%    | 25.0%   | 0.30%      |
| 2.0x           | 19.2%    | 19.2%      | 45.1%    | 35.7%   | 0.34%      |
| 3.0x           | 7.0%     | 7.0%       | 45.7%    | 47.3%   | 0.39%      |

**Key Insight:** As targets get more aggressive:
- Win rate plummets (56% → 7%)
- Average return per trade increases slightly (0.14% → 0.39%)
- BUT: ~45% of trades hit stop loss regardless of target size
- Trade expectancy is maximized at 3.0x ATR (0.39% per trade) but with terrible win rate

**The Problem:** Setting 1.5x ATR targets creates a ~44% chance of hitting stop vs 31% chance of hitting target. You're essentially betting against yourself.

### 2. Mean Reversion DOES Work (Better Than Momentum)

| Strategy | Win Rate | Avg Trades | Avg Return |
|----------|----------|------------|------------|
| **Mean Reversion** (RSI < 30) | **54.9%** | 6 | 0.81% |
| Momentum (RSI > 70) | 48.2% | 159 | 0.23% |

**Key Insight:** Mean reversion strategy (buying oversold stocks) has:
- 6.6% higher win rate than momentum
- Higher average return per trade (0.81% vs 0.23%)
- BUT: Much fewer trading opportunities (6 vs 159 trades)

**Verdict:** You should NOT be doing the opposite. Mean reversion is the right direction, but the execution (ATR target sizing) is the problem.

### 3. Model Calibration is BROKEN

| Predicted Confidence | Actual Win Rate | Count | Error |
|---------------------|----------------|-------|-------|
| 0-50%               | 31.4%          | 3,555 | -6.8% (underconfident) |
| 50-55%              | 38.7%          | 106   | -13.4% (underconfident) |
| 55-60%              | 34.0%          | 50    | **-23.2%** |
| **60-65%**          | **38.7%**      | 31    | **-23.6%** |
| 65-70%              | 42.9%          | 14    | **-24.4%** |
| 70-75%              | 25.0%          | 4     | **-46.9%** |
| 75-80%              | 0.0%           | 4     | **-77.4%** |
| 80-100%             | 0.0%           | 1     | **-80.8%** |

**Average Calibration Error: 37.1%**

**The Critical Problem:**
- At 60% confidence threshold, actual win rate is only 35%
- Model predicts 77% confidence for trades that have 0% win rate
- This is DANGEROUS - the model is lying about its confidence

**Why This Happens:**
1. Training labels use 1.5x ATR targets (31% base success rate)
2. Model learns features that predict mean reversion
3. But labels are based on unrealistic profit targets
4. Result: Model identifies good mean reversion setups but labels them as failures

### 4. Alternative Success Definitions

| Definition | Win Rate |
|------------|----------|
| **Any Profit** (close positive) | **83.8%** |
| Fixed 2% Target | 69.6% |
| 1.0x ATR Target | 59.6% |
| 1.5x ATR Target (Current) | 42.5% |
| Fixed 5% Target | 28.7% |

**Key Insight:** The mean reversion signal is EXCELLENT at identifying stocks that will move higher:
- 83.8% of signals eventually close positive
- 69.6% hit a 2% profit target
- BUT only 42.5% hit the aggressive 1.5x ATR target

### 5. Return Distribution

**Statistics (using 1.5x ATR targets):**
- Mean: 0.59%
- Median: 0.47%
- Std Dev: 2.92%
- Min: -6.05% | Max: 5.72%

**Distribution:**
- Big wins (>5%): 2.5%
- Small wins (0-5%): 48.8%
- Small losses (0 to -5%): 47.5%
- Big losses (<-5%): 1.2%

**Fat Tail Risk:** Minimal (only 1 trade with >2 std dev loss)

**Key Insight:** Returns are relatively symmetric. No hidden disaster risk. The problem is simply that targets are set too high.

## Root Cause Analysis

### Why the Model Fails

1. **Mismatch between signal quality and label definition**
   - Model correctly identifies mean reversion setups
   - But labels require 1.5x ATR profit (too aggressive)
   - This creates a training set where "good" trades are labeled as failures

2. **Overfitting to noise**
   - With only 31% base success rate, model has little signal
   - AUC of 0.56 suggests it's finding weak patterns
   - Calibration issues show it's overconfident

3. **Fundamental edge is real but small**
   - Best expectancy: 0.39% per trade (with 3.0x ATR targets)
   - This is barely above transaction costs
   - Not enough edge for a profitable system

## Recommendations

### Option 1: Fix Current Approach (RECOMMENDED)

**Retrain model with 1.0x ATR targets:**
- Win rate improves to ~60% (from 31%)
- More realistic profit targets
- Better calibration (less aggressive targets = fewer mislabeled trades)

**Implementation:**
```python
# In src/models/config.py
atr_target_multiplier: float = 1.0  # Change from 1.5
```

**Expected Outcome:**
- Win rate: 55-65%
- Expectancy: ~0.20% per trade
- Better model calibration

### Option 2: Use Fixed 2% Targets

**Alternative: Train with fixed percentage targets**
- 70% win rate at 2% profit target
- Simpler to understand and communicate
- Less dependent on volatility regime

**Implementation:**
```python
# In src/models/config.py
use_atr_targets: bool = False
target_return: float = 0.02  # 2% target
```

### Option 3: Focus on Ranking (NOT Classification)

**Better approach: Predict magnitude of return, not binary success**
- Train regression model to predict expected return
- Rank trades by predicted return
- Take top N ranked opportunities

**Why this is better:**
- Doesn't require arbitrary success threshold
- Model can learn full distribution of outcomes
- More useful for position sizing

### Option 4: Abandon This Approach

**If edge is too small:**
- 0.39% per trade expectancy is marginal
- After costs (0.1% transaction + 0.1% slippage), edge is only 0.19%
- May not be robust enough for live trading

**Alternative strategies to explore:**
1. Earnings announcement plays
2. Sector rotation
3. Volatility-based strategies
4. Options strategies (covered calls on holdings)

## Immediate Action Items

1. **DO NOT trade this model live** - it is miscalibrated and will lose money

2. **Retrain with 1.0x ATR targets** and re-evaluate:
   ```bash
   # Edit src/models/config.py first
   python scripts/train_mean_reversion_model.py
   python scripts/mean_reversion_calibration_analysis.py
   ```

3. **If retrained model still has AUC < 0.60:**
   - The edge is too small to be useful
   - Focus on alternative strategies

4. **Consider regime filtering:**
   - Model might work better in certain market conditions
   - Test performance by VIX level, market trend, etc.

## Bottom Line

**Should you be doing the opposite?**
→ **NO.** Mean reversion is the right direction.

**Is the model broken?**
→ **YES.** The target sizing is too aggressive and calibration is broken.

**Is this approach viable?**
→ **MAYBE.** With 1.0x ATR targets and better calibration, it might work. But the edge is small (0.2-0.4% per trade) and may not survive real-world conditions.

**What to do next?**
→ **Retrain with realistic targets (1.0x ATR or 2% fixed), then reassess.** If still poor after retraining, abandon this approach.

---

**Files for reference:**
- Analysis script: `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_critical_analysis.py`
- Calibration analysis: `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_calibration_analysis.py`
- Model config: `/Users/williambennett/Github/macro-beans/src/models/config.py`
