# VIX Options Greeks - Quick Reference Guide

## What You Need from Your Options Chain

### **Theta (Θ)** - Time Decay
**Look for:** Negative number (e.g., -0.020, -0.015, -0.030)

**What it means:**
- How much money you lose per day from time decay
- Example: Theta = -0.020 means you lose $2.00 per day
- Lower (less negative) is better = slower decay

**Typical Values:**
- 60 DTE, $20 strike: -0.015 to -0.020
- 36 DTE, $20 strike: -0.025 to -0.035
- 15 DTE, $20 strike: -0.045 to -0.060

**Rule of thumb:**
- Theta accelerates as you get closer to expiration
- First 30 days: lose ~30-40% to decay
- Last 15 days: lose ~50-60% to decay

---

### **Vega (ν)** - Volatility Sensitivity
**Look for:** Positive number (e.g., 0.08, 0.12, 0.15)

**What it means:**
- How much money you GAIN when implied volatility (IV) increases by 1%
- Example: Vega = 0.12 means you gain $12 for every 1% increase in IV
- Higher is better = more profit when VIX spikes

**Typical Values:**
- 60 DTE, $20 strike: 0.10 to 0.14
- 36 DTE, $20 strike: 0.08 to 0.12
- 15 DTE, $20 strike: 0.05 to 0.08

**Why Vega matters for VIX:**
- When VIX spikes, IV explodes (often 2-3x)
- If VIX moves 30%, IV might rise 60-100%
- This is WHERE YOUR PROFIT comes from!
- High Vega = bigger premium expansion

---

## How to Use Greeks in the Calculator

### Step 1: Find Your Greeks
1. Open your broker's options chain
2. Find your contract (e.g., Feb $20 call)
3. Look for columns labeled "Greeks" or individual Theta/Vega columns

### Step 2: Enter in Calculator
1. Check "Use Actual Greeks" box in sidebar
2. Enter Theta (will be negative, like -0.020)
3. Enter Vega (will be positive, like 0.12)

### Step 3: Compare Results
- With Greeks: Uses your actual option's decay and IV sensitivity
- Without Greeks: Uses estimated 30-40% monthly decay model
- Greeks are MORE ACCURATE for your specific contract

---

## Reading Your Options Chain

### Example Options Chain Row:
```
Strike | Exp    | Last | Bid  | Ask  | Theta  | Vega | Delta | Gamma
$20    | Feb 17 | 1.25 | 1.20 | 1.30 | -0.022 | 0.11 | 0.35  | 0.04
```

**What to copy into calculator:**
- Entry Premium: Use **Ask** price ($1.30) = what you'll pay
- Theta: Copy **-0.022**
- Vega: Copy **0.11**
- Ignore Delta and Gamma (not needed for this strategy)

---

## Greeks Comparison by Expiration

### January (36 DTE) $20 Call @ $1.00
**Estimated Greeks:**
- Theta: -0.025 to -0.030
- Vega: 0.08 to 0.10

**What this means:**
- Faster decay ($2.50-3.00/day)
- Lower IV sensitivity
- Need spike to happen FAST

---

### February (64 DTE) $20 Call @ $1.30
**Estimated Greeks:**
- Theta: -0.018 to -0.022
- Vega: 0.10 to 0.13

**What this means:**
- Slower decay ($1.80-2.20/day)
- Higher IV sensitivity
- More breathing room

---

## Quick Decision Matrix

| If Your Greeks Are... | What It Means | Action |
|----------------------|---------------|---------|
| Theta < -0.030 | Fast decay | Need quick spike, risky |
| Theta -0.020 to -0.030 | Normal decay | Workable, set tight stops |
| Theta -0.015 to -0.020 | Slow decay | Good, more time to work |
| Vega < 0.08 | Low sensitivity | Less profit on spike |
| Vega 0.08 to 0.12 | Normal | Standard profit potential |
| Vega > 0.12 | High sensitivity | Max profit on spike! |

---

## What Makes a Good VIX Call Option?

### ✅ Ideal Profile:
- **Theta**: -0.015 to -0.022 (manageable decay)
- **Vega**: 0.10 to 0.15 (strong IV sensitivity)
- **DTE**: 45-60 days
- **Strike**: 25-35% above current VIX
- **Price**: $0.80-1.50

### ⚠️ Avoid:
- Theta worse than -0.035 (decaying too fast)
- Vega below 0.06 (weak premium expansion)
- DTE below 30 days (theta cliff approaching)
- Strike >40% OTM (lottery ticket)

---

## Real Example Calculation

**Setup:**
- Feb $20 call @ $1.30
- Theta: -0.020
- Vega: 0.12
- Current VIX: 15.75

**If VIX spikes to 20 in 14 days:**

1. **Theta decay:** -0.020 × 14 = -$0.28 loss
2. **VIX move:** 15.75 → 20 = +27%
3. **IV expansion:** ~60% (2.5x VIX move)
4. **Vega gain:** 0.12 × 60 = +$7.20 gain
5. **Intrinsic:** $0 (still OTM, VIX futures trade differently)

**Total value:** $1.30 - $0.28 + $7.20 = **$8.22**
**Your gain:** $8.22 / $1.30 = **532%** 🚀

*This is why you use Greeks! The Vega contribution dominates everything.*

---

## FAQ

**Q: My broker doesn't show Greeks. What do I do?**
A: Use the estimated model in the calculator (uncheck "Use Actual Greeks"). It's less precise but still useful.

**Q: Greeks keep changing. Which value do I use?**
A: Use the current values when you enter the trade. Greeks change as market conditions change.

**Q: Should I update Greeks daily in the calculator?**
A: No need. Use entry Greeks to model the trade. Once you're in, watch your actual P&L.

**Q: What if my Theta is worse than -0.030?**
A: Consider a longer expiration. Fast decay is dangerous for a 30-day hold strategy.

**Q: Can I ignore Delta and Gamma?**
A: Yes! For VIX options, Theta and Vega are what matter for premium expansion plays.

---

## Bottom Line

**For your strategy (VIX low → spike):**
1. ✅ **Vega is KING** - This is your profit source
2. ⚠️ **Theta is your enemy** - Lower is better
3. ❌ **Delta doesn't matter much** - VIX options behave differently

**Ideal Greeks for Feb $20 call:**
- Theta: -0.018 to -0.020 ✅
- Vega: 0.11 to 0.13 ✅

This gives you manageable decay with strong premium expansion potential!
