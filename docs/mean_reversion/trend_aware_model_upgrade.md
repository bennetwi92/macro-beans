# Trend-Aware Model Upgrade

**Date:** 2026-02-05

## Problem Statement

The mean reversion model was giving 91% confidence to COIN despite being in a severe downtrend (-30% below MA50). The original approach used a post-hoc uptrend filter, but this was a bandaid solution. The model should **learn** when trend direction matters.

## Solution: ADX and Directional Features

Added 10 new features to help the model understand trend strength and direction:

### ADX and Directional Indicators (5 features)
- `adx_14`: Measures trend strength (0-100, >25 = strong trend)
- `plus_di_14`: Positive directional movement indicator
- `minus_di_14`: Negative directional movement indicator
- `di_diff`: +DI - -DI (positive = uptrend, negative = downtrend)
- `di_ratio`: +DI / -DI (>1 = uptrend, <1 = downtrend)

### Trend Clarity Features (5 features)
- `price_above_ma50`: Binary indicator (1 if price > MA50)
- `price_above_ma200`: Binary indicator (1 if price > MA200)
- `ma50_above_ma200`: Binary indicator (1 if MA50 > MA200)
- `ma50_slope`: Rate of change of MA50 over 10 days
- `trend_alignment`: 1 if price > MA50 > MA200 (golden alignment)

## Implementation

**File:** `/Users/williambennett/Github/macro-beans/src/models/features.py`

Added `calculate_adx()` method and integrated into `calculate_momentum_features()`.

## Model Performance

**Total Features:** 90 (up from 80)

**Feature Importance Analysis:**
- Trend features: 1,589 total importance
- Oversold features: 2,053 total importance
- ADX is now #4 most important feature overall (425 importance)

**Top Trend Features by Importance:**
1. adx_14: 425
2. ma50_slope: 345
3. plus_di_14: 297
4. minus_di_14: 216
5. di_diff: 152

**Model Metrics:**
- Mean AUC: 0.6097
- Mean Precision: 0.6181
- Mean Recall: 0.7009

## Scanner Enhancement

**File:** `/Users/williambennett/Github/macro-beans/scripts/scan_mean_reversion.py`

Added `calculate_trend_quality()` function that scores opportunities 0-100:
- 70-100: Strong uptrend (price > MA50 > MA200, +DI > -DI significantly)
- 50-70: Uptrend (some positive trend indicators)
- 0-50: Downtrend or weak trend

Scanner now sorts by Trend Quality first, then Confidence.

## Results: COIN vs PFE Comparison

### COIN (Downtrend)
- **Confidence:** 79.6%
- **Trend Quality:** 0 (downtrend)
- **Price vs MA50:** -30%
- **ADX:** 31.5 (strong trend)
- **+DI / -DI:** 10.6 / 46.9
- **DI Diff:** -36.3 (strong downtrend)
- **RSI:** 2.1 (extreme oversold)

### PFE (Uptrend)
- **Confidence:** 68.4%
- **Trend Quality:** 100 (strong uptrend)
- **Price vs MA50:** +6.2%
- **ADX:** 31.7 (strong trend)
- **+DI / -DI:** 35.1 / 18.8
- **DI Diff:** +16.3 (uptrend)
- **RSI:** 64.9

## Key Insight

The model **learned** the trend features correctly, but it also learned that extreme oversold conditions (RSI < 5) often bounce even in downtrends. This is historically accurate for mean reversion.

**Solution:** Rather than force the model to ignore downtrends, we surface **Trend Quality** as a separate dimension. Users can now see:
1. Model confidence (how oversold/likely to bounce)
2. Trend quality (is this a safe environment for mean reversion)

## Top Opportunities (Trend Quality 100)

From latest scan:
1. **SLB:** 74% confidence, DI_Diff +30
2. **WMT:** 70% confidence, DI_Diff +30
3. **PFE:** 68% confidence, DI_Diff +16
4. **COP:** 61% confidence, DI_Diff +26

## Downtrend Warnings (Trend Quality 0)

High confidence but dangerous:
1. **SOFI:** 85% confidence, DI_Diff -27
2. **COIN:** 80% confidence, DI_Diff -36
3. **HOOD:** 79% confidence, DI_Diff -35

## Recommendation

**Focus on opportunities with Trend Quality 70+** for safer mean reversion setups. Downtrend opportunities (Quality <50) may bounce but carry higher risk.

## Files Modified

1. `/Users/williambennett/Github/macro-beans/src/models/features.py` - Added ADX and trend features
2. `/Users/williambennett/Github/macro-beans/scripts/scan_mean_reversion.py` - Added trend quality scoring
3. `/Users/williambennett/Github/macro-beans/models/mean_reversion_model.pkl` - Retrained with new features

## Testing Scripts

Created for validation:
- `/Users/williambennett/Github/macro-beans/scripts/test_trend_awareness.py`
- `/Users/williambennett/Github/macro-beans/scripts/analyze_feature_importance.py`
