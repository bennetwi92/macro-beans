# Shell vs BP — what drives the pair, and what drove the last year's swings

The Shell / BP portfolio on the site (long Shell `SHEL.L`, short BP `BP.L`,
beta-hedged) is a bet on the *relative* fortunes of the two London oil
supermajors with the common crude-oil move hedged out. This note characterises
that relationship over the last year (2025-06-10 → 2026-06-10) and attributes
each major swing to a catalyst.

**Method:** pulled ~18 months of LSE closes for both names, computed a rolling
60-day beta (1-day lag, no look-ahead), a beta-hedged "oil-neutral" spread
(`r_SHEL − beta·r_BP`), the raw `SHEL/BP` price ratio, and a zig-zag swing
decomposition of the ratio. Then web-researched the proximate cause of each leg.

**Files:**
- Script: `scripts/event_studies/shell_bp_pair_study.py`
- Daily series: `data/event_studies/shell_bp_pair_daily.csv`
- Extreme single-day relative moves: `data/event_studies/shell_bp_pair_extremes.csv`
- Swing legs: `data/event_studies/shell_bp_pair_swings.csv`
- Chart: `data/event_studies/shell_bp_pair.png`

---

## Headline numbers (last year)

| Metric | Value |
|---|---|
| Shell (SHEL.L) | 2,594p → 3,194p (**+23%**) |
| BP (BP.L) | 374p → 531p (**+42%**) |
| SHEL/BP ratio | 6.94 → 6.00 (max **7.04** on 2025-06-25, min **5.68** on 2026-04-28) |
| Rolling 60d correlation | mean **0.78** (range 0.63–0.89) |
| Rolling 60d beta (SHEL on BP) | mean **0.60** (range 0.46–0.85) |
| Oil-neutral spread (long SHEL/short BP) | +0.9% total, **13.7% ann vol**, Sharpe 0.13 |

**The single fact that frames the year: BP nearly doubled Shell's return** (+42%
vs +23%). The pair was *not* a quiet mean-reverter — it trended hard in BP's
favour, with violent counter-swings around results and the oil shock.

Note the structure of the hedge: because BP is the **higher-beta** leg, a
1-for-1 Shell-vs-BP regression gives beta ≈ 0.6, i.e. BP typically moves ~1.7×
as much as Shell per unit of the common oil factor. The beta-hedge deliberately
shorts only ~0.6 of BP per 1 of Shell, which is why the *oil-neutral spread* is
roughly flat (+0.9%) even though BP crushed Shell outright — most of BP's
outperformance was higher-beta participation in a rising-then-spiking oil tape,
which the hedge strips out by design. The leftover ±14% vol is the genuinely
idiosyncratic, company-specific story below.

---

## What structurally drives the relationship

1. **Common factor — crude oil.** Both are integrated majors; 60-day correlation
   averages 0.78 and rises toward 0.9 in risk-on/oil-shock regimes. Hedging one
   against the other removes most of this.
2. **BP is the higher-beta, higher-gearing, "turnaround/optionality" name.** More
   upstream- and balance-sheet-levered, cheaper, and carrying a persistent
   **M&A / self-help premium**. It leads on the way up (especially in oil
   spikes) and lags on the way down.
3. **Shell is the higher-quality "compounder."** Stronger and steadier free cash
   flow ($26.1bn FY2025), a consistent buyback, lower gearing. It wins on
   **capital-return divergence** and tends to outperform on down-moves.
4. **Three idiosyncratic swing engines this year:** (a) takeover-premium
   oscillation in BP, (b) the capital-returns divergence (Shell buying back
   stock while BP *suspended* its buyback), and (c) the oil supply shock, which
   is a common factor but hits the pair *asymmetrically* through beta.

---

## Swing-by-swing attribution (SHEL/BP ratio zig-zag, ≥4.5% legs)

A falling ratio = BP outperforming; a rising ratio = Shell outperforming.

| # | Window | Ratio move | Winner | What drove it |
|---|---|---:|---|---|
| 1 | Jun 10 – Sep 24 '25 | −12.2% | **BP** | BP "in play." WSJ reported Shell was in early talks to buy BP; **Shell issued a formal Rule 2.8 denial on 26 Jun 2025**, which under the City Code froze it from bidding for six months (to 26 Dec) — but left BP wearing a takeover/​floor premium. Layered on top: **Elliott's ~5% activist stake** forcing cost cuts, disposals and higher returns, and traction in BP's Feb-2025 strategy reset (back to oil & gas, ~$10bn/yr upstream). The cheap, high-beta laggard re-rated. |
| 2 | Sep 24 – Oct 20 '25 | +8.3% | Shell | Counter-swing as oil softened into autumn (crude was heading for its biggest annual loss since Covid). Higher-beta BP gave back; Shell's steadier cash generation outperformed. |
| 3 | Oct 20 – Dec 4 '25 | −8.9% | **BP** | Renewed megadeal speculation as the **26 Dec standstill expiry** approached, plus continued self-help. BP re-rated again. |
| 4 | Dec 4 – Dec 19 '25 | +5.7% | Shell | **Deflation of the bid premium:** Shell's M&A chief Greg Gut resigned (~16 Dec) after CEO Wael Sawan blocked an internal push for a ~$56bn BP takeover — a clear signal that *no* near-term Shell bid was coming. BP's takeover optionality cheapened; Shell outperformed. |
| 5 | Dec 19 '25 – Feb 6 '26 | −8.8% | **BP** | Premium re-inflates: the **26 Dec standstill lapsed** ("clear runway for renewed speculation"), and BP's **CEO change** — Murray Auchincloss out, **Meg O'Neill** in from 1 Apr 2026 (first woman to lead a Big Oil major) — *reignited* merger talk hours after the announcement. BP rallied on takeover + new-broom optionality. |
| 6 | Feb 6 – Feb 27 '26 | +10.9% | **Shell** | **Capital-returns divergence, the cleanest fundamental swing of the year.** On **10 Feb 2026 BP reported FY2025, missed (~$7.5bn vs ~$7.6bn est.), and *suspended its share buyback* to prioritise debt paydown** — BP fell ~4–6% (the pair's single biggest one-day BP-underperformance, −6.1% on the day). Shell's Q4, by contrast, delivered $26.1bn FY free cash flow and a fresh **$3.5bn buyback**. Shell rewards holders; BP withdraws returns. |
| 7 | Feb 27 – Mar 19 '26 | −7.8% | **BP** | **The oil supply shock.** US/Israel strikes on Iran on **28 Feb** disrupted Strait of Hormuz flows; **Brent rocketed toward $120–128** (the largest-ever monthly gain, March). Higher-beta, higher-operational-gearing BP outran Shell (BP +22% vs Shell +13% over the leg). |
| 8 | Mar 19 – Mar 23 '26 | +5.0% | Shell | Sharp oil pullback / volatility spike inside the war premium — the higher-beta leg gives back fastest, so Shell outperformed on the down-tick. |
| 9 | Mar 23 – Apr 28 '26 | −8.8% | **BP** | Oil stayed elevated through April (Brent ~$117 avg) on the still-disrupted Hormuz, keeping the upstream-levered name bid even through violent daily swings (e.g. BP −7.4% on 17 Apr). The ratio bottomed at **5.68 on 28 Apr** — BP's richest point vs Shell all year. |
| 10 | Apr 28 – Jun 10 '26 | +5.9% | **Shell** | **Mean-reversion of the war premium.** US–Iran ceasefire talks to reopen Hormuz pulled Brent down (May avg $107, −$10). Higher-beta BP gave back the oil-spike premium (−8% vs Shell −3%), and with BP's buyback still suspended, Shell's steadier return profile won on the way down. |

---

## So what actually moves this pair?

- **Most of the trend (BP +42% vs Shell +23%) is BP's structural re-rating** from
  a cheap, geared, activist-pressured turnaround into a name carrying a live
  takeover premium *and* a high-beta call on a sharply rising oil tape.
- **The biggest *clean* relative swings are corporate-action and capital-return
  events**, not oil: the Shell-bid denial (Jun), the blocked-bid/M&A-chief exit
  (Dec), the standstill lapse + BP CEO change (Dec–Jan), and above all **BP's
  buyback suspension vs Shell's fresh buyback in Feb** (the single biggest
  one-day move in the pair).
- **The oil shock (Iran/Hormuz, Feb–Apr) is a beta event, not an alpha event:**
  it moved the *raw* pair hard (BP leads up, lags down) but largely washes out of
  the beta-hedged spread. For a beta-hedged Shell/BP position, oil spikes are
  mostly noise; the durable edge is the *capital-discipline and M&A* narrative.

### Trading read-through
The oil-neutral spread is a low-Sharpe (0.13), ~14%-vol mean-reverter dominated
by event risk. The asymmetry worth respecting: **BP carries embedded takeover
optionality and higher oil beta**, so a static short-BP/long-Shell hedge is
short a call on both a Shell bid and an oil spike — both of which fired this
year. Size the BP leg by *live* beta (it ranged 0.46–0.85), and treat BP
results days and any Takeover-Code headline as the dominant event risks.

---

## Sources

- [BP stock performance in 2025 vs Shell — Meyka](https://meyka.com/blog/bp-stock-performance-in-2025-solid-gains-but-still-trailing-shell/)
- [Elliott increases BP stake to 5% pushing reset strategy — Oil & Gas 360](https://www.oilandgas360.com/elliot-increases-bp-stake-to-5-as-it-pushes-reset-strategy/)
- [Activist Elliott meets BP investors to discuss more changes — US News/Reuters](https://money.usnews.com/investing/news/articles/2025-03-21/activist-elliott-meets-bp-investors-to-discuss-more-changes-sources-say)
- [Shell denies interest in BP takeover, freezing potential deal for six months — INN](https://investingnews.com/shell-denies-bp-takeover/)
- [Shell doubles down on BP denial; legally barred from offer for six months — Fortune](https://fortune.com/2025/06/26/denying-reports-bp-takeover-shell-legally-barred-offer-six-months/)
- [Shell M&A chief resigns after push to acquire BP is blocked by CEO — energynews.africa](https://energynews.africa/2025/12/17/shell-ma-chief-quit-after-leadership-blocked-bp-takeover-plan/)
- [BP CEO shake-up reopens talk of a Shell megadeal — OilPrice](https://oilprice.com/Energy/Energy-General/BP-CEO-Shake-Up-Reopens-Talk-of-a-Shell-Megadeal.html)
- [BP suspends share buyback in fresh sign of oil price pressure (FY2025 results) — CNBC](https://www.cnbc.com/2026/02/10/bp-earnings-q4-full-year-oil-energy.html)
- [BP full-year 2025 earnings preview (10 Feb 2026) — IG](https://www.ig.com/uk/news-and-trade-ideas/bp-full-year-earnings--can-the-energy-giant-balance-transition-w-260206)
- [Shell Q4 2025 results — $26.1bn FY free cash flow, $3.5bn buyback (Form 6-K)](https://www.sec.gov/Archives/edgar/data/0001306965/000162828026005600/q42025exhibit992.htm)
- [Oil Market Report — March 2026 (Iran supply shock, Hormuz) — IEA](https://www.iea.org/reports/oil-market-report-march-2026)
- [Oil Market Report — April 2026 — IEA](https://www.iea.org/reports/oil-market-report-april-2026)
- [Short-Term Energy Outlook (Brent monthly averages) — EIA](https://www.eia.gov/outlooks/steo/report/global_oil.php)
