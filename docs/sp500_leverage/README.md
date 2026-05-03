# S&P 500 monthly-return probability under LSE leveraged products

**Question.** I have £100/month to drip-feed into the S&P 500. The LSE offers
leveraged daily trackers (1x CSPX, 2x products like 2USL, 3x products like 3USL/3LUS).
What's the probability that any given month is positive at each leverage level,
and what does that imply for a monthly DCA?

**TL;DR.** Leverage *slightly reduces* the probability of a positive month
(66% → 63% → 62% as you go from 1x to 2x to 3x). The first-order effect of
leverage isn't a higher hit-rate — it's a much fatter left tail, dominated by
volatility drag and financing costs. For a passive £100/month plan, **1x is the
rational default**; 2x/3x are tactical instruments, not DCA vehicles.

## Method

- Daily total-return data: `^SP500TR` from Yahoo, 1988-01-05 to 2026-05-01
  (9,654 trading days, 460 calendar months).
- Risk-free / financing proxy: `^IRX` (13-week T-bill yield), forward-filled
  daily.
- Synthetic NAV for each product, daily-compounded:

  ```
  daily_nav_change = L * r - (L-1) * rf_daily - (L-1) * swap_spread/252 - TER/252
  ```

  | Product | Leverage | TER  | Swap spread |
  |---------|---------:|-----:|------------:|
  | 1x  CSPX (iShares Core S&P 500 UCITS) | 1x | 0.07% | 0.00% |
  | 2x  e.g. 2USL                          | 2x | 0.75% | 0.40% |
  | 3x  e.g. 3USL / 3LUS                   | 3x | 0.99% | 0.50% |

- Monthly return = `(NAV_eom / NAV_prev_eom) - 1`.
- DCA: invest £100 at the start of each month, compound at realised monthly
  returns, evaluate over rolling 5y/10y/20y windows.

Code: `scripts/sp500_leverage/leverage_analysis.py` and `plot_leverage.py`.
Outputs: `data/sp500_leverage/`.

## Results

### Monthly return statistics (1988–2026, 460 months)

| Product | P(>0) | Mean | Median | Std | Best | Worst | Ann. ret | Ann. vol | CAGR | Max DD |
|---------|------:|-----:|-------:|----:|-----:|------:|---------:|---------:|-----:|-------:|
| 1x CSPX | **66.1%** | 0.99% | 1.38% | 4.2% | +12.8% | −16.8% | 12.5% | 14.6% | 11.3% | −51.0% |
| 2x      | **63.0%** | 1.57% | 2.33% | 8.5% | +25.4% | −34.7% | 20.6% | 29.5% | 15.4% | −84.9% |
| 3x      | **61.5%** | 2.11% | 3.17% | 12.9% | +37.6% | −51.7% | 28.5% | 44.6% | 16.0% | **−97.4%** |

The 3x line essentially gets wiped out twice on this synthetic history (GFC and
COVID crash) and the max drawdown of −97% means any lump sum invested at the
wrong time would have been functionally destroyed. CAGR climbs much less than
linearly with leverage — 1x → 2x adds ~4% CAGR, 2x → 3x adds <1% — because
volatility drag eats the rest.

### Probability total return > 0 over rolling N-month windows

| Window | 1x | 2x | 3x |
|-------:|---:|---:|---:|
| 1 mo   | 66.1% | 63.0% | 61.5% |
| 3 mo   | 72.9% | 68.8% | 66.4% |
| 6 mo   | 76.7% | 72.5% | 70.8% |
| 12 mo  | 83.5% | 79.3% | 74.2% |
| 24 mo  | 87.0% | 81.5% | 78.7% |
| 36 mo  | 85.9% | 80.9% | 78.1% |
| 60 mo  | 87.8% | 74.8% | 72.3% |
| 120 mo | 93.0% | 86.8% | 82.7% |

Even over a **10-year** window, 1-in-6 starts leave 3x underwater, vs. 1-in-14
for 1x. The non-monotonicity at 5y for 2x/3x is the GFC bite — start in 2007,
finish in 2012, still negative.

### £100/month DCA terminal values

| Years | Product | Invested | P(beat invested) | Median  | P10    | P90     | Min   | Max     |
|------:|---------|---------:|-----------------:|--------:|-------:|--------:|------:|--------:|
|  5  | 1x | £6,000  | 88.8% | £8,157  | £5,855 | £10,091 | £3,741 | £12,291 |
|  5  | 2x | £6,000  | 82.5% | £9,745  | £4,676 | £14,294 | £1,767 | £20,942 |
|  5  | 3x | £6,000  | 80.6% | £10,980 | £3,652 | £20,066 | **£739** | £34,282 |
| 10  | 1x | £12,000 | 96.2% | £21,038 | £14,554 | £29,567 | £8,151 | £37,652 |
| 10  | 2x | £12,000 | 89.4% | £28,809 | £11,955 | £55,100 | £3,596 | £81,791 |
| 10  | 3x | £12,000 | 80.9% | £33,791 | £8,853  | £93,174 | £1,336 | £161,977 |
| 20  | 1x | £24,000 | 100.0% | £58,305 | £44,820 | £94,375 | £32,916 | £110,424 |
| 20  | 2x | £24,000 | 98.6%  | £76,800 | £35,316 | £213,890 | £18,202 | £291,370 |
| 20  | 3x | £24,000 | 82.8%  | £81,640 | £18,063 | £345,274 | £6,341 | £553,069 |

Read this carefully:

- **Median** terminal values *do* climb with leverage at every horizon.
- **P10** (10th-percentile outcome) **falls** with leverage at every horizon.
  Over 20 years, the unlucky decile of 3x DCAers ends at £18k on £24k invested
  — a *real loss after two decades of saving*. The unlucky decile of 1x ends
  at £45k, comfortably ahead.
- The **minimum** outcome at 3x over 5 years is **£739 on £6,000 invested** —
  a ~88% loss from a *dollar-cost-averaged* (i.e. supposedly defensive) plan.
- 1x reaches 100% positive over 20-year windows in this sample. 3x does not.

## Why does leverage hurt P(positive month)?

Three compounding effects:

1. **Volatility drag.** The geometric mean of `1 + L·r` is below `L` times the
   geometric mean of `1 + r`. Variance is amplified `L²`, so 3x has 9× the
   variance contribution to drag.
2. **Financing.** The product borrows `(L-1)` units of NAV at roughly the
   risk-free rate plus a swap spread. Over the 1988–2026 period this averaged
   ~4.4%/yr; at 3x that's ~9% headwind before TER.
3. **TER.** 1bp here, 99bps there — small but non-zero.

The net is that the *median* daily return drops below `L × median(r)` by an
amount that grows fast in `L`. Over a month (≈21 trading days) those small
drags compound into a noticeable shift of the distribution leftwards near
zero, which is exactly where the P(>0) line sits.

## Caveats

- **Synthetic, not realised.** Real LSE 2x/3x S&P 500 ETPs (2USL, 3USL, 3LUS)
  only launched around 2012. Pre-2012 numbers are a backtest of the daily-
  rebalance methodology, not actual NAVs.
- **Financing assumption.** I used USD T-bill yields for the borrowed leg;
  GBP-share-class products will see slight tracking differences plus FX in/out
  of the underlying USD exposure. Not modelled.
- **Currency.** A GBP investor in USD-denominated S&P exposure also takes
  GBPUSD risk. CSPX, 2USL, 3USL are all USD-priced UCITS ETPs. The
  GBP-hedged variants (e.g. GSPX, IGUS for 1x) carry a hedge cost (~0.3%/yr).
- **Tax/wrapper.** Holding inside an ISA/SIPP avoids CGT and dividend tax.
  Outside a wrapper a daily-rebalance ETP can generate complicated tax
  treatment (ETN-like for some structures).
- **Regime sensitivity.** The 1988–2026 sample includes one of the strongest
  equity bull markets in history. Forward returns may not look like this.

## Practical takeaway for £100/month

- For a passive monthly drip, **1x (CSPX, VUAG, VUSA, SPXP, etc.) dominates**
  on a risk-adjusted basis. The probability of a positive month is *higher*
  than at 2x/3x, the tails are tolerable, and the 20-year DCA is essentially
  certain to beat invested capital on this sample.
- 2x products buy you ~4% extra CAGR for ~double the volatility and a −85%
  worst-case drawdown. It's a real risk premium, but it's not a "DCA upgrade"
  — it's a different product.
- 3x products buy you almost no extra CAGR over 2x (≈0.6%) for another 50%
  more vol and a near-total drawdown in 2008/2020. They're designed for
  short-horizon tactical use; using them as a monthly savings vehicle would
  be a mistake on this evidence.
- If you want some leveraged sleeve, a **small** allocation (e.g. 10–20% of
  monthly contribution) into 2x while keeping the rest in 1x captures most
  of the upside skew without committing the whole pot to the bad left tail.

## Files

- `scripts/sp500_leverage/leverage_analysis.py` — main simulator + tables.
- `scripts/sp500_leverage/plot_leverage.py` — overview chart.
- `data/sp500_leverage/nav_series.csv` — daily synthetic NAVs.
- `data/sp500_leverage/monthly_returns.csv` — monthly returns per product.
- `data/sp500_leverage/summary_stats.csv` — distributional stats table.
- `data/sp500_leverage/rolling_p_positive.csv` — P(>0) over rolling windows.
- `data/sp500_leverage/dca_terminal_values.csv` — DCA terminal-value stats.
- `data/sp500_leverage/leverage_overview.png` — NAV / drawdown / histogram / P(+) chart.
