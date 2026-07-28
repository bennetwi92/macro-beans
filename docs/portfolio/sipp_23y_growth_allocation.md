# A 23-year SIPP built for compound growth — five funds, one monthly instruction

This note sets out the allocation for a self-invested personal pension funded by a
monthly contribution stream and left to compound for 23 years, to the normal minimum
pension age of 57 in 2049. The mandate is deliberately aggressive: the account holder
treats a −40% year as a buying opportunity and intends to keep contributing through
one, so no tail constraint is imposed and the portfolio is optimised for expected
compound growth alone. The result is five accumulating LSE-listed funds, bought by a
single monthly instruction, rebalanced out of contributions, and left alone.

> **Version note (rev. 1, 28 July 2026).** Companion to the five-year ISA notes in
> this directory, but a separate mandate with a separate engine: a contribution
> stream over 23 years is a different optimisation from a lump sum over five.

*Not financial advice and not a personal recommendation. Capital is at risk. The
capital-market assumptions are a transparent prior, not a forecast.*

**Method:** Expected returns come from the building-block capital-market assumptions
in `portfolio_optimiser/config/cma.toml`, net of each fund's ongoing charge. The
covariance is a Ledoit-Wolf shrinkage estimate on proxy-spliced GBP total returns from
April 2008 to July 2026 (220 months), a window that contains the 2008 crash rather than
starting after it. Weights are the equal-weight ensemble of two return-aware optimisers
— the convex geometric (Kelly) solution and a Black-Litterman posterior — each first put
through Michaud resampling. The recommendation is then stress-tested by a stationary
block bootstrap (Politis–Romano, mean block 12 months, 20,000 paths) of the real return
history recentred onto the assumptions, so fat tails and clustered drawdowns survive
into the projection. Every figure is re-derived with the assumed factor premia set to
zero.

**Files:**
- Driver: `portfolio_optimiser/report/build_sipp_23y.py`
- Lifecycle engine: `portfolio_optimiser/optimiser/lifecycle.py`
- Mandate: the `[sipp]` block of `portfolio_optimiser/config/constraints.toml`
- Weights and instruction ladder: `portfolio_optimiser/outputs/sipp_23y/targets_recommended.csv`
- All eight methods side by side: `portfolio_optimiser/outputs/sipp_23y/method_comparison.csv`
- Assumption sensitivity: `portfolio_optimiser/outputs/sipp_23y/sensitivity.csv` (resampled engine) and `sensitivity_raw.csv` (unsmoothed)
- Crash-timing study: `portfolio_optimiser/outputs/sipp_23y/sequence_risk.csv`
- Platform fee drag: `portfolio_optimiser/outputs/sipp_23y/fee_drag.csv`
- Charts: `wealth_23y.png`, `glidepath.png`, `sequence_risk.png` in the same directory
- Every number cited below: `portfolio_optimiser/outputs/sipp_23y/results.json`

---

## 1. Executive summary

| Metric | Value |
|---|---:|
| Expected return (geometric, net of fees) | **7.77%** |
| Expected return (arithmetic) | 8.91% |
| Expected volatility | 15.11% |
| Blended ongoing charge | **0.28%** |
| Holdings | **5** |
| Median outcome | **2.80×** total contributions |
| 5th-percentile outcome | 1.56× contributions |
| 95th-percentile outcome | 5.21× contributions |
| Probability of ending below what was paid in | **0.2%** |
| Median worst drawdown along the way | **−37%** |
| 5th-percentile worst drawdown | **−50%** |
| Money-weighted return (median path) | 8.09% |

**Recommendation: adopt the five-fund allocation in §3, buy it through one monthly
instruction, and do nothing else until the mid-2030s.** The single most useful
property of this portfolio is not its expected return — it is that nothing about it
requires attention. There is no rotation, no rebalancing trade, and no annual review
that changes anything before roughly year 15.

Two numbers deserve to sit next to the headline. The portfolio is expected to fall
about 37% at some point along the way, and in the worse fifth of paths, about 50%.
That is the price of the mandate, and it is being paid deliberately.

## 2. The mandate, as we understood it

- A newly opened SIPP with **no opening balance** and no transfers in.
- Funded by a **level monthly contribution** from contractor income, paid via an
  umbrella arrangement that passes back employer National Insurance.
- **23 years to access** at age 57 in 2049. The account holder was born in 1992, so the
  April 2028 rise in the normal minimum pension age from 55 to 57 applies in full.
- **Maximum sustainable risk.** Asked how they would behave in a deep bear market, the
  account holder chose "increase contributions — a −40% year is a sale."
- **Standalone.** The SIPP must be a complete portfolio in its own right, not a sleeve
  that depends on the ISA.
- **Low maintenance**, with the number of holdings decided by the optimisation rather
  than specified up front.

## 3. The portfolio

| # | Fund | Ticker | Weight | OCF | Role |
|---|---|---|---:|---:|---|
| 1 | Avantis Global Small Cap Value | `AVSG.L` | **29.2%** | 0.39% | Size × value × profitability — the largest single expected premium |
| 2 | Avantis Emerging Markets Equity | `AVEM.L` | **27.4%** | 0.36% | EM with a value/profitability tilt; de-concentrates a cap-weighted EM index |
| 3 | Xtrackers S&P 500 Equal Weight | `XDEW.L` | **17.8%** | 0.15% | US exposure with the mega-cap concentration removed |
| 4 | Avantis Global Equity | `AVCG.L` | **16.0%** | 0.22% | Value/profitability-tilted global core |
| 5 | iShares Core FTSE 100 | `CUKX.L` | **9.7%** | 0.07% | UK large-cap — cheapest developed market, and GBP, so no currency conversion |

All five are **accumulating** share classes, which matters on a platform that charges
per dividend reinvestment: nothing is ever paid out, so nothing needs reinvesting.
All five trade in GBP on the London Stock Exchange.

Sleeve composition: **100% equity.** See §6 for why the diversifiers were not included
— it was tested, not assumed.

Risk contribution is more concentrated than the weights suggest, which is worth
knowing: small-cap value supplies 33% of portfolio variance and EM value 28%, so two
holdings account for roughly three-fifths of the risk.

## 4. Execution — one instruction, ordered deliberately

The platform's regular-investing service is free, allows up to 25 monthly instructions
per account, has a £25 minimum per line, and runs on the 12th of each month. Two
mechanical details shape the design:

1. **Instructions are fixed pound amounts, not percentages.** The target weights have
   to be translated into a cash ladder, and that ladder needs revisiting only if the
   contribution level changes materially.
2. **If there is not enough cash, the platform fills instructions in the order they
   were added.** Contractor income varies with billable days, so the ladder is ordered
   largest first. A light month then degrades gracefully toward the core holdings
   instead of failing outright or starving the biggest sleeve.

Every line clears the £25 minimum with a wide margin at the planned contribution level,
and five lines sit far inside the 25-instruction cap.

**Rebalancing:** contributions alone. New money buys whichever holding is furthest
below target. Selling incurs a dealing charge where regular buying does not, and inside
a pension there is no tax reason to rebalance by selling. A corrective trade should only
be needed if a holding drifts more than 5 percentage points, or 25% in relative terms,
from its target and contributions cannot close the gap — realistically once every few
years, and less often early on when contributions are large relative to the pot.

## 5. What the money is expected to do

Modelled on 20,000 bootstrapped paths, expressed as multiples of total contributions so
the figures do not depend on the contribution level:

| | Multiple of contributions |
|---|---:|
| 95th percentile | 5.21× |
| 75th percentile | 3.59× |
| **Median** | **2.80×** |
| 25th percentile | 2.20× |
| 5th percentile | 1.56× |
| Passive global tracker, median | 2.14× |

The comparison against a passive global tracker deserves a caveat rather than a
victory lap — see §7.

**A note on what the horizon actually is.** A 23-year plan funded monthly does not
compound for 23 years. The first contribution does; the last compounds for one month.
The money's effective duration is roughly half the calendar horizon, which is why the
median outcome is 2.8× contributions rather than the ~6× that 23 years at 7.8% would
suggest for a lump sum. Quoting the calendar horizon as though the whole pot earned it
is one of the more common ways these projections mislead.

## 6. Did the diversifiers earn their place? No — and that was tested

The obvious question for an all-equity pension is whether gold, infrastructure or a
trend-following sleeve should be in it. Under a geometric objective this is not a
question about safety: cutting portfolio variance raises the compound growth term
directly, so a low-return but genuinely uncorrelated asset can improve growth even for
an investor who does not care about volatility. So the sleeves were given a fair
hearing rather than being excluded on mandate grounds.

The optimisation gave gold about 3% and listed infrastructure about 5% before the
minimum-holding threshold, and both fell below the 5% level at which a line justifies
the attention it costs forever. Forcing a 13% real-asset sleeve in — the equivalent of
the design-intent floors used for the ISA — costs **0.19 percentage points of expected
compound return** (7.29% against 7.48% for the unconstrained ensemble). That is the
price of the insurance, and for this mandate it was judged not worth paying.

**Managed futures could not be assessed at all, for an unwelcome reason.** The
trend-following fund used elsewhere in this repository, `JMFP.L`, no longer exists —
J.P. Morgan liquidated its Managed Futures UCITS ETF in November 2020, and the price
series stops in December 2020. The nearest LSE-listed replacement listed in April 2025
and has too little history, and quote data too erratic, to model honestly. There is
therefore currently no way to hold a modellable trend sleeve in this portfolio, and the
note says so rather than substituting something and hoping.

## 7. Is this just a tracker with extra steps?

Partly, and the honest answer needs the counterfactual.

Against a passive global tracker the portfolio wins on 99% of modelled paths. That
number should not be believed as stated, because both sides are recentred onto their
own assumptions — so it is very largely a restatement of the assumed value, size,
profitability and emerging-market premia rather than evidence about the world.

The useful test is to switch those premia off entirely and re-run everything:

| | With assumed premia | Premia set to zero |
|---|---:|---:|
| Expected geometric return | 7.77% | **5.99%** |
| Median outcome | 2.80× | 2.16× |
| Probability of beating the tracker | 99% | **55%** |

So if every factor premium in the assumptions turns out to be worth nothing, the
portfolio returns roughly 1.8 percentage points a year less and becomes a coin-flip
against a plain tracker rather than a near-certainty. It does not become a disaster,
because what remains is still diversified global equity at a low blended charge. That
asymmetry — meaningful upside if the premia are real, near-parity if they are not — is
the actual case for the tilt, and it is a much weaker claim than the 99% figure implies.

## 8. Why an early crash is survivable and a late one is not

For someone drawing down a pension, a crash early in retirement is the catastrophic
case. **During accumulation the asymmetry runs the other way**, and it runs strongly.
An identical −40% crash was dropped into the same simulated paths at different points:

| Crash lands in year | Impact on the pot at 57 |
|---:|---:|
| 1 | **−3.6%** |
| 3 | −10.1% |
| 5 | −15.6% |
| 10 | −26.2% |
| 15 | −33.3% |
| 20 | −38.2% |
| 23 | **−40.4%** |

A crash in year one costs almost nothing, because it falls on a nearly empty pot and
discounts every contribution still to come. The same crash in the final year costs
essentially its full magnitude, because by then the pot is large and there is no
remaining contribution stream to buy the recovery.

This is the quantitative licence for the account holder's stated instinct, and it has
two practical consequences. Early volatility is genuinely close to free and should not
be traded away. And the risk that matters is concentrated in the last decade, which is
what the glidepath in §9 addresses — and the only reason a glidepath is needed at all.

## 9. The glidepath

Hold the allocation above unchanged for the first **15 years**. From year 15, move
toward short-dated gilts on a straight line over **eight years**, reaching **30%
defensive** at 2049.

| | Median | 5th percentile |
|---|---:|---:|
| Static — never de-risks | baseline | baseline |
| Glidepath | **−3.9%** | **+1.6%** |

De-risking costs about 3.9% of the median outcome and improves the bad fifth of
outcomes by about 1.6%. That is a real trade, not a free lunch, and reasonable people
would price it differently. It is recommended here because the loss being insured
against is concentrated and irreversible: arriving at 57 having just taken a 40% hit,
with no contribution stream left to recover it, is the one scenario in this plan with
no remedy.

The schedule is expressed in years *before* the target date rather than as fixed
calendar dates, so if the normal minimum pension age moves again — a real possibility,
given the long-discussed idea of linking it to state pension age minus ten — the whole
path re-points with a one-line change.

## 10. Costs

The platform charges a **flat monthly fee**, not a percentage. This is the right shape
of charge for a pot starting from nothing and compounding for two decades, because the
drag falls away as the pot grows:

| Year | Platform fee as % of pot |
|---:|---:|
| 1 | 0.71% |
| 5 | 0.07% |
| 10 | 0.03% |
| 23 | **0.007%** |

The first year is genuinely expensive in percentage terms. By year five it is
immaterial, and over the full horizon the flat fee costs less than a percentage-based
platform charging even 0.15%. Adding the 0.28% blended fund charge, total cost runs
from about 0.99% in year one to about 0.29% by the end.

## 11. How much the answer depends on the assumptions

It is worth separating two questions that sensitivity analysis usually blurs: which
assumption changes *what you hold*, and which changes *what you earn*. They have
different answers here.

| Assumption shifted ±1ppt | Largest weight move | Expected-return range |
|---|---:|---:|
| Broad developed-equity premium | **0.9 pts** | **1.95 pts** |
| Value premium | **9.8 pts** | 0.55 pts |
| Quality / profitability premium | 8.6 pts | 0.71 pts |
| UK value premium | 8.1 pts | 0.30 pts |
| Emerging-market premium | 5.7 pts | 0.41 pts |

The broad equity premium dominates the *return* and barely touches the *allocation* —
it lifts every holding at once, so the mix is unaffected. That is the honest headline:
this plan's outcome depends far more on whether global equities deliver than on any
factor judgement in it.

The factor premia are the reverse. The value premium is the assumption the *allocation*
leans on hardest, moving the largest single weight by 9.8 percentage points, but it
moves expected return across only 0.55 points. No single assumption moves any weight by
more than about 10 points, which is the threshold at which an allocation should be
treated as an artefact of its inputs rather than a conclusion.

That stability is a product of the resampling, and it is worth showing the contrast.
Run once on point estimates, the same optimiser is wildly unstable: a ±1 point shift in
the value premium moves a weight by **35 percentage points**, because the unsmoothed
optimiser produces corner solutions that flip between assets when their assumed returns
cross. Both tables are published — `sensitivity.csv` for the engine actually used, and
`sensitivity_raw.csv` for the unsmoothed version — because quoting only the smoothed one
would hide how much work the smoothing is doing.

## 12. Risks and honest limitations

1. **The drawdown is real.** A −37% median worst drawdown means the expected experience,
   not the bad case. The bad case is −50%. On a pot that will eventually be substantial,
   that is a large absolute sum to watch disappear, and the plan only works if the
   contributions keep going during it.
2. **The factor tilt may not pay.** §7 quantifies this: roughly 1.8 percentage points a
   year, and near-parity with a tracker rather than outperformance.
3. **Two holdings carry ~60% of the risk.** Small-cap value and EM value are correlated
   with each other and both are deep-value strategies. They can underperform together,
   for a decade at a time; 2010–2020 is the obvious example.
4. **The history starts in April 2008.** It captures the 2008 crash and the 2009 trough
   but not the October 2007 peak, so the very worst peak-to-trough experience is
   slightly understated even in the bootstrap.
5. **Every crash in the sample recovered — and the simulation inherits that.** Because
   the bootstrap resamples contiguous blocks of April 2008 to July 2026, it carries
   forward the mean reversion of a period in which every drawdown was followed by a
   recovery. It is correspondingly harsh about a single bad *year* and comparatively
   mild about a bad *decade* (Appendix A quantifies both). A prolonged flat market of
   the kind Japan experienced after 1990 is not represented anywhere in this history,
   and would hurt an all-equity accumulation more than any figure in this note suggests.
   The bootstrap also recentres history onto the assumed returns: it inherits the real
   *shape* of returns but its *level* is an assumption.
6. **No allowance for a change in circumstances.** The model assumes level contributions
   for 23 years. Contract work is not level. A prolonged gap between assignments changes
   the outcome far more than any choice in this note.
7. **Emerging-market value carries governance and political risk** that a volatility
   estimate does not capture well.
8. **The rules will change.** Twenty-three years is long enough for pension taxation to
   be rewritten more than once.

## 13. Recommendation

Adopt the five-fund allocation, set up one monthly instruction with the lines ordered
largest first, and review in the mid-2030s rather than annually. The allocation is
built to be held through exactly the kind of market that makes people abandon
allocations, and the analysis in §8 is the reason to hold it: for the next decade and a
half, a crash is closer to an opportunity than a threat.

The one thing worth checking sooner is whether a liquid, long-history trend-following
fund becomes available on the London market. If one does, §6 should be re-run — the
case for it was never rejected on merit, only on the absence of anything investable.

## Important information

This note is portfolio modelling for a personal account. It is not financial advice,
not a personal recommendation, and not a regulated activity. Capital is at risk and
past performance does not indicate future results. Pension rules, tax treatment and the
normal minimum pension age can change, and the tax treatment of pensions depends on
individual circumstances. The capital-market assumptions are a stated prior, not a
forecast; §7 and §11 quantify what happens if they are wrong. Anyone other than the
account holder should treat every figure here as illustrative of a method, not as
guidance for their own circumstances.

---

### Appendix A — Methodology

**Expected returns.** Building-block construction: a cash rate plus an equity risk
premium plus explicit factor and geography premia, so a single assumption can be revised
and propagate rather than thirteen correlated point estimates being hand-tuned. Returns
are stated nominal, GBP, arithmetic, then converted to geometric internally using the
covariance-implied variance. Each fund's ongoing charge is deducted.

**Covariance.** Ledoit-Wolf shrinkage toward a constant-correlation target, on
winsorised month-end GBP total returns, April 2008 to July 2026. Young funds are spliced
onto longer-history proxies in return space, so no level adjustment is needed. Two proxy
choices were corrected for this build: the quality proxy moved from `QUAL` (2013) to
`SPHQ` (2005) and the UK proxy from `ISF.L` (2009) to `EWU` (1996), because in both
cases the shorter series was the binding constraint on how far back the whole panel
could reach — and excluding 2008 from a 23-year risk model is not defensible.

**Optimisation.** Maximise `w'μ − ½w'Σw`, the geometric growth (Kelly) objective, long
only and fully invested, with a 35% per-holding cap. This objective is self-disciplining:
variance is penalised directly, so no separate risk constraint is needed for a mandate
that does not want one.

**Estimation-error control.** Michaud resampling with 250 draws, applied to both the
plain geometric optimiser and the Black-Litterman posterior, then the two resampled
solutions averaged. Averaging smoothed and unsmoothed solutions was rejected: the
unsmoothed ones are corner solutions and would dominate the blend with exactly the
fragility resampling exists to remove.

**Return-blind cross-checks.** Hierarchical Risk Parity and Equal Risk Contribution are
computed and published but excluded from the recommendation. Over a universe containing
low-volatility assets both allocate by risk alone, irrespective of expected return —
a legitimate question, but not the one this mandate asks.

**Simulation.** Stationary block bootstrap with geometric block lengths averaging 12
months, wrapping at the sample end, resampling whole cross-sections so correlation
structure — including its tendency to converge in a crash — is preserved exactly. Blocks
are drawn from history recentred so each column's mean equals its assumed return, which
keeps volatility, skew, kurtosis and serial dependence from the data while taking the
level of returns from the stated assumptions. 20,000 paths, monthly rebalancing to
target, contributions invested at the start of each month, the flat platform fee
deducted in cash terms.

**Why the Gaussian model is also reported — and what the comparison actually showed.**
The expectation going in was that the bootstrap would be uniformly harsher than a normal
model. It is not, and the difference is instructive. The two produce almost identical
portfolio volatility (15.17% against 15.11%), so nothing below is a spread effect.

| | Block bootstrap | Normal model |
|---|---:|---:|
| Worst 12 months, 1st percentile | **−44.7%** | −39.4% |
| Worst 3 years, 1st percentile | −47.6% | **−51.0%** |
| Worst 5 years, 1st percentile | −47.4% | **−54.0%** |
| Dispersion of terminal wealth (sd of log) | **0.53** | 0.72 |

The bootstrap is markedly worse over a single year — the monthly return history is
left-skewed (−0.40) and fat-tailed (excess kurtosis 1.00), and block resampling keeps
losing months adjacent, which a Gaussian cannot reproduce. But over three years and
longer it is *milder*, and terminal dispersion is substantially narrower. The reason is
mean reversion: in the April 2008 to July 2026 sample every crash was followed by a
recovery, and resampling contiguous blocks carries that pattern forward, whereas iid
normal draws let losses compound independently.

This cuts both ways and the note reports both numbers rather than the convenient one.
It also implies a specific blind spot, recorded as limitation 5 in §12: a sample in
which every crash recovered cannot represent a market that simply goes nowhere for a
decade.

### Appendix B — Per-holding assumptions (net of fees)

| Fund | Expected arithmetic return | Volatility | OCF |
|---|---:|---:|---:|
| Avantis Global Small Cap Value | 9.61% | 16.8% | 0.39% |
| Avantis Emerging Markets Equity | 9.14% | 16.2% | 0.36% |
| Avantis Global Equity | 9.28% | 12.3% | 0.22% |
| iShares Core FTSE 100 | 8.43% | 12.5% | 0.07% |
| Xtrackers S&P 500 Equal Weight | 7.35% | 16.3% | 0.15% |
| *Considered, not selected:* iShares World Quality | 7.25% | 13.5% | 0.25% |
| *Considered, not selected:* iShares Japan GBP-Hedged | 7.36% | 15.7% | 0.64% |
| *Considered, not selected:* iShares Global Infrastructure | 5.85% | 19.7% | 0.65% |
| *Considered, not selected:* iShares Physical Gold | 3.88% | 18.8% | 0.12% |
| *Glidepath destination:* iShares UK Gilts 0–5yr | 3.93% | 2.1% | 0.07% |
