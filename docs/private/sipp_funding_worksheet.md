# SIPP funding worksheet — personal figures (PRIVATE, not published)

Companion to the public note `docs/portfolio/sipp_23y_growth_allocation.md`, which
carries the same analysis in percentage terms only. **This file holds the personal
detail — day rate, contribution amounts, projected balances — and is excluded from the
public site** by the `private` entry in `EXCLUDE_DIRS` in `scripts/site/build_reports.py`.
Verify that exclusion still holds after any change to the site build.

*Not financial advice. Tax figures are 2026/27 rates and will change over a 23-year plan.*

---

## 1. The contribution arithmetic

| Input | Value |
|---|---:|
| Day rate | £800 |
| Assumed billable days per year | 225 |
| Assignment rate value, annual | £180,000 |
| Contribution — cost to take-home pay | **£40/day** |
| Marginal relief rate (45% income tax + 2% NI) | 47% |
| Gross salary sacrificed for £40 net cost | £75.47/day |
| Employer NI (15%) + apprenticeship levy (0.5%) passed back by Paystream | ×1.155 |
| **Gross landing in the SIPP** | **~£87/day** |

**Modelled at £1,500/month (£18,000/year), which is deliberately conservative.** The
arithmetic above supports roughly £87/day, or £19,600/year at 225 days. The model uses
the lower figure so that a light billing year does not invalidate the projection. If
billing holds up, the real outcome should land modestly above everything in the public
note.

Sense-check on the "almost double" description: £40 of take-home foregone produces
about £87 in the pension, so the multiple is closer to **2.2×** than 2×. The leverage
comes from three places at once — 45% income tax relief, 2% employee NI, and the
employer NI the umbrella passes back rather than keeping.

## 2. Projected outcome, in pounds

Modelled on 20,000 bootstrapped paths, £1,500/month for 276 months, nil opening
balance, ii platform fee deducted in cash:

| | Nominal at 2049 | In today's money (2.5% inflation) |
|---|---:|---:|
| Total contributed | £414,000 | — |
| 5th percentile | £645,000 | £366,000 |
| 25th percentile | £911,000 | £516,000 |
| **Median** | **£1,158,000** | **£656,000** |
| 75th percentile | £1,486,000 | £842,000 |
| 95th percentile | £2,158,000 | £1,223,000 |
| Passive global tracker, median | £888,000 | £503,000 |
| If all factor premia are worth zero, median | £896,000 | £508,000 |

Median money-weighted return 8.09% a year. Probability of ending with less than was
paid in: 0.2%.

## 3. The monthly instruction ladder

Set these up once, in this order. ii fills instructions in the order they were added
when there is not enough cash, so a light month degrades toward the core rather than
starving the largest holding.

| Order | Fund | Ticker | Monthly | % |
|---:|---|---|---:|---:|
| 1 | Avantis Global Small Cap Value | `AVSG.L` | **£437** | 29.2% |
| 2 | Avantis Emerging Markets Equity | `AVEM.L` | **£411** | 27.4% |
| 3 | Xtrackers S&P 500 Equal Weight | `XDEW.L` | **£267** | 17.8% |
| 4 | Avantis Global Equity | `AVCG.L` | **£240** | 16.0% |
| 5 | iShares Core FTSE 100 | `CUKX.L` | **£145** | 9.7% |
| | **Total** | | **£1,500** | 100% |

Every line clears ii's £25 minimum by a wide margin — the smallest is £145, so
contributions could fall by 80% before any line became unexecutable.

**Practical setup notes:**
- ii's regular investing runs on the **12th of the month**. Paystream contributions need
  to have landed before then. Build a **one-month cash buffer** in the SIPP at the start
  so the 12th is never short — otherwise the first light month silently part-fills.
- If the contribution level changes materially (a new day rate, a change in billable
  days), rescale all five amounts proportionally. The percentages are what matter.
- Do **not** set up dividend reinvestment. All five are accumulating share classes, so
  there is nothing to reinvest, and ii charges £0.99 per reinvestment on Core and Plus.

## 4. Platform plan

| Pot size | Plan | Cost | Drag |
|---|---|---:|---:|
| Up to £100k (roughly years 1–5) | **ii Core** | £5.99/mo | 0.71% in year 1, 0.07% by year 5 |
| Above £100k | **ii Plus** | £14.99/mo | 0.18% at £100k, 0.016% at £1m |

Switch to Plus when the pot passes £100,000 — projected around **year 5 or 6**. The flat
fee is the right structure here: over the full horizon it costs less than a
percentage-based platform charging even 0.15%, and by 2049 it is 0.007% of the pot.

Year one is the expensive year in percentage terms (0.71% platform + 0.28% funds ≈
0.99% all-in). That is unavoidable on a pot starting from nothing and is not a reason to
choose a percentage-fee provider, which would be more expensive for 22 of the 23 years.

## 5. Allowances and tax — what to watch

**Annual allowance: £60,000.** At ~£19,600/year the headroom is roughly £40,000. Not a
constraint now, but worth re-checking if the day rate rises materially or a lump sum is
added — including via carry-forward of unused allowance from the previous three years,
which is available and currently unused.

**Tapered annual allowance: not in scope, with room to spare.** The taper only bites if
*threshold income* exceeds £200,000. Threshold income here is roughly £154,000 of umbrella
gross salary less the ~£19,600 sacrificed, so about £134,000 — comfortably below the
trigger, and because threshold income is the first test, the £260,000 adjusted-income
test never comes into play. This stays true unless the day rate rises by roughly 45%.

**Lump Sum Allowance: £268,275 — this one will bind.** Tax-free cash is 25% of the pot
*capped at the LSA*, so the cap starts biting once the pot exceeds about £1,073,100. The
median projection is £1,158,000, so on the central path the tax-free cash is capped
rather than a clean 25%. The allowance is currently frozen in nominal terms; if it stays
frozen to 2049 it will bind on most of the distribution, not just the median. Nothing to
do about it now — and it is a good problem — but it argues against assuming "25% tax
free" when planning the drawdown, and it is a reason to keep building the ISA alongside
rather than routing everything into the pension.

**Inheritance tax from 6 April 2027.** Unused pension funds and most death benefits come
into the estate for IHT from that date; HMRC's technical note was published 11 May 2026
and personal representatives, not scheme administrators, will handle reporting. This
removes the old "leave the pension untouched as an IHT-free legacy" logic. It does not
change the allocation, but it changes the drawdown order later in life.

**Normal minimum pension age.** 57 from 6 April 2028 is legislated and applies in full to
anyone born on or after 6 April 1973. The live risk is a future link to state pension age
minus ten, which would push access to 58. The glidepath is written as "years before the
target date" precisely so that this is a one-line change rather than a rebuild.

## 6. Flagged separately: the ISA holds a fund that no longer exists

This came out of the SIPP data work and is not part of this mandate, but it needs
raising because the ISA is already invested.

`docs/portfolio/isa_5y_build_sheet.md` line 5 lists **JPM Managed Futures (`JMFP.L`) at
9.3%** of the ISA. **J.P. Morgan liquidated that ETF in November 2020.** Its price series
stops in December 2020, which is how it surfaced — it was truncating the return panel.

Three things follow:
1. Check what actually happened to that 9.3% when the ISA was built. If it could not be
   bought, the cash either sat idle or was absorbed elsewhere, and in either case the
   live ISA no longer matches the modelled allocation.
2. The ISA's modelled risk figures assumed a crisis-alpha diversifier that is not there.
   The realised portfolio is more equity-directional than the note claims.
3. There is currently no liquid, long-history LSE-listed trend fund to replace it. The
   nearest, `DBMG.L`, listed in April 2025 and its quote data is not yet usable.

`portfolio_optimiser/config/universe.toml` now records `sipp_eligible = false` for JMFP
with the reason, so it cannot silently reappear. The ISA configuration was deliberately
left otherwise untouched — re-running that mandate is a separate decision.

## 7. Review triggers

Nothing here needs an annual review. Revisit only if one of these happens:

- Contribution level changes materially → rescale the five instruction amounts.
- Pot passes £100,000 → switch ii Core to Plus.
- **Year 15 (2041)** → begin the glidepath in §9 of the public note.
- Normal minimum pension age changes → re-point `target_year` in
  `portfolio_optimiser/config/constraints.toml` and re-run the driver.
- A liquid, long-history trend-following UCITS ETF lists in London → re-run the
  diversifier test in §6 of the public note.
- Any of the Avantis funds closes or changes mandate → the two Avantis lines are 45% of
  the portfolio between them, which is real single-provider concentration.

Regenerate every figure in both notes with:

```bash
/usr/local/bin/python3 -m portfolio_optimiser.report.build_sipp_23y --refresh
```
