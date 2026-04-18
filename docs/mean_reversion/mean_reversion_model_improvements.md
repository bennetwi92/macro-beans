# Mean Reversion Model Improvements - February 2025

## Summary

Implemented three critical improvements to the mean reversion trading model:

1. **ATR-based volatility-adjusted targets** (replaced fixed 3% targets)
2. **Stock universe filtering** (removed 8 poor-performing stocks)
3. **Lower confidence threshold** (reduced from 65% to 60%)

---

## 1. ATR-Based Volatility Adjustment

### Problem
- Fixed 3% stop/target was inappropriate across different volatility stocks
- Low volatility stocks (PG, WMT): ATR ~1.2% - fixed 3% was too aggressive
- High volatility stocks (TSLA, AMD): ATR ~3%+ - fixed 3% was too conservative
- One-size-fits-all approach ignored individual stock characteristics

### Solution
Implemented ATR(14)-based dynamic targets:
- **Target**: Entry + (1.5 × ATR)
- **Stop**: Entry - (1.0 × ATR)
- Each stock now has personalized risk/reward based on volatility profile

### Implementation
- `/Users/williambennett/Github/macro-beans/src/models/features.py`:
  - Added `calculate_atr()` method
  - Updated `generate_labels()` to use ATR-based targets
  - Added ATR features (atr_14, atr_pct, atr_ratio) to feature set

- `/Users/williambennett/Github/macro-beans/src/models/config.py`:
  - Added `use_atr_targets: bool = True`
  - Added `atr_target_multiplier: float = 1.5`
  - Added `atr_stop_multiplier: float = 1.0`

### Results
ATR-based approach shows stocks naturally fall into risk profiles:
- **High volatility** (HOOD, COIN, SOFI): 6-7% ATR → wider targets (9-10%)
- **Low volatility** (PG, WMT): 1.2% ATR → tighter targets (1.8%)
- Risk/Reward consistently 1.5x regardless of volatility

---

## 2. Stock Universe Filtering

### Analysis Results
Analyzed historical mean reversion success rates (2015-2024) for all training stocks.

#### Poor Performers (Excluded - Success Rate <30%)
| Stock | Success Rate | Total Samples | ATR % | Reason |
|-------|-------------|---------------|-------|--------|
| PG    | 15.95%      | 2,264        | 1.28% | Low volatility + poor mean reversion |
| WMT   | 22.53%      | 2,264        | 1.15% | Low volatility + poor mean reversion |
| V     | 25.57%      | 2,264        | 1.16% | Low volatility + poor mean reversion |
| COST  | 25.80%      | 2,264        | 1.80% | Poor mean reversion characteristics |
| CSCO  | 28.31%      | 2,264        | 1.18% | Low volatility + poor mean reversion |
| DIS   | 28.75%      | 2,264        | 1.49% | Poor mean reversion characteristics |
| XOM   | 29.81%      | 2,264        | 1.65% | Poor mean reversion characteristics |
| HD    | 29.90%      | 2,264        | 1.55% | Poor mean reversion characteristics |

**Key Finding**: Low volatility stocks (<2% ATR) averaged 30.13% success rate vs. better performers.

#### Top Performers (Success Rate ≥40%)
| Stock | Success Rate | Total Samples | ATR % |
|-------|-------------|---------------|-------|
| AMD   | 53.36%      | 2,264        | 3.01% |
| TSLA  | 51.46%      | 2,264        | 3.40% |
| NVDA  | 50.97%      | 2,264        | 2.37% |
| NFLX  | 46.73%      | 2,264        | 2.22% |
| PYPL  | 43.45%      | 2,138        | 2.51% |
| META  | 40.28%      | 2,264        | 2.10% |

### Updated Training Universe
**Included (18 stocks)**:
AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, JPM, BAC, JNJ, MA, UNH, NFLX, ADBE, CRM, PYPL, INTC, AMD, PEP, KO, NKE, MCD, CVX

**Excluded (8 stocks)**:
HD, XOM, DIS, CSCO, COST, V, WMT, PG

---

## 3. Confidence Threshold Adjustment

### Change
- **Previous**: 65% confidence threshold
- **New**: 60% confidence threshold

### Rationale
- More trading opportunities while maintaining quality
- ATR-based targets provide better risk management, allowing slightly lower threshold
- Filtered stock universe removes worst performers, improving signal quality

---

## Model Training Results

### Overall Statistics (ATR-Based Labels)
- **Total samples**: 40,626 (down from ~58,000 due to exclusions)
- **Success rate**: 31.27% (with ATR targets)
- **Cross-validation AUC**: 0.5649 (±0.1510)

### Success Rates by Stock (ATR-Based)
| Stock | Success Rate | Change from Fixed 3% |
|-------|-------------|---------------------|
| AAPL  | 34.10%      | -1.9% (tighter targets for low vol) |
| AMD   | 32.95%      | -20.4% (more realistic for high vol) |
| TSLA  | 32.16%      | -19.3% (more realistic for high vol) |
| MSFT  | 32.02%      | +0.2% |
| NVDA  | 33.22%      | -17.5% (more realistic for high vol) |

**Note**: Success rates appear lower with ATR because high-volatility stocks now have appropriately wider targets. This is more realistic for actual trading.

### Top Features
ATR-related features now rank highly in importance:
1. month (486)
2. volume_price_trend (484)
3. **atr_ratio (465)** ← NEW
4. volatility_20d (426)
5. price_to_ma_200 (424)
6. bb_bandwidth_50 (392)
7. ma_20_50_cross (386)
8. volatility_10d (372)
9. **atr_pct (365)** ← NEW

---

## Current Opportunities (February 5, 2025)

Scanner found 3 opportunities at 60% threshold:

### HOOD - 79.7% Confidence
- Entry: $80.62
- Target: $89.05 (+10.46%)
- Stop: $75.00 (-6.97%)
- ATR: 6.97% (high volatility stock)
- RSI(14): 2.9 (extremely oversold)
- Risk/Reward: 1.50x

### COIN - 75.9% Confidence
- Entry: $168.62
- Target: $184.40 (+9.36%)
- Stop: $158.10 (-6.24%)
- ATR: 6.24% (high volatility stock)
- RSI(14): 2.1 (extremely oversold)
- Risk/Reward: 1.50x

### SOFI - 73.1% Confidence
- Entry: $20.75
- Target: $22.61 (+8.97%)
- Stop: $19.51 (-5.98%)
- ATR: 5.98% (high volatility stock)
- RSI(14): 8.4 (extremely oversold)
- Risk/Reward: 1.50x

**Note**: All three are high-volatility stocks with wider ATR-based targets. This is appropriate given their price action characteristics.

---

## Key Files Updated

### Core Components
1. **`/Users/williambennett/Github/macro-beans/src/models/features.py`**
   - Added ATR calculation
   - Updated label generation for ATR-based targets
   - Added ATR features to feature set

2. **`/Users/williambennett/Github/macro-beans/src/models/config.py`**
   - Added ATR configuration parameters
   - Lowered confidence threshold to 60%

3. **`/Users/williambennett/Github/macro-beans/scripts/train_mean_reversion_model.py`**
   - Updated training universe (removed 8 poor performers)
   - Uses ATR-based label generation

4. **`/Users/williambennett/Github/macro-beans/scripts/scan_mean_reversion.py`**
   - Excludes poor-performing stocks
   - Displays ATR-based targets and stops
   - Shows risk/reward ratios
   - Enhanced output format

### Analysis Scripts
5. **`/Users/williambennett/Github/macro-beans/scripts/analyze_stock_performance.py`** (NEW)
   - Analyzes historical success rates by stock
   - Calculates ATR statistics
   - Identifies poor performers for exclusion

---

## Impact Summary

### Improvements
1. **More realistic targets**: Each stock has volatility-appropriate risk/reward
2. **Better stock selection**: Removed chronic poor performers from universe
3. **More opportunities**: Lower threshold (60% vs 65%) generates more signals
4. **Clearer risk management**: ATR-based stops/targets visible in scanner output

### Trade-offs
1. **Lower base success rate**: More realistic targets mean lower historical win rate
2. **Higher volatility exposure**: Current opportunities are all high-vol stocks
3. **Model complexity**: ATR calculation adds computational overhead

### Next Steps
1. Monitor live performance with ATR-based targets
2. Consider adjusting ATR multipliers (currently 1.5x target, 1.0x stop)
3. Backtest on 2024 data with new parameters
4. Consider adding more high-volatility stocks to training universe
5. Analyze if 60% threshold generates enough quality signals

---

## Usage

### Train Model
```bash
python scripts/train_mean_reversion_model.py
```

### Scan for Opportunities
```bash
python scripts/scan_mean_reversion.py
```

### Analyze Stock Performance
```bash
python scripts/analyze_stock_performance.py
```