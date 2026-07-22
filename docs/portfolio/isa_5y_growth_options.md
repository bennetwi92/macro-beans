# Five-Year ISA Portfolio — £20,400 Core + Rotating Themes

This note cements a single, buildable portfolio for a ~£20,400 Trading 212 Stocks & Shares ISA transferred out of a Nutmeg (ex-JP Morgan) managed account, to be run yourself over a five-year horizon and then withdrawn in full. It is a July-2026 refresh of the earlier three-option proposal, rebuilt around two decisions you made: a **Balanced** risk budget, and an explicit split between a **core that is meant to compound untouched (~80%)** and a **thematic sleeve you rotate roughly once a year (~20%)**. The whole thing is one Trading 212 Pie of London-listed, mostly GBP building blocks, costs **~0.36% a year** (roughly a third of a typical Nutmeg fee), and is deliberately tilted *away* from the crowded US mega-cap / AI-semiconductor trade.

> **Version note (rev. July 2026).** This is the revised edition, updated after an
> independent three-analyst review of the proposal. The **portfolio and its modelled
> numbers are unchanged**; what changed is the *honesty of the framing* — the downside
> is now stated as the model actually reports it, the "hedge" and "diversifier" claims
> are qualified, the glidepath is made explicit, and two genuine investment decisions
> (the silver holding and the AI-capex tilt of the theme sleeve) are surfaced for you
> to decide. The review, its findings, and exactly what was and wasn't actioned are in
> the companion note [`isa_5y_analyst_review.md`](isa_5y_analyst_review.md).

*Prepared for the account holder · investment proposal · illustrative, not a personal recommendation. Capital is at risk. Figures are modelled, not guaranteed. Please read the Important Information at the end.*

---

## 1. Executive summary

You have transferred roughly **£20,400** of previous-year ISA savings from a Nutmeg managed account into a **Trading 212 Stocks & Shares ISA** to run yourself. The objective is to grow the pot over **five years**, at which point you withdraw it all. You are comfortable with risk (a Nutmeg 7/10) but chose a **Balanced** structure here — protecting the floor matters when there is a hard date at which you must sell. You want part of the money to **sit and compound indefinitely**, and part to **rotate each year** to capture themes — and, importantly, you asked for **second-order themes that are not already crowded**, plus a hedge against a stumble in US/AI strength.

The result is **one portfolio, in two buckets**:

- a **~80% CORE** that compounds untouched — a global *value / quality / small-value* equity engine, a dedicated **UK** sleeve (the cheapest developed market, and GBP so no FX fee), an **emerging-market value** sleeve, a **de-concentrated** slice of the S&P 500 (equal-weight), plus a **crisis-hedge pair** (gold + a trend-following fund, ~16%) that genuinely cushions falls and a listed-**infrastructure** slice (inflation-sensitive, but equity-like — not a crash cushion);
- a **~20% ROTATING sleeve** of four fresher, less-saturated themes, ~5% each, that you review and rotate annually.

| Metric (modelled, after fees) | Value |
|---|---:|
| Expected return | **~6.9% / yr** (geometric) · 7.3% arithmetic |
| Expected volatility | 9.5% |
| 1-year 95% expected-shortfall (CVaR) | 13.9% |
| Typical worst 5-yr dip | ~13% |
| Deep (1-in-20) 5-yr dip | ~26% |
| **Worst modelled 5-yr dip** | **~46%** (severe path — see §6/§9) |
| Median value after 5 years | **~£28,500** (×1.40) |
| Poor five years (5th percentile) | **£19,470 (×0.95 — a small nominal *loss*)** |
| Strong five years (95th percentile) | £41,898 |
| Roughly-even odds of beating a passive global tracker | ~57% (premia-conditional — see §6) |
| Blended ongoing charge (TER) | **0.36% / yr** (~£73 on £20,400) |

*The geometric figure is quoted as ~6.9%; the model reports 6.86% on a mean-variance basis and 6.96% as the Monte-Carlo realised mean — different objects, same order. The 5th-percentile is a **small nominal loss**, and the worst simulated five-year drawdown is **~46%**; both come from a near-normal model that, as §9 notes, understates genuine crashes.*

**Recommendation: build the Pie in §4** — with two changes to weigh at build time and at your first rotation (the silver holding and the AI-capex tilt of the theme sleeve; see §7 and §8). It matches the Balanced risk level you chose, keeps a genuine growth engine while holding a **~16% genuine crisis-hedge sleeve (gold + trend)** — plus ~10% inflation-sensitive, equity-like infrastructure — and expresses your "interesting, not-yet-crowded" brief through the rotating sleeve, without betting the portfolio on it. Note that "Balanced" here still means **~74% risk assets and no conventional bonds until the glidepath** (§10); the low 9.5% volatility relies on diversification that tends to compress in a genuine crisis.

---

## 2. Your mandate, as we understood it

| Parameter | Your instruction | How it shaped the design |
|---|---|---|
| Amount | ~£20,400, **transferred** from a Nutmeg ISA | Sized as a standalone pot; transfer (don't withdraw) to keep the ISA wrapper — see §10. |
| Horizon | 5 years, then withdraw **in full** | A fixed liability date. Late-horizon drawdown matters most, so we measure 5-year drawdown explicitly and set out a glidepath. |
| Risk | **Balanced** (Nutmeg 7/10, but floor-protective here) | A ~9.5% vol book with a real diversifier sleeve. Note this is still **~74% risk assets** — it sits at the *lower* end of adventurous, **not** in cautious/defensive territory. |
| Capacity for loss | *Assumed:* the year-five proceeds are **not essential** and a nominal loss on that date is tolerable | This is an *assumption*, not something the design can verify. Attitude to risk (Nutmeg 7) is **not** the same as capacity for loss against a hard date. If the money is committed (deposit, tuition), a book that can end slightly below capital and draw down ~46% in a severe path may be too much — see §9. |
| Structure | A part that **grows forever** + a part you **rotate yearly** | Explicit **~80% core / ~20% rotating** split. |
| Themes | **Second-order**, undervalued, *not* the crowded trade | Fresh sleeve (grid, nuclear fuel-cycle, Japan value-up, silver); defence & uranium *miners* dropped as now-consensus. |
| US/AI hedge | Hedge a stumble in US strength | No Nasdaq/semis/AI fund; equal-weight US; value/UK/EM-value tilt; gold + trend. |
| Currency | Prefer GBP (avoid FX) | UK sleeve and the GBP-hedged Japan sleeve carry no FX; gold/overseas equity remain unhedged (by design). |
| Cost | Minimise vs Nutmeg | Blended ~0.36% vs Nutmeg ~0.95–1.0% all-in. |

This document is **guidance and illustration**, not a regulated personal recommendation. If you want a formal suitability assessment, that requires an FCA-authorised adviser.

---

## 3. What changed since the June proposal — and why

The earlier note offered three options and used **European defence** and **uranium miners** as its themes. Three things, checked against current (July 2026) market data, moved the design:

1. **US concentration is worse, not better.** The top 10 S&P 500 stocks are ~41% of the index, the Shiller CAPE is ~39 (near dot-com territory), and semiconductors alone are ~a fifth of total US market cap. Mainstream 2026 mid-year outlooks (Invesco, Amundi, J.P. Morgan) prefer Europe, Japan and EM on valuation and flag record concentration as the key risk. **Your instinct to hedge US/AI is more valid now, not less.**
2. **A plain emerging-market tracker is no longer an AI hedge.** Technology has risen from ~24% to **~42%** of the MSCI EM index, dominated by Taiwan/Korea semiconductors — so a standard EM fund quietly *re-imports* the very AI/semi risk you want to avoid. We therefore use an **EM *value*** building block (Avantis) instead of a cap-weight EM tracker.
3. **Defence, uranium and copper have become consensus.** Sprott's and Rick Rule's 2026 notes now describe the commodity/energy-security supercycle as *"no longer contrarian … visible in price action and capital flows."* Your brief was explicitly for themes that are *not* saturated — so defence and uranium *miners* are demoted to bench alternates, and the rotating sleeve moves one step down each value chain (below).

A fourth change is additive: **the UK is the cheapest developed market** on most metrics (Fidelity/Schroders), with a high return on equity — and it is GBP, so it carries no FX fee. It now has a dedicated core sleeve.

---

## 4. The portfolio — one Trading 212 Pie

Build these as slices of a single Pie. The **core** compounds untouched; the **rotating sleeve** is what you revisit each year (§8).

### Core — the compound-forever engine (~80%)

| Holding | Ticker | Sleeve | Pie % | Why it's here |
|---|---|---|---:|---|
| Avantis Global Equity (value/profitability) | `AVCG.L` | Equity | 12.6 | Cheap, profitable companies worldwide — the engine |
| Avantis Global Small-Cap Value | `AVSG.L` | Equity | 10.8 | Highest expected factor premium (size × value × quality) |
| Avantis Emerging Markets Equity (value) | `AVEM.L` | Equity | 10.4 | EM **value** — cheap, and de-teched vs the 42%-tech EM index |
| iShares Global Infrastructure | `INFR.L` | Real asset | 9.6 | Real-asset, inflation-resilient cash flows |
| JPM Managed Futures (trend, GBP-hedged) | `JMFP.L` | Diversifier | 9.3 | "Crisis alpha" — can profit in sustained downtrends |
| iShares Core FTSE 100 (UK) | `CUKX.L` | Equity | 9.3 | Cheapest developed market, high ROE, **GBP (no FX)** |
| iShares Physical Gold | `SGLN.L` | Real asset | 6.8 | Crisis / inflation hedge; ~0.1 correlation to shares |
| Xtrackers S&P 500 Equal-Weight | `XDEW.L` | Equity | 5.8 | US exposure **without** the mega-cap-tech concentration |
| iShares MSCI World Quality | `IWQU.L` | Equity | 5.4 | Durable compounders; smooths the value sleeve |

### Rotating thematic sleeve — reviewed & rotated ~yearly (~20%, 5% each)

| Holding | Ticker | Theme | Pie % | The second-order angle |
|---|---|---|---:|---|
| VanEck Electrification & Power Infrastructure | `PIKG.L` | Grid & electrification | 5.0 | The **picks-and-shovels of AI power demand** — grids, transformers, utilities. Less hyped than the chips; ~$5.8T global grid capex 2026–35. |
| VanEck Uranium & Nuclear Technologies | `NUCG.L` | Nuclear fuel cycle | 5.0 | Utilities + reactors + fuel cycle, **not just the crowded miners** — a step down the value chain. |
| iShares MSCI Japan (GBP-hedged) | `IJPH.L` | Japan value-up | 5.0 | Corporate-governance reform unlocking cheap balance sheets — a **value + geography** play; GBP-hedged so no JPY FX. Note: a *maturing* (≈3-year) story, not undiscovered — see §7. |
| iShares Physical Silver | `ISLN.L` | Silver & PGMs (⚠ see note) | 5.0 | Monetary **and** industrial (solar, electronics); higher-beta than gold. **Held for optionality/inflation, not expected return** — the model assigns it just ~0.8% compounded at ~28% vol (Appendix B). Treat as a high-vol *tactical* slice, and see the §8 note on shrinking or replacing it. |

**Totals:** core 80.0% · rotating 20.0% · **100%**. By sleeve: equities **54%**, themes **20%**, real assets (gold + infrastructure) **16%**, trend-following **9%**.

> **How the sleeves were sized — read this.** The **core (~80%) is optimised** (§5). The
> **rotating sleeve (~20%) is *not*** — it is imposed at four equal ~5% slices *on top of*
> the optimised core, because the 20%-rotating structure is your instruction, not the
> optimiser's choice. A growth-maximising solve given a free hand would size these
> themes differently and would almost certainly hold **no silver** (§8). The sleeve is a
> deliberate, mandate-driven overlay; it is not claimed to be return-optimal.

*(Defence `NAVY.L` and uranium miners `URNP.L` remain on the bench for future rotations — see §8.)*

> **Fund/ISIN check before you fund (⚠).** Several lines still need their ISIN
> reconciled on the issuer factsheet before building, and together they are **~30%+ of
> the book**: `CUKX.L` (UK core), `AVEM.L` (EM core), `NUCG.L`, `IJPH.L`, `ISLN.L`.
> Some funds are also **very young** — `PIKG.L` launched **2026-06** (weeks old),
> `AVEM.L` 2025, `NUCG.L` 2023 — so they can have wider spreads and less liquidity than
> the decades-old proxies used to model their risk. Keep same-role fallbacks ready:
> **`WIRE.L`** (grid), **`SILV.L`** (silver-miners), a **broad UK line** (`ISF.L`/`IUKD.L`),
> and confirm each is searchable and tradable in your Trading 212 ISA before funding.

---

## 5. How it's built (investment process)

The core is built with the in-house `portfolio_optimiser` — the same disciplined engine as the earlier note:

1. **Forward-looking return assumptions, not past performance.** Expected returns are transparent building blocks (a cash rate + equity-risk premium + factor/theme premia), net of each fund's charge — never an extrapolation of recent returns.
2. **Risk from long history.** Covariance is estimated on ~17 years of monthly GBP total returns (from 2009), with young funds spliced onto longer-history proxies (e.g. the nuclear sleeve onto VanEck's 2007-vintage US analogue, grid onto the 2009 First Trust smart-grid index, silver onto the 2006 silver trust).
3. **Diversification is rewarded explicitly.** The optimiser maximises *geometric* (compounded) growth, which penalises volatility — so gold and the trend fund earn their slots by cushioning falls, not by headline return.
4. **Robust, not fragile weights.** Michaud **resampling** (250 draws on noise-perturbed inputs) produces diversified, stable core weights rather than a knife-edge "optimal" point.
5. **Structure by design.** The core is solved under a Balanced tail budget (1-yr 95% CVaR ≤ 13% *within the core*); the fixed 20% rotating sleeve is then overlaid and the **combined** book is validated by 20,000-path Monte-Carlo. The combined 1-yr CVaR is **13.9%**, comfortably inside the ~15% Balanced level.

> **Why this fits your "no hot themes" brief — and one honest caveat.** The equity core is value, small-cap value, EM *value*, quality and *equal-weight* S&P 500 — by construction a tilt away from the expensive mega-cap-tech names. There is **no Nasdaq-100, no semiconductor, and no explicit "AI" fund** anywhere in the book.
>
> The caveat: the removal of AI risk is a **core** property, not a whole-book one. The rotating sleeve's grid/electrification and nuclear themes are both levered to the **same AI-power / data-centre capex cycle** — so roughly **10% of the book is net-*long* AI-capex** and would sell off *with* it if AI spending disappoints. "No AI anywhere" is true at the chip level but the exposure is partly re-added at the power level. This is why the theme sleeve is **not** the US/AI hedge — the *core* is (equal-weight US, value/UK/EM-value, gold + trend). See §7.

---

## 6. Five-year outlook (modelled, £20,400, no further contributions)

| Outcome | Value after 5 years |
|---|---:|
| Poor (5th percentile) | **£19,470 (×0.95 — a small nominal *loss*)** |
| **Median** | **~£28,500** (×1.40) |
| Strong (95th percentile) | £41,898 |
| Typical worst dip along the way | ~13% |
| Deeper (1-in-20) 5-yr dip | ~26% |
| **Worst modelled 5-yr dip** | **~46%** |
| Passive global tracker, median | £27,788 |

The book expects to grow your money by roughly **40% at the median** over five years. But be clear about the downside: in a **poor five years you could get back slightly *less* than you put in** (~£19,500 at the 5th percentile), and along the way **interim paper losses of ~46% are possible in a severe path** (the worst simulated five-year drawdown). The gold + trend sleeve (~16%) is the genuine cushion — infrastructure is inflation-sensitive but behaves like equity in a crash, so it is *not* part of that cushion. And all of these figures come from a **near-normal simulation that understates real crashes** (§9), so treat the tail as a floor on the *modelled* pain, not on the worst that can actually happen.

On the tracker comparison: the book edges a passive global tracker in **~57%** of simulated paths — **roughly even odds**, not a reliable win — and that edge is **conditional on the value/size/EM/quality premia actually showing up** (the model grants them to this portfolio while pricing the tracker flat). The median edge is only ~£28,500 vs ~£27,800 (≈0.5%/yr). If mega-cap concentration keeps winning for the full five years, this anti-concentration tilt is expected to **lag** a plain tracker the whole way. You are buying a *different risk profile* (a hedge against concentration), not a probable outperformance.

---

## 7. The "interesting themes" story — is this just a tracker with extra steps?

No. The portfolio is deliberately different from a global index fund, in the directions you asked for:

- **Cheap over expensive.** The equity core is value and small-cap value globally — today that means under-owning the handful of very large, very expensive US tech names.
- **Equal-weight US.** Where we hold the S&P 500 we hold the equal-weighted version, which removes most of the "AI mega-cap" concentration in one line.
- **EM *value*, not EM beta.** Because a cap-weight EM fund is now ~42% technology, we use an EM value sleeve — cheaper, and a genuine diversifier rather than more semis.
- **UK.** The cheapest developed market on most metrics, high ROE — and GBP, so no FX drag.
- **Four themes — chosen for freshness, but read the honest labels.** Grid/electrification, the nuclear *fuel cycle*, Japan *value-up*, and silver/PGMs, each sized as a ~5% satellite. Two caveats the earlier draft glossed over:
  - **Grid + nuclear are the AI-power trade, not a hedge against AI.** "The power *behind* AI" is one of the most-marketed narratives of 2026, and grid *and* nuclear both ride the same data-centre capex cycle. They are legitimate growth themes, but they are **crowded and positively correlated to AI-capex** — so this pair does *not* hedge a US/AI stumble, it participates in it. Treat them as AI-capex-linked satellites, not as part of the hedge.
  - **Nuclear "fuel cycle" is only marginally less consensus than the miners it replaced** (it holds the same Cameco/Constellation/Vistra/reactor names), and **Japan value-up is a maturing ≈3-year story** with much of the easy re-rating and foreign inflow already behind it — still valid, but "mid-cycle, catalyst-supported", not undiscovered.
  - **Silver is a *post-rally* asset, not an under-the-radar one**, and the model expects it to compound at just ~0.8% (§4/Appendix B). It earns its slot as optionality/inflation insurance, if at all — not as a conviction growth theme. See §8.

  The genuinely on-brief, uncrowded ideas now sit on the **bench** (water, agriculture/fertiliser — defensive, structural, still under-owned); §8 recommends rotating toward one of them to make the sleeve less one-way-long AI-capex.

---

## 8. The annual rotation playbook

The rotating sleeve is the part you actively manage. Once a year (a calendar reminder is enough):

1. **Hold the sleeve at ~20%** of the pot (rebalancing inside an ISA is tax-free).
2. **Re-score each theme on a rules-based checklist, not a gut "is it in the news" call.** "Sell when it's on every front page" is a *lagging* trigger — by the time a theme is front-page it has usually already run (silver, up sharply into 2026, is the live example). Instead score each theme on: *(a) is the structural thesis still intact?* *(b) is its valuation still reasonable vs its own history (not vs the hype)?* and *(c) is your position still ~5%?* Rotate only when (a) breaks or (b) is clearly stretched. Prefer a boring annual rebalance-to-5% over active theme-timing — the modelled outcomes in §6 **assume static weights and no rotation skill**, and turnover on young, wider-spread ETFs quietly eats the sleeve's already-thin edge.
3. **Rotate from a watchlist**, keeping the sleeve at four ~5% slices. A live watchlist for the next few years:

| Bench alternates (ready to rotate in) | Why they're waiting |
|---|---|
| European defence `NAVY.L` · uranium miners `URNP.L` | Your former themes — now consensus; hold on the bench until they cool or a new leg opens. |
| Copper miners `COPM.L` / `MINE.L` | Electrification metal; strong thesis but the trade is already visible. |
| Water `IH2O.L` · agriculture/fertiliser | Defensive, structural, still under-owned — natural rotations if a current theme gets hot. |
| Latin America / Brazil; Korea value-up | Deep-value geographies; rate-cut and governance catalysts. |

4. **Rebalance the core back to target** at the same time. Leave the core's *composition* alone unless a building block is closed or a cheaper equivalent appears — the core is meant to compound, not to be tinkered with.

> **Two composition changes to weigh — at build time or at the first rotation.** The
> analyst review (companion note) recommends, and you should decide on:
> - **Shrink or drop silver (`ISLN.L`).** It is the lowest-return holding in the book
>   (~0.8% modelled compounded, ~28% vol) and diversifies *worse* than the gold already
>   in the core; holding 5% costs on the order of **0.3–0.4%/yr** of expected growth. If
>   you value it purely as inflation/monetary optionality, keep a smaller slice and hold
>   it *knowing* it is not there for return; otherwise redeploy it into the core engine or
>   a more on-brief theme.
> - **Re-pair the AI-capex tilt.** Grid + nuclear together are ~10% net-long the AI-power
>   cycle. If the point is to hedge a US/AI stumble, replace one of them (or silver) with a
>   genuinely *orthogonal* bench theme — **water (`IH2O.L`)** or **agriculture/fertiliser** —
>   so the sleeve isn't one-way long the same factor as the crowd.
>
> Both are *investment* decisions on your own themes, so they are left for you to make
> rather than baked in. The numbers in this note reflect the portfolio **as built**
> (silver in, four themes equal-weight).

---

## 9. Risks and important considerations

Read this as carefully as the return tables.

- **Capital is at risk.** In a poor five years the modelled value falls to roughly £19,500 at the 5th percentile (a *small nominal loss*), short-term paper losses of 25–30% are entirely possible, and the **worst modelled five-year drawdown is ~46%**.
- **The projections are modelled, not promised.** They use forward-looking assumptions that may be wrong. Past performance is not a guide.
- **Tail risk is understated.** The simulation assumes near-normal returns, which under-states genuine crashes (2008, 2020, a future AI-bubble unwind). The **gold and trend sleeves (~16%)** are the deliberate crisis hedge (infrastructure is inflation-sensitive but behaves like equity in a crash); they cushion but do not eliminate a deep fall.
- **Sequence risk at a fixed exit.** Because you sell everything at year five, a crash in year four or five hurts far more than the same crash in year one. This is why we recommend the diversified structure and the §10 glidepath.
- **Theme concentration.** The rotating sleeve is higher-octane (silver standalone volatility ~28%, the energy themes ~14–19%). Each is capped at ~5% for this reason; do not let a winner run far beyond that without understanding the added risk.
- **New funds / short live histories.** `PIKG.L` (2026), `NUCG.L` (2023) and `AVEM.L` (2025) are young — their modelled risk leans on longer-history *proxies* (see the appendix and §5). Those proxies are mostly **US-listed, USD, differently-constructed analogues** (e.g. an unhedged US fund standing in for a GBP-hedged one), so the 20% theme sleeve has the **least-certain risk estimates in the book** despite the "17 years of history" framing. Confirm each fund is **searchable and tradable in your Trading 212 ISA** before funding; keep same-role fallbacks (`WIRE.L` for grid, `SILV.L` for silver-miners, a broad UK line) in mind.
- **Single-manager and single-platform concentration.** Three Avantis funds make up **~34% of the book** (`AVCG.L` + `AVSG.L` + `AVEM.L`) — one manager, one factor philosophy — and the *entire* pot sits on **one platform (Trading 212)**. The £20,400 is within the £85,000 FSCS limit, but a single manager's factor implementation lagging, or a platform operational event, would hit an outsized share at once (and a platform outage bites hardest around the forced year-five sale). Comfortable with the Avantis weighting is a decision worth making consciously; a non-Avantis value line is an easy diversifier if not.
- **This is not personal advice — and note the substance.** This document is addressed to you, sized to your exact pot, and directive ("build the Pie"). Under FCA rules the *substance*, not the disclaimer, determines whether something is a personal recommendation, so treat it as **educational illustration** and, for a regulated recommendation that accounts for your wider circumstances, other assets and tax position, consult an FCA-authorised adviser.

---

## 10. Implementation and the five-year glidepath

**Transferring the money (do this right).** Use an **ISA transfer**, not withdraw-and-redeposit — ask Trading 212 to pull the funds from Nutmeg via the official ISA transfer process. Previous-year ISA money transfers in full without touching this year's £20,000 allowance.

**Building it.** Create one **Trading 212 Pie**, add a slice per holding at the §4 percentages, and turn on auto-rebalance. On lump-sum vs phasing: investing the whole sum at once has the higher *expected* value, but this is a **fixed-exit** mandate where sequence risk is the dominant hazard, so **phasing the entry over ~3–6 months is a legitimate sequence-risk mitigant here, not just a behavioural comfort** — it is a reasonable trade of a little expected return for less exposure to a bad entry point. Either choice is defensible; just make it deliberately.

**Maintenance.** Rebalance to target once or twice a year (free inside an ISA), and run the §8 rotation review annually. The optimiser can be re-run any time to refresh the numbers (`python -m portfolio_optimiser.report.build_isa_5y`).

**The glidepath — treat this as committed, not optional.** Because you withdraw everything at year five, a crash in year four or five is the single worst thing that can happen to this plan (§9). So the de-risking below is a **dated, pre-committed schedule with target risk-asset weights — set the calendar reminders now** — not a "see how you feel" suggestion. "Risk assets" = equities + themes; "defensive" = gold + trend + min-vol (`MVOL.L`) + short bonds (`IGLS.L`/`ERNS.L`).

| Trigger date (set the reminder) | Target risk-asset weight | Stance |
|---|---:|---|
| **T‑60m → T‑24m** (now to 2y out) | **~74%** | This portfolio as built (core + 20% themes). |
| **T‑24m** | **~55%** | Cut the rotating sleeve to ~10%; begin adding min-vol (`MVOL.L`) and short gilts. |
| **T‑12m** | **~35%** | Themes minimal; majority now in gold / min-vol / short bonds. |
| **T‑6m** | **~15%** | Largely cash-like ballast (`IGLS.L` / `ERNS.L`) — protect the number. |
| **T‑3m** | **~5–10%** | Final de-risk; only what you're willing to see fall in the last quarter. |

*These are target ranges to commit to in advance, not to second-guess in the moment — the whole point is to remove the year-four/five "should I sell?" decision before the market makes it for you.*

---

## 11. Costs versus your current Nutmeg arrangement

| | This proposal (DIY ISA) | Nutmeg fully-managed (typical) |
|---|---|---|
| Management / platform fee | £0 (Trading 212 ISA has no platform fee) | ~0.75% / yr |
| Underlying fund charges (blended TER) | **0.36% / yr** | ~0.20% / yr |
| Market-spread / FX | small; UK & GBP-hedged sleeves carry no FX | small spread |
| **Indicative all-in** | **~0.4% / yr** | **~0.95–1.0% / yr** |

On £20,400, moving from ~1.0% to ~0.4% saves on the order of **£120 a year**, compounding to very roughly **£700+** retained over five years before any performance difference. The blended charge is barely above the earlier all-value proposal despite the pricier theme ETFs, because those sit at only 20% and the core is very cheap (the UK line is 0.07%). *Check your latest Nutmeg statement for your exact charges.*

---

## 12. Recommendation

Build the single Pie in §4: a **Balanced ~80% core that compounds** — global value / quality / small-value, UK, EM-value, equal-weight US, plus a **~16% genuine crisis-hedge sleeve (gold + trend)** and ~10% inflation-sensitive infrastructure — and a **~20% rotating sleeve** of four themes (grid & electrification, the nuclear fuel cycle, Japan value-up, and silver/PGMs). Two decisions to make consciously as you build (§7–§8): **whether to keep silver** (a return-drag held only for optionality) and **whether to re-pair the AI-capex themes** with a more orthogonal one. Then review and rotate the sleeve once a year against the §8 watchlist on a rules-based check, rebalance the core back to target, and — most important for the fixed exit — **de-risk along the committed §10 glidepath** in the final two years. Keep in mind the honest expectations from §6: ~40% median growth, a ~57% (roughly even, premia-conditional) chance of beating a tracker, a 5th-percentile outcome that is a *small loss*, and severe-path drawdowns near ~46%.

---

## Important information

This document has been prepared for the named account holder for information and illustration only. It is **not a personal recommendation, financial advice, or an offer to buy or sell any investment**, and it does not constitute a regulated suitability assessment. It does not take account of your full financial circumstances. The value of investments and any income from them can fall as well as rise and is not guaranteed; you may get back less than you invest. **Past performance is not a reliable indicator of future results.** All return, risk and outcome figures are the output of a quantitative model using forward-looking assumptions that may prove incorrect, and are not promises of future performance. Tax treatment depends on your individual circumstances and ISA rules may change. Specific funds are named for illustration; confirm availability, charges and eligibility on your platform before investing. If you are unsure whether an investment is suitable for you, seek advice from an FCA-authorised financial adviser.

---

### Appendix A — Methodology and assumptions

*Generated by the in-house `portfolio_optimiser` (module `report.build_isa_5y`). Inputs are editable in `portfolio_optimiser/config/`; re-run with `python -m portfolio_optimiser.report.build_isa_5y` to refresh.*

- **Return history:** month-end GBP total returns, Feb 2009 – Jun 2026, young funds spliced onto longer-history proxies.
- **Expected returns:** forward-looking building-block CMAs, net of each fund's TER; converted to geometric using the modelled variance.
- **Risk:** Ledoit-Wolf shrinkage covariance.
- **Core weights:** Michaud-resampled (250 draws); sub-3% dust removed; per-holding and per-sleeve caps applied; solved for geometric growth subject to a 1-yr 95% CVaR ≤ 13% within the core.
- **Structure:** the resampled core is scaled to ~80%; a fixed ~20% rotating sleeve (four themes, equal weight) is overlaid; the **combined** book is validated by 20,000-path Monte-Carlo for the 1-yr CVaR, the 5-yr drawdown, and the 5-yr terminal-wealth distribution.
- **Benchmark:** a transparent passive global-tracker proxy (0.60 global-value + 0.25 equal-weight S&P 500 + 0.15 EM-value) priced at the plain developed-equity assumption of 7.0%.

### Appendix B — Per-holding assumptions (net of fees)

| Holding | Ticker | Expected return (compounded) | Volatility | Ongoing charge | Bucket |
|---|---|---:|---:|---:|---|
| Avantis Global Equity | `AVCG.L` | 8.6% | 11.6% | 0.22% | Core |
| Avantis Global Small-Cap Value | `AVSG.L` | 8.1% | 17.4% | 0.39% | Core |
| Avantis EM Equity (value) | `AVEM.L` | 7.8% | 16.2% | 0.36% | Core |
| iShares Core FTSE 100 (UK) | `CUKX.L` | 7.6% | 12.6% | 0.07% | Core |
| iShares MSCI World Quality | `IWQU.L` | 6.5% | 12.3% | 0.25% | Core |
| Xtrackers S&P 500 Equal-Weight | `XDEW.L` | 5.9% | 16.8% | 0.15% | Core |
| iShares Global Infrastructure | `INFR.L` | 4.5% | 16.1% | 0.65% | Core (real asset) |
| JPM Managed Futures | `JMFP.L` | 3.6% | 7.8% | 0.57% | Core (diversifier) |
| iShares Physical Gold | `SGLN.L` | 2.5% | 16.5% | 0.12% | Core (real asset) |
| VanEck Uranium & Nuclear Technologies | `NUCG.L` | 6.5% | 14.2% | 0.55% | Rotating |
| iShares MSCI Japan (GBP-hedged) | `IJPH.L` | 5.9% | 17.0% | 0.64% | Rotating |
| VanEck Electrification & Power Infra | `PIKG.L` | 5.6% | 19.4% | 0.55% | Rotating |
| iShares Physical Silver | `ISLN.L` | **0.8%** | **28.2%** | 0.20% | Rotating (optionality, *not* return — see §8) |

Note the silver row: **0.8% expected compounded return at 28.2% volatility** is the lowest-return, near-highest-vol line in the book, and below the ~2.5% on the gold already held in the core. It is included as monetary/industrial optionality, not because the model expects it to add return; §8 sets out shrinking or replacing it.

**On the "diversifier" sleeve, precisely.** The genuine crisis hedges are **gold** (~0.1 correlation to equities) and the **trend fund** (crisis alpha) — together **~16%** of the book. **Infrastructure** (`INFR.L`, ~16% vol) is inflation-sensitive but **equity-correlated** — it fell alongside equities in 2022 — so it is best thought of as equity-like real assets, not a crash cushion. Read the earlier "~25% that holds up when equities fall" language through this lens: ~16% reliably cushions, the rest is return-seeking with an inflation tilt.

**On the theme covariance.** These modelled theme vols/correlations lean on proxy-spliced history (§5, §9) — mostly US-listed, differently-constructed analogues for new GBP/GBP-hedged UCITS — and the thematic return premia in `config/cma.toml` are deliberately uniform round numbers (+1.0% each for grid/nuclear/Japan, +2.0% for silver) with no crowding haircut. They are a *transparent prior* so the sensitivity is auditable, not a precise forecast; the 20% sleeve is the least-certain part of the model.

The four themes are sized as satellites — meaningful enough to matter, small enough that a bad year in any one will not derail the plan.
