# QQQ3.L Positive-Streak Study — does an N-day positive run predict day N+1?

**Hypothesis tested:** if QQQ3.L (WisdomTree 3x Long Nasdaq 100, LSE) closes up N days in a row, is the next day more likely to be positive than baseline?

**Method:** pulled QQQ3.L history via yfinance (2012-12-14 → 2026-05-01, 3,378 daily rows after first NaN), tagged each day with the prior streak of consecutive positive (and consecutive negative) returns ending at the previous close, then computed the conditional next-day return distribution per streak length. 95% Wilson CIs, two- and one-sided binomial tests vs the unconditional baseline, and a 2x2 chi-square Markov-independence test on (sign yesterday, sign today).

**Files:**
- Script: `scripts/event_studies/qqq3l_streak_study.py`
- Per-day table: `data/event_studies/qqq3l_streak_rows.csv`
- Bucketed stats: `data/event_studies/qqq3l_streak_buckets.csv`
- Magnitude-conditioned view: `data/event_studies/qqq3l_streak_magnitude.csv`
- Chart: `data/event_studies/qqq3l_streak_study.png`

---

## Headline

**The data does not support the hypothesis at the simple sign level.** A 2x2 chi-square test on (yesterday's sign, today's sign) gives p = 0.7132 — we cannot reject the null that the sign of today's return is statistically independent of the sign of yesterday's. In plain English: knowing only that yesterday closed up tells you almost nothing about whether today will close up.

| Quantity | Value |
|---|---:|
| Daily observations | 3,378 |
| Date range | 2012-12-14 → 2026-05-01 |
| Unconditional P(ret > 0) | 0.5628 |
| Unconditional P(ret < 0) | 0.4254 |
| Unconditional P(ret = 0) | 0.0118 |
| Markov chi-square p-value | 0.7132 |

The unconditional baseline of 56.3% is well above 50% — but that is the *positive drift* of a 3x long Nasdaq instrument over a 13-year bull regime, not a streak signal. Any conditional probability needs to be compared against 0.5628, not against 0.5.

---

## Positive-streak buckets — P(next > 0 | N consecutive positive prior days)

| N | n_obs | P(next > 0) | 95% Wilson CI | mean next ret (bps) | binom p (one-sided) | z-test vs baseline p |
|---:|---:|---:|---|---:|---:|---:|
| 1  | 826 | 0.545 | [0.511, 0.579] |   6.1 | 0.859 | 0.351 |
| 2  | 450 | 0.578 | [0.532, 0.623] |   8.7 | 0.277 | 0.546 |
| 3  | 259 | **0.618** | [0.557, 0.675] |  56.6 | **0.042** | 0.085 |
| 4  | 160 | 0.556 | [0.479, 0.631] |   4.2 | 0.598 | 0.871 |
| 5  |  89 | 0.584 | [0.481, 0.681] |  13.1 | 0.383 | 0.686 |
| 6  |  52 | 0.558 | [0.423, 0.684] |  16.0 | 0.587 | 0.942 |
| 7  |  29 | 0.483 | [0.314, 0.656] | -19.1 | 0.854 | 0.387 |
| 8+ |  35 | 0.600 | [0.436, 0.745] |  25.1 | 0.395 | 0.659 |

**Reading the table:**

- The user's intuition says higher N should mean a higher P(next > 0). Empirically the bumps at N=2 and N=3 sit just above baseline (0.578 and 0.618 vs 0.563), but the only bucket that crosses one-sided p < 0.05 vs baseline is **N=3, p = 0.042**.
- That single hit does not survive a multiple-comparisons adjustment — testing 8 buckets gives a Bonferroni-adjusted threshold of ≈ 0.006, which N=3 does not clear (and the two-sided test does not clear 0.05 either, p = 0.079).
- N=1 actually sits *below* baseline (0.545 vs 0.563). If the "winners keep winning" intuition were true at the sign level, this should be the most populated bucket and should be at or above baseline. It is not.
- N=7 dips to 0.483 with a slightly negative mean next-day return (−19 bps). The sample (n=29) is too small to claim mean reversion, but the direction is consistent with "very long winning streaks tend to exhaust."

---

## Negative-streak buckets — P(next < 0 | N consecutive negative prior days)

| N | n_obs | P(next < 0) | 95% Wilson CI | mean next ret (bps) | binom p (one-sided) |
|---:|---:|---:|---|---:|---:|
| 1  | 813 | 0.440 | [0.407, 0.475] |  18.1 | 0.204 |
| 2  | 358 | 0.447 | [0.396, 0.499] |  18.7 | 0.220 |
| 3  | 160 | 0.450 | [0.375, 0.527] |  19.8 | 0.291 |
| 4  |  72 | **0.319** | [0.223, 0.434] | 172.3 | 0.975 |
| 5  |  23 | 0.391 | [0.222, 0.592] |  49.9 | 0.703 |
| 6  |   9 | 0.111 | [0.020, 0.435] | 405.7 | 0.993 |
| 7  |   1 | 1.000 | — | -308.6 | — |
| 8+ |   2 | 0.500 | [0.094, 0.906] | 214.3 | 0.670 |

**Reading the table:**

The negative side is more interesting than the positive side. After **four consecutive down days** (n=72), the probability that day five is also negative drops to 0.319 — well below the unconditional 0.425 — and the mean next-day return jumps to **+172 bps**. That looks like a mean-reversion signal in the right direction, although:

- Two- and one-sided binomial tests against the negative baseline are p = 0.074 and p = 0.975 (one-sided "greater than baseline" is the wrong tail here; the relevant directional test is *less than* baseline, which would be ≈ 0.037).
- Sample sizes for N ≥ 5 are too small to be confident (Wilson CIs are very wide; the N=7 bucket is a single observation and should be ignored).
- This is consistent with the well-documented short-horizon mean-reversion in equity index ETFs after sustained sell-offs, amplified here by 3x leverage.

---

## Magnitude-conditioned view — does the signal live in the count or the run-up size?

For positive streaks of N=2, 3, 4, the table below splits each N into quintiles by the cumulative N-day return ending at the prior close, then reports P(next > 0).

| N | quintile | cum prior range | n_obs | P(next > 0) | mean next ret (bps) |
|---:|:--|:--|---:|---:|---:|
| 2 | Q1 | 0.03 – 2.06% | 215 | 0.572 |  15.6 |
| 2 | Q2 | 2.08 – 3.16% | 215 | 0.544 |  -0.7 |
| 2 | Q3 | 3.16 – 4.52% | 214 | 0.622 |  24.4 |
| 2 | Q4 | 4.52 – 6.93% | 215 | 0.609 |  51.0 |
| 2 | Q5 | 6.94 – 30.33% | 215 | 0.563 |  10.0 |
| 3 | Q1 | 0.70 – 3.52% | 125 | 0.552 |  19.8 |
| 3 | Q2 | 3.53 – 4.88% | 125 | 0.584 |   4.4 |
| 3 | Q3 | 4.91 – 6.60% | 124 | 0.613 |  15.0 |
| 3 | Q4 | 6.61 – 9.41% | 125 | **0.632** |  66.0 |
| 3 | Q5 | 9.45 – 36.64% | 125 | 0.544 |  36.1 |
| 4 | Q1 | 1.26 – 5.06% |  73 | 0.479 |  -0.1 |
| 4 | Q2 | 5.06 – 6.53% |  73 | 0.534 | -31.4 |
| 4 | Q3 | 6.55 – 8.47% |  73 | 0.589 |  20.9 |
| 4 | Q4 | 8.48 – 11.77% |  73 | **0.685** |  76.2 |
| 4 | Q5 | 11.80 – 32.53% |  73 | 0.521 | -24.6 |

**Pattern:** within each N, the highest P(next > 0) is in **Q4** (above-average but not extreme cumulative run-ups), not Q5 (the most extreme). For N=3 and N=4, Q5 actually drops back to or below baseline, with mean next-day return turning slightly negative for N=4 Q5. This is the "exhaustion" signal at the magnitude level — consistent with the N=7 dip in the count-based view above.

The headline takeaway from this view is that **streak count alone does discard useful information**. The conditional structure is closer to "moderately strong run-ups continue, very strong run-ups don't." But the N=4 Q4 bucket has only 73 observations, so the 0.685 figure should be treated as suggestive, not conclusive.

---

## Caveats

- **Thin samples for long streaks.** N ≥ 6 buckets on either side have n < 60; the N=7 negative bucket has n = 1. Don't trade off these.
- **Multiple-comparisons.** Reporting a one-sided p < 0.05 from any of 8 buckets is not strong evidence of a real effect. Bonferroni-corrected, none of the buckets clear the bar.
- **Leveraged-ETF path dependence.** QQQ3.L has daily-rebalance decay and amplified vol. Streak structure here may not transfer to the unlevered NDX, and would not transfer to multi-day holding periods on QQQ3.L itself.
- **Single regime.** The 2012–2026 window is dominated by a strong Nasdaq bull market plus the 2022 leveraged drawdown. Findings should not be extrapolated beyond that regime mix.
- **No transaction-cost analysis.** This is descriptive, not a backtest. A naive "buy after 3 up days, hold 1 day" strategy would have to clear UK FX/spread costs and slippage on a sub-1bp/day signal — almost certainly negative net.

---

## What would change the conclusion

If a follow-up wants to rescue the streak-momentum hypothesis, the candidates are:

1. **Condition on volatility regime.** Compute the same buckets within high/low realized-vol terciles. Streak persistence may exist only in the low-vol regime.
2. **Use intraday or overnight returns separately.** The close-to-close return mixes overnight gap and intraday drift, which have different autocorrelation structures for ETFs that trade off-hours from their underlying.
3. **Look at multi-day forward returns, not just N+1.** A signal that doesn't show up at one day may show up cumulatively over 5 days, especially if it's drift rather than serial dependence.
4. **Pair with a magnitude threshold.** The Q4 (moderate run-up) bucket result is the most interesting subset to pursue, not the count-only framing.

The current finding does not justify building a trading strategy off "buy QQQ3.L after N up days" alone.
