# Turning Scanner Signals into Trades: a £1000 Playbook

The [Scanner guide](?r=guides-scanner_guide) taught you how to *read* a row. This is the sequel: a complete, rules-based way to *trade* those rows with a real £1000 in a Trading 212 Stocks & Shares ISA — what to buy, how big, where the stop goes, when to sell — plus an honest backtest of whether it actually beats just buying a global tracker. (Spoiler: over the last five years it didn't, but *how* it lost is the interesting part.)

This is a playbook, not advice. Every number below is a starting point you can dial to your own nerve.

---

## The account we're trading

Five constraints shape every rule that follows. They're all from the real Trading 212 ISA:

- **£1000 to start**, growing or shrinking from there.
- **No commission.** The *only* cost is the bid/ask **spread** — the gap between the buy and sell price. We assume **0.25% round-trip** on a liquid London ETF (more on this below). That sounds tiny. It is not.
- **No OCO orders.** You cannot attach a take-profit *and* a stop-loss to the same holding. You *can* place one resting **stop-loss order**, and you *can* set price **alerts**. That single limitation drives the whole exit design.
- **Fractional shares**, so position sizes can be exact to the penny.
- **You check in once each morning.** Before the London open (~08:00 UK) you spend five minutes managing what you hold and acting on what's new. No intraday babysitting.

---

## The playbook at a glance

| Step | Rule |
|---|---|
| **Shortlist** | Scanner set to **New today · Uptrend · Same-trend stats · 5Y**. Read top-down. |
| **Admit a row** | EDGE positive **and** green, EDGE ≥ **+0.3%** (≥ **+1.0%** for a ⚡ leveraged name), **N ≥ 15**, trend ▲. Prefer big **Z** (≥2σ), **confluence** (×2/×3), and **Buy-the-Bounce** dips. |
| **How many** | Up to **5–6** open positions, **1–2 new** per morning, **one position per instrument**. |
| **How big** | Risk **1.5%** of the pot per trade. Stop distance = **1.4 × the row's MAE** (min 3%, max 12%). Size = risk ÷ stop distance, capped at **40%** of the pot and at your spare cash. |
| **Get in** | Market order just after the open, the morning *after* the signal. |
| **Protect it** | Place a resting **STOP** at entry − stop distance. Set a take-profit **ALERT** at entry **+ 3 × stop distance**. |
| **Get out** | Whichever comes first: stop fills, alert fires (sell, cancel stop), or you've held the row's **HOLD** horizon. |

The rest of this note explains each line and then stress-tests it.

---

## 1. What to buy — the morning shortlist

Open the Scanner with the daily-routine filters from the guide: **WHEN → New today**, **TREND → Uptrend**, **STATS → Same trend**, **TRACK → 5Y**, **SETUP → All**. The table is already sorted best-first. Walk it top-down and admit a row only if **all** of these hold:

- **EDGE is positive and green.** This is the price of admission. A red or negative EDGE means the setup historically lost to simply owning the thing — skip it, however pretty the win rate.
- **EDGE ≥ +0.3%** as a floor (and **≥ +1.0%** for a ⚡ leveraged/inverse name, because their decay and wide spreads eat thin edges alive).
- **N ≥ 15.** Below 10 the Scanner shows a `⚠`; we want a bit more evidence than that before committing money.
- **Trend is ▲** (the uptrend filter already enforces this).
- **Tie-breakers that earn a row extra trust:** an extreme **Z** (≥ 2σ — a genuinely unusual move, not an average day), **confluence** (a ×2/×3 badge — several setups agreeing), and the **Buy-the-Bounce** setup specifically. The backtest below shows bounce dips did almost all the heavy lifting.

Take the **top one or two** that clear the bar each morning, never more, and never two of the same instrument. You are looking for the *best* setup of the day, not every setup of the day — because every extra trade pays the spread again.

> **Why so picky?** The edges here are thin — about 1% over a week. Trade too many and the spread quietly out-earns you. Selectivity is not caution; it's the strategy.

---

## 2. How much to buy — let the stop size the trade

Forget "£200 per position." Size each trade so that **if the stop is hit, you lose the same small slice of the pot every time.** That slice is your **risk budget**: **1.5% of the current pot** (£15 on the first £1000).

1. **Stop distance** = `1.4 × the row's MAE`, floored at 3% and capped at 12%. MAE is the average dip a setup puts you through *before* it works (see the guide). Putting the stop a little *beyond* the MAE means normal wiggle doesn't shake you out — a stop tighter than the MAE is a money-loser, and the backtest confirms it (tight stops cut returns hard).
2. **Position size** = `risk budget ÷ stop distance`.
3. **Cap** any single position at **40% of the pot**, and never spend cash you don't have (an ISA can't borrow).

**Worked example.** A Buy-the-Bounce row shows MAE −4%. Stop distance = 1.4 × 4% = **5.6%**. On a £1000 pot, risk = £15, so position = £15 ÷ 0.056 = **£268** (about 27% of the pot). A jumpier row with MAE −8% would get a wider 11.2% stop and therefore a *smaller* £134 position — the size shrinks automatically as the risk grows. That's the whole point: you feel roughly the same pain on every stop-out, whatever you're trading.

---

## 3. How to get out — the no-OCO workaround

This is where the ISA's "no OCO" rule bites, and where the **stop order + take-profit alert** combination earns its keep.

- **The floor: a real STOP order.** The instant you're filled, place a resting stop-loss at `entry × (1 − stop distance)`. It sits in the market and sells you out automatically — you don't have to be watching. This is your hard, unemotional floor.
- **The target: a take-profit ALERT.** You can't *also* rest a take-profit order, so set a price **alert** at `entry × (1 + 3 × stop distance)` — a *wide* target. If it fires, sell manually next morning and cancel the stop. Why wide? In testing, a tight take-profit (1× the risk) clipped winners short and *hurt* returns; letting the occasional big winner run while the stop still caps the downside was worth more.
- **The clock: a time exit.** If neither the stop nor the alert triggers, sell at the open once you've held the row's **HOLD** horizon (the HOLD column — 3 days for a bounce, up to 20 for an MA-cross). Every Scanner statistic is measured to exactly this horizon, so this is the exit that matches the track record. In the backtest, the clock — not the stop or the target — was how **four trades in five** ended.

**Each morning, in order:** (1) any stop that already filled overnight — cancel its leftover alert; (2) any take-profit alert that fired — sell at the open, cancel the stop; (3) any position that has reached its HOLD day — sell at the open; (4) everything else — leave it alone. Then, and only then, look at today's new shortlist.

---

## 4. The cost we can't ignore — the spread

With no commission, the spread is the whole cost of doing business, and it is **decisive**. We assume **0.25% round-trip** for a liquid London ETF — slightly conservative for names like ISF, VUSA or IWDA whose real spread is often 0.05–0.20%, but realistic once you include thinner thematic ETFs and the odd wider quote. Leveraged ⚡ names are assumed wider at ~0.6%.

How much does this assumption matter? Enormously — see the cost table below. Halve the spread and the strategy shines; double it to 0.5% and it goes from a gain to a **loss**. Two practical rules fall straight out of that:

- **Trade only liquid instruments.** If the quoted spread on the day looks wide, the edge is probably already gone. Pass.
- **Don't over-trade.** Every round-trip pays the spread again. Frequency is the enemy of a thin edge.

---

## Your 5-minute morning routine

1. **Manage first.** Run the exit checklist above on everything you hold.
2. **Open the Scanner** with the daily-routine filters.
3. **Admit the top 1–2 rows** that pass the checklist in Section 1.
4. **Size each** with the 1.5%-risk rule and place the **market buy** at the open.
5. **Immediately** place the resting **stop** and set the take-profit **alert**.
6. Close the laptop. Come back tomorrow.

---

## Does it actually work? An honest backtest

I replayed the Scanner day by day from **July 2021 to June 2026** (about five years) on the **91 non-leveraged** London ETFs in its universe, and traded it under exactly the rules above. No look-ahead: every decision used only data that existed that morning, entries are at the *next* open, and prices are split- and dividend-adjusted. The benchmark is the obvious lazy alternative — **£1000 into an MSCI World tracker (IWDA), bought once and held.**

### Headline

| | Scanner strategy | Buy & hold MSCI World |
|---|---|---|
| Final value of £1000 | **£1,348** | **£1,699** |
| Total return | +34.8% | +69.9% |
| Annualised | +6.2%/yr | +11.2%/yr |
| Worst drawdown | −31.7% | −25.9% |
| Trades | 629 (~125/yr) | 1 |
| Win rate | 51.4% | — |
| Average trade | +0.22% | — |
| Average hold | 6.6 trading days | — |

**The verdict: it made money, but it lost to doing nothing.** The strategy turned £1000 into £1,348 — a real gain — yet a one-click world tracker turned the same £1000 into £1,699, and did it with a *shallower* worst drop. After 629 trades and five years of 8 a.m. discipline, you'd have ended up behind a buy-and-hold investor who never opened the Scanner once. That is the honest result, and it matches the guide's own warning: EDGE is a historical average, not a promise about your next trade.

### But look at *when* it won and lost

| Year | Scanner strategy | MSCI World |
|---|---|---|
| 2021 (H2) | −3.2% | +7.6% |
| **2022** | **+11.1%** | **−18.5%** |
| 2023 | +4.0% | +24.7% |
| 2024 | −0.4% | +20.3% |
| 2025 | +9.6% | +21.5% |
| 2026 (H1) | +13.0% | +7.9% |

The strategy is **defensive**, not high-octane. In the 2022 bear market it was *up 11% while the world fell 18%* — a 29-point swing in its favour. Then it spent the 2023–24 bull market badly lagging a roaring index. It stays about **92% invested**, so this isn't sitting-in-cash timidity; it's that the Scanner spreads you across a broad, rotating basket (including bonds, defensive sectors and lagging regions) with protective stops, while the benchmark is 100% concentrated in the one index that happened to lead. In a mostly-rising five years, concentration won. In a *sideways or falling* stretch, the defensive basket would likely have come out ahead.

### Costs decide everything

| Assumed spread | Final value | Total return |
|---|---|---|
| 0.10% round-trip | £1,759 | +75.9% |
| **0.25% (our base)** | **£1,348** | **+34.8%** |
| 0.50% round-trip | £870 | **−13.0%** |

Same trades, three different spread assumptions — and the outcome flips from beating the market to losing money. This is the single most important chart for a small account: **your edge lives or dies on liquidity and turnover.** Trade liquid names, trade rarely.

### Which setups actually paid

| Setup | Trades | Win rate | Avg trade | Total P&L |
|---|---|---|---|---|
| Buy the Bounce | 136 | 56.6% | +0.38% | **+£264** |
| Red Streak | 140 | 51.4% | +0.14% | +£48 |
| Tight Range | 36 | 58.3% | +0.19% | +£32 |
| Multi-Day Drop | 19 | 36.8% | −0.48% | +£0 |
| Breakout High | 298 | 49.0% | +0.25% | −£1 |

Nearly **all** the profit came from one setup: **Buy the Bounce** (buying an unusually sharp one-day dip in an uptrend). Meanwhile **breakouts were almost half the trades and contributed essentially nothing** — they churned the spread for no net reward. If you trade only one part of this playbook, trade the bounce, and treat breakouts with suspicion in a small, cost-sensitive account.

### What *didn't* help

Two things I expected to sharpen the edge and didn't:

- **Tightening the EDGE / Z filters.** Raising the EDGE bar to +0.6% or +1.0%, or demanding a ≥2σ move, mostly *reduced* returns in this sample. The historical EDGE is a weak predictor of the *next* trade — useful as a floor (skip negatives), unreliable as a dial. Don't kid yourself that a bigger EDGE number guarantees a better trade.
- **Leverage.** Including ⚡ names (even on the higher EDGE bar) hurt — and separately, their Yahoo price history is so corrupted by un-flagged reverse splits that I couldn't backtest them honestly at all, so they're excluded from every figure above. Live, the Scanner shows clean prices, but the lesson stands: ⚡ is where thin edges go to die.

*(One caveat against over-reading the wins: a couple of variants — e.g. a stricter ranking-score cut — beat the market in this sample. I've deliberately **not** recommended them, because they win on one five-year window and are exactly the kind of knob that looks brilliant in hindsight and fails live. The config above is a sensible middle, not the curve-fitted peak.)*

---

## So how should you actually use this?

Read honestly, the backtest doesn't say "trade the Scanner to get rich." It says something more useful:

1. **This is a satellite, not a core.** Put the bulk of £1000 in a cheap global tracker and hold it. If the Scanner appeals, trade it with a *small slice* — say £100–£250 — as a defensive, hands-on sleeve. You'll learn far more per pound than reading about it, and the downside is ring-fenced.
2. **If you trade it, be ruthless about the two things that mattered:** keep **turnover low** (one or two of the *best* rows a day, not every row) and **costs low** (liquid names only). Everything else is noise next to those.
3. **Lean on Buy-the-Bounce**, give trades room with generous stops, keep take-profit alerts wide, and let the clock do most of the selling.
4. **Expect to lag in roaring bull markets and to protect you in bad ones.** If that defensive shape suits how you want to feel about your money, the modest return may be a fair price. If you just want the highest number in five years, the tracker is still ahead.

---

## Honest limitations

- **One sample, one regime.** Five years, mostly rising. A different window could look better or much worse. Treat every number as illustrative, not a forecast.
- **Spread is assumed, not paid.** Real fills vary; on a bad day a thin name costs more than 0.25%.
- **No intraday data.** The Scanner (and this test) use daily open/close only, so stops and targets are checked once a day and acted on at the next open — close to a real "check each morning" rhythm, but a live resting stop would sometimes fill *intraday* at a different price.
- **Currency is ignored.** A few lines quote in USD; their returns are treated as if in sterling, so real FX moves would add noise.
- **Survivorship.** The universe is today's instrument list; ETFs that closed aren't in it.

---

## The scripts

Everything here is reproducible. Three scripts under `scripts/scanner_strategy/`:

| Script | What it does |
|---|---|
| `fetch_prices.py` | Pulls 10 years of split/dividend-adjusted daily open/close for the whole Scanner universe into a local cache. |
| `scanner_lib.py` | A faithful Python port of the live Scanner (the same detectors, EDGE, MAE and ranking as `web/v2/js/scanner.js`), so the backtest replays exactly what you'd have seen each morning. |
| `backtest.py` | Simulates the £1000 account under this playbook — risk sizing, stop, take-profit alert, time exit, spread — and writes the equity curve, trade log, per-year, per-setup and cost-sensitivity tables, plus the chart, into `data/scanner_strategy/`. |

Run them in order with `/usr/local/bin/python3`. Re-run `backtest.py` after editing the rules in its `Config` block to test your own variant — the levers that move the result most are **spread**, **turnover** (positions and new-trades-per-day) and **stop width**, in that order.
