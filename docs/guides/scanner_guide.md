# How to Read the Scanner

The Scanner is your daily shortlist of stocks and ETFs that just triggered a buy setup — and, crucially, whether that setup has ever actually paid. This guide walks you through every column and control with worked examples, so a row stops looking like a wall of numbers and starts reading like a sentence.

---

## What the Scanner actually is

Every page on the site studies **one** strategy. The Scanner runs **all of them at once**, every day, across every instrument, and shows you only the names where a setup is live *right now*.

Two things to hold in your head before anything else:

1. **Every row is a BUY.** There are no "sell" rows. Some setups buy weakness (a dip you expect to bounce); others buy strength (a breakout you expect to keep running). Either way the action is the same: you'd buy.
2. **You buy tomorrow's open, not today's close.** The Scanner spots the setup on today's closing bar, but you can't buy a close that has already happened. So every statistic assumes you enter at the *next* day's open. That's not a detail — it's how the track record is measured, so it matches what you could really do.

Think of it as a metal detector on a beach. It beeps when something is buried under your feet. It does **not** tell you whether it's a gold coin or a bottle cap — that's what the columns are for.

---

## Reading one row, left to right

Here's a single (made-up but realistic) row. We'll decode it column by column.

| INSTRUMENT | THEME | SETUP | SIGNAL | Z | TREND | EDGE | WIN% | MED | MAE | WORST | N | HOLD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gold Miners · GDGB | Commodities | Buy the Bounce | −4.1% day | −2.3σ | ▲ | +1.18% | 64% | +1.0% | −3.2% | −7.4% | 41 | 10d |

Read it as a sentence:

> *"Gold Miners just fell 4.1% in a single day — an unusually big drop for it (−2.3σ). It's still in an uptrend (▲). The last 41 times this exact setup happened, buying the next open and holding 10 days beat just owning the thing by +1.18% on average, won 64% of the time, and the median trade made +1.0%. Along the way you'd typically have stomached a −3.2% dip, and the worst single case was −7.4%."*

Now each piece:

- **INSTRUMENT** — the name and ticker. A `⚡` next to it means it's leveraged or inverse (more on that below — treat with care). A `×2` or `×3` badge means *multiple* setups fired on the same instrument today (called **confluence** — several signals agreeing is a stronger tell than one alone).
- **THEME** — what bucket it sits in (Stock Markets, Commodities, Bonds, etc.). Handy for spotting when a whole sector lights up at once.
- **SETUP** — which strategy triggered. "Buy the Bounce", "Red Streak" and "Multi-Day Drop" buy **dips**. "Breakout High" and "MA Cross Up" buy **strength**. "Tight Range" buys quiet coils.
- **SIGNAL** — *what* triggered, in plain numbers. "−4.1% day" = the size of today's move. "3 red closes" = a three-day losing streak. "20-day high" = it just made a new high.
- **Z** — *how unusual* that trigger was for this specific instrument, versus its own last year of moves. `−2.3σ` means today's drop was far bigger than its normal day. Anything `≥ 2σ` (in either direction) gets highlighted — those are the genuinely extreme moves, the ones most worth a look. A blank (`—`) just means the setup doesn't have a symmetric "size" to measure (e.g. a streak).

---

## The one column that separates signal from noise: EDGE

If you only learn one column, learn **EDGE**. It's what makes this Scanner different from every "stocks that dropped today" screener.

Here's the trap it protects you from. Imagine a setup wins 60% of the time. Sounds good — until you realise the stock itself rose on 58% of *all* days over the same period, just by drifting upward like the market tends to. So your "edge" is really worth 2%, not 60%. You were mostly being paid by the rising tide, not the setup.

**EDGE strips the tide out.** It's the setup's average return **minus** the instrument's own baseline return over the same window and hold. So:

- **EDGE = +1.18%** → after removing normal drift, this setup genuinely added 1.18% on average. That's real.
- **EDGE = −0.20%** → the setup actually did *worse* than just buying and waiting. The win rate is a mirage. Skip it.
- **EDGE is the column the table sorts by** (via a hidden score), so the most promising setups float to the top automatically.

**WIN%** is coloured the same way: green when the setup's win rate beats the instrument's *own* baseline win rate, red when it doesn't. A green 55% can be better than a red 70%, because it's 70% against an even higher baseline. Always read WIN% next to EDGE, never alone.

> **Rule of thumb:** a positive, green EDGE is the price of admission. No edge, no trade — however pretty the other numbers look.

---

## The rest of the track-record columns

These describe what holding the setup has historically felt like:

- **MED** (median return) — the "typical" trade, with outliers ignored. If MED is much lower than the average return baked into EDGE, a couple of lucky monster trades are flattering the average. MED keeps you honest.
- **MAE** (maximum adverse excursion) — the average worst dip *during* the hold, before it (maybe) recovered. This is your **stop-loss reality check**: if MAE is −3.2%, then a −2% stop would have shaken you out of perfectly good trades. It tells you how much wiggle room the setup normally needs.
- **WORST** — the single ugliest outcome in the whole track record. Your "what's the bad day look like" column. Position-size so you could live through it.
- **N** — how many times this setup has happened (the sample size). **This is a trust dial.** `N = 41` is a decent body of evidence. Anything **under 10 shows a `⚠` and dims** — a 100% win rate over 3 events isn't an edge, it's a coin that landed heads three times. Treat small-N rows as curiosities, not signals.
- **HOLD** — how many days the track record assumes you hold (e.g. `10d`). Every stat on the row is measured over exactly this horizon. It's the plan: buy the next open, exit this many trading days later.

---

## The control bar — filtering the firehose

Across the top you have filters. Each one narrows what you see or changes how the stats are computed.

- **SETUP** — *All* / *Dips* / *Breakouts*. Show every setup, or only the "buy weakness" family, or only the "buy strength" family. Start with **All**, then narrow once you know which style you trust.
- **WHEN** — *New today* / *All active*. "New today" shows only setups that *flipped true on the latest bar* — fresh triggers you could act on now. "All active" also shows setups that fired earlier and are technically still live. For a daily routine, **New today** is what you want.
- **TREND** — *All* / *Uptrend*. "Uptrend" hides anything trading below its 200-day average. Buying dips in things that are still in long-term uptrends is generally safer than catching falling knives. The **▲ / ▼** in the TREND column shows each row's state.
- **STATS** — *All history* / *Same trend*. This is subtle and powerful. "Same trend" recomputes the track record using **only** past days where the instrument was in the *same* trend it's in today. So if it's in an uptrend now, you see how this setup did in *past* uptrends — not muddied by how it behaved in bear markets. It makes EDGE an apples-to-apples comparison.
- **TRACK** — *5Y* / *All*. How far back the track record reaches. 5Y keeps it recent and relevant; All uses the full history for a bigger sample. If 5Y and All disagree a lot, the edge may not be stable.
- **AS OF** — a date picker. This is the **time machine**. Set it to a past date and the Scanner rewinds: it shows you exactly what would have fired *that* day, using only data available then (no peeking at the future). When you rewind, a new **OUTCOME** column appears showing what the trade *actually* went on to do — or `pending` if the hold window hasn't finished yet. It's the single best way to build trust before risking money.

---

## Two worked walkthroughs

### A row worth a closer look

| INSTRUMENT | SETUP | SIGNAL | Z | TREND | EDGE | WIN% | MAE | N | HOLD |
|---|---|---|---|---|---|---|---|---|---|
| FTSE 250 · MIDD ×2 | Multi-Day Drop | −9.2% / 5d | −2.6σ | ▲ | +1.40% | 66% | −3.0% | 53 | 10d |

Why this one earns attention:
- **EDGE +1.40%, green** — a real edge after drift is removed.
- **N = 53** — plenty of history behind it.
- **Z −2.6σ** — a genuinely unusual drop, not everyday noise.
- **▲ uptrend** — buying a dip inside a longer uptrend.
- **×2 confluence** — a second setup fired on the same name the same day.
- **MAE −3.0%** tells you to give it room: a tight −1.5% stop would likely tag you out early.

This is the shape of a setup you'd at least put on a watchlist and size sensibly.

### A row that looks great and isn't

| INSTRUMENT | SETUP | SIGNAL | Z | TREND | EDGE | WIN% | N | HOLD |
|---|---|---|---|---|---|---|---|---|
| Leveraged Tech 3x · LQQ3 ⚡ | Red Streak | 3 red closes | — | ▼ | −0.30% | 100% | 4 ⚠ | 7d |

Every alarm is ringing:
- **WIN% 100%** looks irresistible — but **N = 4 ⚠**. Four flips of a coin. Meaningless.
- **EDGE −0.30%, red** — even across those four, it *lost* to just holding. The 100% is pure small-sample luck.
- **▼ downtrend** — you'd be catching a knife in something already falling.
- **⚡ leveraged** — daily decay and wide spreads quietly eat small edges alive.

A beginner sees "100% win rate" and buys. A Scanner-literate trader sees the `⚠`, the red EDGE, the `⚡`, and the `▼`, and moves on in two seconds. That instinct is the whole point of this guide.

---

## A simple daily routine

1. Set **WHEN → New today**, **SETUP → All**, **TREND → Uptrend**, **STATS → Same trend**.
2. The table is already sorted best-first. Read from the top.
3. For each row, run the quick checklist:
   - Is **EDGE** positive and green?
   - Is **N** at least 10 (no `⚠`)?
   - Is **Z** meaningful, or is this just an average day?
   - Any **⚡**? If so, demand a much bigger edge — costs are higher.
   - What does **MAE** say about where a stop belongs?
4. For the survivors, click the little chart icon on the right to see the price action in context.
5. Want proof? Set **AS OF** back a few months, find similar setups, and read the **OUTCOME** column to see how they actually resolved.

---

## What the Scanner does *not* do

Honesty matters more than hype here:

- **It is not a crystal ball.** EDGE is a historical average. A +1.18% edge means the wind has blown that way before — not that *this* trade will work.
- **It ignores costs.** Spreads, commissions and (for `⚡` instruments) daily decay are real and not in these numbers. A razor-thin edge can vanish entirely once you pay to play.
- **It doesn't size your position or set your stop.** It gives you MAE and WORST as raw material; the risk decision is yours.
- **Small samples lie.** The `⚠` exists because your brain is wired to trust a 100% win rate. Don't.

Used well, the Scanner turns "what dropped today?" into "what dropped today that has actually paid to buy, in this trend, often enough to believe it?" That second question is a far better one — and now you can read the answer straight off the row.
