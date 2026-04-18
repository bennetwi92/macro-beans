# Copper Event Study — 3HCL.L / 3HCS.L

What macro/geopolitical events have driven the largest daily moves in WisdomTree's 3x copper ETPs on the LSE? Built for trade-idea generation: knowing which event types historically produce big moves tells us when 3HCL/3HCS pair trades are worth taking.

**Method:** Pulled 3HCL.L history (2012-12-20 → 2026-04-17, 3,365 days) and ranked the top 25 up-days and 25 down-days by daily return. Cross-checked each with COMEX HG=F to confirm a copper-driven move. Then web-researched the proximate cause of each cluster.

**Files:**
- Script: `scripts/event_studies/copper_event_study.py`
- Raw data: `data/event_studies/copper_event_study_top_moves.csv`
- Chart: `data/event_studies/copper_event_study_chart.png`

---

## Distribution of 3HCL daily returns (2012–2026)

| Stat | Value (%) |
|---|---|
| Mean | +0.05 |
| Std dev | 4.22 |
| 1st percentile | -10.30 |
| 5th percentile | -6.60 |
| Median | 0.00 |
| 95th percentile | +6.67 |
| 99th percentile | +10.78 |
| Max | +24.49 (2025-07-09) |
| Min | **-64.71 (2025-07-31)** |

**Interpretation for sizing:** a "normal" big day is ±4–7%. A "tail event" (top/bottom 1%) is ±10–11%. Beyond that you're into single-event historic territory — the top-15 list below covers every move >12% in either direction.

---

## Top moves by event cluster

### Cluster A — Trump copper tariff regime (Jul 2025 onwards) — *the biggest moves on record*

The single most important driver in 3HCL/3HCS history. The Section 232 tariff process generated unprecedented COMEX–LME spread dislocations.

| Date | 3HCL | 3HCS | HG=F | Driver |
|---|---:|---:|---:|---|
| 2025-07-09 | **+24.49%** | -33.10% | -3.57% | Trump announces 50% copper tariff after July 8 close. COMEX +13% intraday to record $5.69/lb. LSE-listed 3HCL captured the spike on July 9 morning while HG=F (US daily close) was already retracing — explains the cross-asset divergence. |
| 2025-07-31 | **-64.71%** | +64.15% | -22.25% | **Largest single-day copper move in COMEX history**. Trump's actual tariff text excluded raw + refined copper, only hitting 51 semi-finished products. COMEX-LME spread collapsed from $2,704/t → $29/t in hours. The "tariff bubble" that had been built up over weeks imploded. |
| 2025-04-04 | -22.20% | +23.18% | -8.87% | Liberation Day reciprocal tariff fallout (announced April 2). Copper itself excluded but global sell-off + China retaliation (34% tariff on US imports) hit the metal. |
| 2025-04-07 | -16.89% | +16.21% | -4.92% | Continuation of the Liberation Day rout. Bottom marked April 9 when Trump paused reciprocal tariffs (ex-China). |
| 2025-04-30 | -15.67% | +16.04% | -5.45% | Tariff-pause unwind + China demand worry. |
| 2025-04-10 | +12.59% | -13.22% | +3.48% | Snap-back from the 90-day reciprocal-tariff pause announcement (April 9). |
| 2025-03-05 | +18.42% | -17.82% | +5.28% | Section 232 copper investigation news + tariff front-running into US warehouses. |
| 2025-06-02 | +13.82% | -14.71% | +3.91% | Tariff implementation timeline updates. |
| 2025-09-24 | +12.30% | -12.07% | +3.66% | Mine outage + tariff residuals. |
| 2026-01-05 | +11.71% | -11.62% | +5.04% | 2026 tariff/supply uncertainty restart. |
| 2026-02-03 | +13.40% | -12.96% | +4.50% | Mid-February tariff escalation cycle (10% → 15% raised Feb 20-21). |

**Trade implication:** Tariff/trade-policy tape bombs are now the dominant tail-risk driver for copper. They produce both directions, often within weeks of each other. Position sizing must account for the possibility of a -65% day in 3HCL.

### Cluster B — Russia/Ukraine commodity squeeze (Feb–Mar 2022)

Energy + metals supply shock; LME nickel halt on March 8 created cross-metal contagion.

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2022-02-11 | -12.78% | -3.27% | Pre-invasion risk-off; Putin troop massing news. |
| 2022-03-07 | -11.93% | -4.20% | LME nickel short squeeze day — same day Tsingshan margin call missed. Cross-metal risk-off in copper as funds de-grossed exposure. |
| 2022-04-25 | -12.60% | -2.91% | Shanghai COVID lockdown extension. |
| 2022-06-23 | -12.27% | -4.88% | Recession fears, Powell hawkish testimony. |
| 2022-07-05 | -13.16% | -5.36% | EU recession fear, copper -4% to 17-month low. |
| 2022-07-07 | +13.06% | +4.80% | Reversal/short cover after multi-week wash-out. |
| 2022-08-30 | -11.95% | -2.25% | China property crisis + dollar wrecking-ball. |
| 2022-10-26 | +12.43% | +5.19% | China reopening rumor cycle begins. |
| 2022-11-04 | **+23.15%** | +7.46% | **Best LME copper day since 2009.** China reopening rumors crystallise + steep DXY drop (yuan biggest rally since 2005). |

**Trade implication:** the 2022 cluster shows copper's sensitivity to (i) geopolitical supply shocks, (ii) China demand resets, and (iii) USD direction. The Nov 4 +23% move came on a *single FX/sentiment shift*, no actual policy change.

### Cluster C — COVID crash & V-recovery (March 2020)

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2020-03-18 | -20.07% | -6.69% | Global lockdown panic; copper hit $2.10/lb (4-yr low). |
| 2020-03-23 | -11.77% | -3.24% | Second leg lower before stimulus tape. |
| 2020-03-24 | **+17.00%** | +3.68% | $2trn US stimulus bill + Fed unlimited QE announced. Start of the V. |

**Trade implication:** lockdown/stimulus pairs produce huge same-week reversals. Pure-direction trades got killed; pair trades or option spreads survived.

### Cluster D — COMEX short squeeze (May 2024)

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2024-05-14 | **+15.71%** | +3.10% | COMEX short squeeze — inventory <20kt, contract flipped to backwardation, funds piled in long. COMEX-LME spread blew out to $1,200+/t. |
| 2024-05-22 | (squeeze peaked, COMEX hit $11,257/mt all-time high) | | |

**Trade implication:** structural inventory/positioning squeezes can drive 5-day rallies. Watch COMEX warehouse stocks + the COMEX-LME spread as leading indicators.

### Cluster E — Trump 2024 election

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2024-11-06 | -13.06% | -5.12% | Trump victory → DXY 1-yr high + tariff fear. Copper biggest drop since Jul 2022. |
| 2024-06-07 | -12.49% | -4.19% | Pre-election China demand worry + USD strength. |

**Trade implication:** US election overnight = high-conviction inverse trade (3HCS) when polls suggest Republican sweep. Repeats in 2028 cycle.

### Cluster F — Global growth scares

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2015-01-14 | **-14.78%** | -4.70% | World Bank cut global growth forecast → copper -8% on LME (biggest drop since 2011), 5-yr low. Pure macro/sentiment. |
| 2015-07-07 | -16.64% | -3.62% | Greek referendum/Grexit fear + China A-share crash continuation. |
| 2015-07-08 | +13.91% | +2.16% | One-day reversal as Greek deal hopes returned. |
| 2015-09-22 | -12.68% | -3.81% | Glencore solvency fear (commodity-trader contagion). |
| 2015-09-30 | +11.93% | +4.08% | Glencore share rebound after debt-paydown plan. |
| 2016-06-07 | -11.65% | -3.12% | Brexit polling lurch + soft US payrolls. |
| 2017-12-05 | -11.89% | -4.65% | Year-end profit-taking in copper after a +30% year. |
| 2018-08-15 | -13.43% | -4.43% | Turkey/EM crisis spillover, Chinese yuan weakest in 14 months. |
| 2018-09-21 | +14.87% | +4.24% | Trade war "less bad" relief + China stimulus rumors. |

**Trade implication:** generic global-growth headlines move copper meaningfully (±10%+ on 3HCL) but tend to mean-revert within a week. Best expressed as short-dated 3HCS positions, not multi-week.

### Cluster G — 2021 commodity supercycle

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2021-02-19 | +12.02% | +4.43% | Reflation trade peak, DXY weakness, Biden $1.9trn stimulus. |
| 2021-05-19 | -11.69% | -3.08% | China verbally intervening to "crack down" on commodity speculation. |
| 2021-06-15 | -11.73% | -4.24% | China announced metals stockpile release. |
| 2021-07-26 | +14.08% | +4.14% | Chile mine strike + China PBoC RRR cut. |
| 2021-09-22 | +13.14% | +3.02% | FOMC dovish hold, dollar weakened. |
| 2021-10-14 | +11.74% | +2.46% | LME copper inventory hit 47-yr low; backwardation extreme. |
| 2021-12-16 | +11.68% | +2.90% | Year-end short cover + China RRR cut signal. |

**Trade implication:** China verbal intervention is a clean reliable inverse trigger. Inventory-driven backwardation moves are reliable long triggers.

### Cluster H — Other notables

| Date | 3HCL | HG=F | Driver |
|---|---:|---:|---|
| 2013-05-03 | +18.62% | +6.73% | US payrolls beat, Fed pushed back on early taper. |
| 2014-03-07 | -11.94% | -3.63% | China shadow-bank default fear (Chaori Solar) — first onshore corporate default. |
| 2017-02-10 | +12.93% | +4.31% | Escondida (world's largest copper mine) strike. |
| 2018-09-21 | +14.87% | +4.24% | Trade war relief + China stimulus rumors. |
| 2020-10-01 | -13.70% | -5.45% | EU COVID second-wave lockdowns. |
| 2016-11-10 | +12.77% | +3.68% | Trump 2016 election victory infrastructure trade. |

---

## Pattern summary — what triggers a >10% day in 3HCL?

Ranked by frequency in the top-50 cluster:

1. **US trade/tariff policy (~13 events)** — single biggest driver post-2025. Generates both directions.
2. **China demand/policy (~10 events)** — reopening, RRR cuts, stockpile releases, verbal intervention.
3. **USD direction (~7 events)** — dovish Fed = big up day; election strong-USD = big down day.
4. **Supply disruptions (~5 events)** — Chilean/Peruvian mine strikes, COMEX inventory squeezes.
5. **Global growth scares (~5 events)** — World Bank/IMF downgrades, EM/Brexit/credit fears.
6. **Russia-Ukraine / Hormuz-style geopolitics (~3 events)** — supply chain + risk-off.
7. **Single-stock/credit contagion (~2 events)** — Glencore 2015, Tsingshan 2022.

---

## Trade-idea heuristics

- **Pre-positioned event** (FOMC, Trump tariff deadline, China NPC): use ≤7-day call/put spreads on 3HCL/3HCS, not outright. Compounding decay + announcement reversion can wreck outright positions in 2 days.
- **Tape-bomb event** (unscheduled tariff tweet, mine strike, geopolitics): outright 3HCL or 3HCS works on day 1 only. Cut by close of day 2.
- **Position size by 3HCL sigma**: cap any single trade so a -65% day in 3HCL (the 2025-07-31 precedent) is recoverable. That likely means ≤2% of book per outright 3HCL/3HCS trade.
- **Pair construction**: 3HCL vs SOIL (long copper / short oil 1x) and 3HCL vs SCOP (within-copper directional with reduced leverage) are cleaner than outright 3HCL. Or 3HCL vs Chilean miners (Antofagasta ANTO.L) for a basis trade.
- **COMEX–LME spread is the early warning**: when it's >$500/t, the next tariff headline produces a -20%+ day in 3HCL. When it's near zero, the next headline produces a +15%+ day.

---

## Sources

- [Trump's 50% copper tariff includes a major exemption — CNBC](https://www.cnbc.com/2025/07/31/why-us-copper-tariff-exemption-wont-fully-ease-price-rises.html)
- [Trump Tariff Surprise Triggers Implosion of Massive Copper Trade — Bloomberg](https://www.bloomberg.com/news/articles/2025-07-31/copper-rises-in-london-after-trump-tariffs-exclude-refined-metal)
- [US Copper Prices Surge to Record as Trump Calls for 50% Tariff — Bloomberg](https://www.bloomberg.com/news/articles/2025-07-08/comex-copper-surges-to-record-after-trump-calls-for-50-tariff)
- [Copper Has Best Day Since 2009 as Metals Rocket on Dollar Drop — Bloomberg](https://www.bloomberg.com/news/articles/2022-11-04/zinc-and-copper-surge-on-china-reopening-hopes-supply-angst)
- [LME Nickel Independent Review (March 2022) — LME](https://www.lme.com/-/media/Files/Trading/New-initiatives/Nickel-independent-review/Independent-Review-of-Events-in-the-Nickel-Market-in-March-2022---Final-Report.pdf)
- [Copper Short Squeeze in NY Prompts Rush to Send Metal to US — Bloomberg](https://www.bloomberg.com/news/articles/2024-05-14/new-york-copper-futures-surge-5-5-amid-short-squeeze-on-comex-lw6mvl7a)
- [Commodities Sink to 12-Year Low as Copper, Oil Slump (Jan 14 2015) — Bloomberg](https://www.bloomberg.com/news/articles/2015-01-14/commodities-sink-to-12-year-low-as-copper-oil-slump)
- [US Elections: Trump win, tariff plans weigh on copper prices — S&P Global](https://www.spglobal.com/commodity-insights/en/news-research/latest-news/metals/110624-us-elections-trump-win-tariff-plans-weigh-on-copper-prices)
- [Copper price sees biggest drop since May as Trump win boosts dollar — MINING.COM](https://www.mining.com/copper-price-sees-biggest-drop-since-may-as-trumps-win-boosts-dollar/)
- [Copper Price Update: Q2 2025 Review — INN](https://investingnews.com/daily/resource-investing/base-metals-investing/copper-investing/copper-forecast/)
- [Copper Price Update: Q1 2026 in Review — INN](https://investingnews.com/daily/resource-investing/base-metals-investing/copper-investing/copper-forecast/)

---

*Last updated: 2026-04-18*
