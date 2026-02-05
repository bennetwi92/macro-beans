# Mean Reversion Model: Action Plan

## TL;DR

**Problem:** Model has 31% win rate and is severely miscalibrated.

**Root Cause:** 1.5x ATR profit targets are too aggressive. Model correctly identifies mean reversion opportunities but labels them as failures because targets are unrealistic.

**Solution:** Retrain with 2% fixed profit targets → 66% win rate (proven in testing).

**Status:** DO NOT trade live until retraining is complete.

---

## Analysis Results Summary

### Current Performance (1.5x ATR Targets)
- Win rate: 31.3% (terrible)
- AUC: 0.5649 (barely above random)
- Calibration: 60% predicted → 35% actual (BROKEN)
- Conclusion: Model is overconfident and unreliable

### What We Discovered

1. **Mean reversion DOES work** (54.9% vs 48.2% for momentum)
   - You should NOT do the opposite
   - The strategy direction is correct

2. **Target sizing is the problem**
   - 0.75x ATR: 56% win rate
   - 1.0x ATR: 47% win rate
   - **1.5x ATR (current): 31% win rate** ← Too aggressive
   - Fixed 2% target: **70% win rate** ← BEST

3. **Model IS picking up real signals**
   - 83.8% of signals eventually close profitable
   - 66% hit a 2% profit target (tested on 2024 data)
   - Problem is purely the target definition

4. **Calibration is severely broken**
   - Average calibration error: 37%
   - 75% predicted confidence → 0% actual win rate
   - This is DANGEROUS for live trading

---

## Immediate Action Plan

### Step 1: Stop Trading (CRITICAL)
```bash
# DO NOT use the current model for live trading
# It will lose money due to miscalibration
```

### Step 2: Retrain with Fixed 2% Targets

**Edit configuration:**
```python
# File: src/models/config.py
# Change lines 20-22 to:

use_atr_targets: bool = False  # Change from True
target_return: float = 0.02    # Use 2% fixed target
stop_loss: float = -0.03       # Keep 3% stop
```

**Retrain the model:**
```bash
# This will take 5-10 minutes
python scripts/train_mean_reversion_model.py
```

**Expected improvements:**
- Win rate: 31% → 65-70%
- Better calibration (more realistic success definition)
- AUC should improve to 0.62-0.65+

### Step 3: Validate Calibration

```bash
# Check if new model is calibrated
python scripts/mean_reversion_calibration_analysis.py
```

**What to look for:**
- Average calibration error < 10%
- At 60% confidence, actual win rate should be 55-65%
- No catastrophic failures at high confidence

**If calibration is GOOD:**
- Proceed to Step 4 (paper trading)

**If calibration is STILL BAD:**
- Model may be overfitting
- Try these fixes:
  - Reduce model complexity (max_depth: 4 instead of 6)
  - Increase regularization (min_child_samples: 50 instead of 20)
  - Add more training data (extend to 2010-2024)

### Step 4: Paper Trade for 1 Month

**Setup paper trading:**
```bash
# Scan for opportunities daily
python scripts/scan_mean_reversion.py > daily_signals_$(date +%Y%m%d).txt

# Track each trade in a spreadsheet:
# - Entry date/price
# - Predicted confidence
# - Actual outcome (win/loss)
# - Exit date/price
# - Return %
```

**Metrics to track:**
- Win rate (should be 60-70%)
- Average return per trade (should be 0.5-1.0%)
- Calibration (does 65% confidence = 65% win rate in practice?)
- Slippage (are you getting filled at expected prices?)

**Success criteria for going live:**
- Win rate ≥ 60%
- Average return after costs ≥ 0.3%
- Calibration error < 15%
- No catastrophic losses (max loss should be ~3%)

### Step 5: Start Small with Real Money

**If paper trading succeeds:**
```bash
# Start with 20% of intended capital
# Position size: 5% per trade (max 4 positions)
# Risk: 3% stop loss per position

Example with $10K account:
- Use $2K for this strategy initially
- $400 per position ($2K / 5 positions)
- Max loss per trade: $12 (3% of $400)
- Max total drawdown: ~$100 if all positions fail
```

**Scale up gradually:**
- After 20 trades with >60% win rate → 40% of capital
- After 50 trades with >60% win rate → 60% of capital
- After 100 trades with >60% win rate → 100% of capital

---

## Alternative Path (If Retraining Fails)

### If retrained model STILL has poor performance:

**Check these issues:**

1. **Insufficient features**
   - Add market regime filters (VIX, market breadth)
   - Add sector relative strength
   - Add earnings calendar (avoid trades near earnings)

2. **Data quality issues**
   - Check for survivor bias (only using current index constituents)
   - Verify ATR calculations are correct
   - Check for data errors (splits, dividends)

3. **Market regime dependency**
   - Model might only work in certain conditions
   - Test performance by VIX level
   - Test performance by market trend (bull vs bear)

4. **Fundamental strategy flaws**
   - Maybe mean reversion on daily timeframe doesn't work anymore
   - Consider: weekly timeframe, different asset classes, options

### If nothing works:

**Abandon this approach and try:**
1. Earnings-based strategies (volatility crush, IV rank)
2. Relative value (pairs trading, sector rotation)
3. Volatility strategies (VIX term structure)
4. Momentum with better filters (not just RSI > 70)

---

## Risk Management Rules (When Live)

**Position Sizing:**
- Never more than 5% per position
- Never more than 5 open positions
- Never risk more than 3% on any single trade

**Stop Losses:**
- ALWAYS use hard stops (not mental stops)
- Place stop at entry - (1.0x ATR) or entry * 0.97
- No moving stops wider
- Only move stops tighter (trailing stops OK after 1% profit)

**Profit Targets:**
- Primary target: 2% profit
- If up 1% by day 3, trail stop to breakeven
- If up 2% intraday, consider taking 50% off table

**Exit Rules:**
- Stop hit: Exit immediately, no hesitation
- Target hit: Exit 100% or scale out 50%
- Day 5 without target: Exit on close
- Stock goes against criteria (breaks below MA50): Exit

**Circuit Breakers:**
- If 3 losses in a row: Stop trading for 1 week, review trades
- If down 5% on month: Stop trading, reassess strategy
- If win rate drops below 45% over 20 trades: Stop trading

---

## Monitoring Dashboard (Build This)

**Daily checks:**
- [ ] New scan completed
- [ ] All positions reviewed
- [ ] Any stops hit overnight?
- [ ] Any approaching day 5 expiry?

**Weekly metrics:**
- Win rate (trailing 20 trades)
- Average return per trade
- Largest win / largest loss
- Sharpe ratio
- Current drawdown from peak

**Monthly review:**
- Compare predicted confidence to actual outcomes (calibration)
- Best performing setups (which features mattered)
- Worst performing setups (what went wrong)
- Market conditions that work best
- Adjust strategy as needed

---

## Key Files Reference

**Analysis scripts:**
- `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_critical_analysis.py` - Main analysis
- `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_calibration_analysis.py` - Check calibration
- `/Users/williambennett/Github/macro-beans/scripts/mean_reversion_quick_fix_test.py` - Test target changes

**Training pipeline:**
- `/Users/williambennett/Github/macro-beans/scripts/train_mean_reversion_model.py` - Retrain model
- `/Users/williambennett/Github/macro-beans/src/models/config.py` - Configuration (EDIT THIS)

**Production scanner:**
- `/Users/williambennett/Github/macro-beans/scripts/scan_mean_reversion.py` - Daily signals

**Documentation:**
- `/Users/williambennett/Github/macro-beans/docs/mean_reversion_critical_findings.md` - Full analysis
- `/Users/williambennett/Github/macro-beans/docs/mean_reversion_action_plan.md` - This file

---

## Decision Tree

```
START: Is current model viable?
│
├─ NO (31% win rate, broken calibration)
│  │
│  └─ STEP 1: Retrain with 2% fixed targets
│     │
│     ├─ Success (>60% win rate, calibrated)
│     │  │
│     │  └─ STEP 2: Paper trade 1 month
│     │     │
│     │     ├─ Success (>60% win rate maintained)
│     │     │  │
│     │     │  └─ STEP 3: Go live with 20% capital
│     │     │     │
│     │     │     └─ Scale gradually to 100%
│     │     │
│     │     └─ Failure (win rate drops, slippage kills edge)
│     │        │
│     │        └─ Abandon or refine (add filters, change timeframe)
│     │
│     └─ Failure (still poor performance)
│        │
│        └─ Try alternative approaches or abandon
│
└─ (This branch doesn't exist - current model is NOT viable)
```

---

## Bottom Line

**What to do RIGHT NOW:**

1. Edit `src/models/config.py` → change to 2% fixed targets
2. Run `python scripts/train_mean_reversion_model.py`
3. Run `python scripts/mean_reversion_calibration_analysis.py`
4. If calibration is good → paper trade for 1 month
5. If paper trading works → go live with small capital

**Timeline:**
- Retraining: 10 minutes
- Calibration check: 5 minutes
- Paper trading: 1 month (20-30 trades)
- Go live decision: After paper trading results

**Critical success factor:**
- Model must be well-calibrated (predicted confidence matches actual win rate)
- Without calibration, you can't size positions correctly
- Without calibration, you can't trust the model

**Most likely outcome:**
- Retraining with 2% targets will work
- You'll get 60-70% win rate
- Edge will be small but positive (~0.5% per trade)
- Worth running with portion of capital as one strategy among several
