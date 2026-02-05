# Mean Reversion Model - Quick Start Guide

## Daily Workflow

### 1. Scan for Opportunities
```bash
python scripts/scan_mean_reversion.py
```

**Output**: List of high-probability mean reversion setups with ATR-based targets.

### 2. Review Signals
Each opportunity shows:
- **Confidence**: Model's probability (60%+ threshold)
- **Entry**: Current price
- **Target**: ATR-based profit target (1.5× ATR)
- **Stop**: ATR-based stop loss (1.0× ATR)
- **Risk/Reward**: Always 1.5:1
- **ATR%**: Volatility as % of price
- **RSI(14)**: Oversold indicator
- **Dist from 20d Low**: How far from recent bottom

### 3. Trade Execution
Use the provided targets and stops directly from scanner output.

---

## Understanding ATR-Based Targets

### What is ATR?
Average True Range - measures stock's typical daily price movement over 14 days.

### Why ATR Instead of Fixed 3%?

**Example: HOOD vs PG**

**HOOD (High Volatility)**:
- Price: $80.62
- ATR: $5.62 (6.97% of price)
- Daily moves: Regularly swings $5-7
- Target: $89.05 (+10.46% = 1.5×ATR)
- Stop: $75.00 (-6.97% = 1.0×ATR)

**PG (Low Volatility) - EXCLUDED**:
- Price: $169
- ATR: $2.16 (1.28% of price)
- Daily moves: Rarely moves $2+
- Old fixed 3% target was unrealistic
- Now excluded from universe

**Key Insight**: High-volatility stocks get wider targets; low-volatility stocks are filtered out.

---

## Model Configuration

### Current Settings (Optimized)
```python
# ATR-based targets
use_atr_targets: True
atr_target_multiplier: 1.5    # Target = Entry + (1.5 × ATR)
atr_stop_multiplier: 1.0      # Stop = Entry - (1.0 × ATR)

# Scanning
confidence_threshold: 0.60    # 60% minimum probability
max_holding_days: 5           # Exit after 5 days max

# Stock universe: 18 stocks
# Excluded: HD, XOM, DIS, CSCO, COST, V, WMT, PG
```

### If You Want to Adjust

**More opportunities** (lower quality):
```python
confidence_threshold: 0.55  # Lower threshold
```

**Wider targets** (bigger wins, lower success rate):
```python
atr_target_multiplier: 2.0  # 2× ATR instead of 1.5×
```

**Tighter stops** (higher R:R, more stopped out):
```python
atr_stop_multiplier: 0.75   # 0.75× ATR instead of 1.0×
```

---

## Interpreting Results

### Good Setup Example
```
HOOD - Confidence: 79.7%
  Entry:         $80.62
  Target:        $89.05 (+10.46%)
  Stop:          $75.00 (-6.97%)
  Risk/Reward:   1.50x
  ATR:           6.97% of price
  RSI(14):       2.9           ← EXTREMELY oversold
  From 20d Low:  3.9%          ← Near recent lows
```

**Why it's good**:
- High confidence (79.7%)
- Extremely oversold (RSI 2.9)
- Near 20-day lows (3.9% above)
- ATR-appropriate targets for volatile stock

### Red Flags
- Confidence <60%: Skip
- RSI >30: Not oversold enough
- >10% from 20d low: Not near bottom
- ATR <2%: Too stable for mean reversion (already filtered)

---

## Historical Performance by Stock

### Top Performers (Keep)
| Stock | Success Rate | ATR% | Reason |
|-------|-------------|------|--------|
| AMD   | 53.36%      | 3.01%| High vol + good mean reversion |
| TSLA  | 51.46%      | 3.40%| High vol + good mean reversion |
| NVDA  | 50.97%      | 2.37%| Good mean reversion |
| NFLX  | 46.73%      | 2.22%| Good mean reversion |
| PYPL  | 43.45%      | 2.51%| Good mean reversion |
| META  | 40.28%      | 2.10%| Good mean reversion |

### Excluded (Poor Performers)
| Stock | Success Rate | ATR% | Reason |
|-------|-------------|------|--------|
| PG    | 15.95%      | 1.28%| Too stable, poor mean reversion |
| WMT   | 22.53%      | 1.15%| Too stable, poor mean reversion |
| V     | 25.57%      | 1.16%| Too stable, poor mean reversion |
| COST  | 25.80%      | 1.80%| Poor mean reversion |
| CSCO  | 28.31%      | 1.18%| Too stable, poor mean reversion |

**Pattern**: Low-volatility stocks (<2% ATR) had poor mean reversion.

---

## Retraining the Model

### When to Retrain
- Monthly: Fresh data
- After major market regime change
- If live performance degrades

### How to Retrain
```bash
python scripts/train_mean_reversion_model.py
```

**What it does**:
1. Loads data for 18 filtered stocks (2015-2024)
2. Calculates ATR-based labels
3. Trains LightGBM classifier
4. Cross-validates (5-fold)
5. Saves model to `models/mean_reversion_model.pkl`

**Takes**: ~2-3 minutes

---

## File Locations

### Models
- `/Users/williambennett/Github/macro-beans/models/mean_reversion_model.pkl` - Trained model
- `/Users/williambennett/Github/macro-beans/models/feature_names.pkl` - Feature list

### Scripts
- `/Users/williambennett/Github/macro-beans/scripts/scan_mean_reversion.py` - Daily scanner
- `/Users/williambennett/Github/macro-beans/scripts/train_mean_reversion_model.py` - Training pipeline
- `/Users/williambennett/Github/macro-beans/scripts/analyze_stock_performance.py` - Performance analysis

### Source Code
- `/Users/williambennett/Github/macro-beans/src/models/features.py` - ATR calculation, feature engineering
- `/Users/williambennett/Github/macro-beans/src/models/config.py` - Configuration
- `/Users/williambennett/Github/macro-beans/src/models/model.py` - LightGBM wrapper
- `/Users/williambennett/Github/macro-beans/src/models/data_loader.py` - Data loading

### Data
- `/Users/williambennett/Github/macro-beans/data/stock_history/` - Historical price data
- `/Users/williambennett/Github/macro-beans/data/stock_performance_analysis.csv` - Performance stats

---

## Troubleshooting

### "No opportunities found"
- Normal in low-volatility markets
- Try lowering confidence threshold to 0.55
- Check if data is up to date

### "Module not found" errors
```bash
pip install joblib scikit-learn lightgbm pandas numpy
```

### Model performance degrading
- Retrain with recent data
- Market regime may have changed
- Consider adjusting ATR multipliers

---

## Key Takeaways

1. **ATR-based targets** = Volatility-appropriate risk management
2. **Filtered universe** = Only stocks with proven mean reversion
3. **1.5:1 R:R** = Profitable even with 40% win rate
4. **60% threshold** = Balance of quality and opportunity
5. **RSI + proximity to lows** = Entry timing confirmation

**Bottom Line**: Trade the scanner signals as displayed. ATR handles volatility differences automatically.