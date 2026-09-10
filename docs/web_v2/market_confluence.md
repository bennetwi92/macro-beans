# Simulator: market confluence scoring

The swing simulator used to ask one question — *what does this chart say?* —
and grade you on the answer. It never asked the question a swing trader should
ask first: **is the tide going my way?** A long taken into a market trading
below its own 50-day average is a materially different trade from the same
chart in a bull tape, and until now nothing on the screen said so.

This note specifies the market block: what is read, how it is scored, how it
gates a trade, and the edge cases it is deliberately quiet about.

## 1. What is read

Everything comes from one build artefact, `web/v2/data/sim-market.json`, which
`scripts/site/build_sim_market.py` writes from the DuckDB price cache:

| | |
|---|---|
| **Indices** | SPY, QQQ, IWM — closes |
| **Sectors** | the eleven GICS sector SPDRs (XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY) |
| **Volatility** | ^VIX, as `VIX` |
| **Span** | 1700 sessions (~6.5 years), matching the simulator's own window |

Closes only — the market panel draws no candles — and every series is reindexed
onto SPY's trading calendar and forward-filled, so `dates[i]` addresses all
fifteen at once. One file, ~200 KB, fetched once a session. The universe lives
in `config/market_context.csv`, whose `sector` column carries the **GICS sector
name exactly as `config/sp500.csv` spells it**: that string is the whole
stock → ETF mapping, so the two files have to agree.

## 2. Trend state

For each index, on the daily and on the weekly:

| State | Rule |
|---|---|
| **Bullish** | price > 21 EMA > 50 SMA |
| **Bearish** | price < 50 SMA |
| **Neutral** | anything else |

"Anything else" catches the ragged middle the textbook rule leaves undefined —
price above both averages but with the averages crossed the wrong way is *not*
an uptrend, and there is a test that says so.

The weekly read uses a **running weekly bar**: the completed weeks plus today's
close, which is what a live weekly chart shows and, crucially, all a trader
could have seen on the day. Closing the current week with the week's eventual
Friday close would be look-ahead, and the test
`trendAt: the running week closes on today, not on Friday` is what stops it
coming back.

## 3. Sector rank and relative strength

The eleven sector ETFs are ranked by return over **1, 5 and 20 sessions**. All
three are published — a sector that is top-3 over 20 days and bottom-3 over 1
is rolling over, and that is worth seeing — but only the **20-day** rank scores,
because a swing trade is held for weeks.

Bands are counts, not fractions: ranks 1–3 are `top`, the last three `bottom`,
the rest `mid`. A build that ships ten sector ETFs instead of eleven still bands
them the same way.

Relative strength is the stock's own edge over the benchmark across 20 sessions:

```
RS = (stock_now / stock_20d_ago) / (SPY_now / SPY_20d_ago) - 1
```

Positive means the stock *led*, whatever the market did — a different claim
from "it went up".

## 4. The Market Tailwinds Score — 35 points

| Block | Points |
|---|---|
| **Market trend** (SPY, daily) | bullish **20** · neutral **10** · bearish **0** |
| **Sector strength** (20-day rank) | top 3 **15** · middle 5 **8** · bottom 3 **0** |
| **VIX haircut** | **−5** when VIX > 30 |

Total 35, floored at zero.

**The score is always for a side.** A bear tape is worth the full 20 to a
*short*, and a bottom-ranked sector the full 15. This is not decoration: a rule
that only fires on longs is a rule you get round by pressing the other button.
The VIX haircut is the one thing that is *not* mirrored — a volatility spike is
nobody's tailwind.

### The composite

`compositePct(blocks)` returns the points scored as a **percentage of the points
that were on offer**. SIM-104 ships one block (the market's 35), and the
signature takes a list because the epic's other blocks land in the same
composite later. The rescale is the whole trick: an unavailable block drops out
of the numerator *and* the denominator, so a missing feed can never quietly
become a failing grade.

## 5. Rule modes

| Mode | Behaviour |
|---|---|
| **Learning** (default) | Every trade is allowed. A counter-trend entry costs one extra tap, and the tailwind points forgone are shown in the recap. |
| **Strict** | A side scoring under **75%** of the available points has its button disabled, and the strip says why. |

The toggle is the one control on the market strip, remembered per browser in
`localStorage` under `mb.sim.rules`. `?rules=strict` / `?rules=learn` overrides
it for a link.

Note what the arithmetic makes true: a counter-trend long scores at most 15 of
35 (43%), so **Strict Mode blocks every counter-trend entry** without needing a
separate rule for it.

## 6. The strip

One line, 18px, between the status chips and the chart:

```
MKT ▲20/35   SPY ▲▲ QQQ ▼▼ IWM ▲▲   XLK #2/11 ▲   RS +3.6%   VIX 15.9   [LEARN]
```

- `MKT ▲20/35` — the score, arrow marking the side it is for, coloured by band.
- Two glyphs per index: **daily**, then **weekly**. `▲` bull, `▬` neutral, `▼` bear.
- The sector segment carries the same alphabet for its band.
- Segments shed by width, in order of how little they carry: VIX below 500px,
  QQQ/IWM below 440px. SPY, the score, the sector and RS always survive.
- Every segment has a `title` with the long version, so nothing is *only* a glyph.

The page has no spare vertical space, so the warning and the Strict-Mode block
**take over this same line** rather than opening a second one — which is right
anyway, since both are about the market the line was describing.

In the recap the strip **rewinds to the entry** (`MKT @ENTRY ▲0/35 −35`): the
tape has moved on by then, and what is worth grading is the market you actually
bought into. It is not a sixth status chip because two rows is the whole chip
budget and a sixth is what pushes `RESULT` off the bottom.

## 7. The two rules that bind changes here

**No look-ahead.** Every reading is taken as of a date, and a date only ever
resolves to the last market session **on or before** it (`asOf`) — a market
holiday resolves backwards, never forwards. There is a mandatory test
(`no look-ahead: the market read on a date cannot depend on what came after
it`) that truncates the feed and asserts the read is byte-identical.

**Fail open.** Missing data is never a penalty:

| Scenario | Behaviour |
|---|---|
| `sim-market.json` missing or unfetchable | Strip reads `MARKET SCORE UNAVAILABLE — CONFLUENCE RESCALED`; no gate can fire. |
| Decision date before the feed's history | Same. |
| Ticker with no sector ETF (an unmapped or exotic sector) | Benchmarked against SPY, flagged `⚠ SECTOR ?`, and the **sector points leave both sides of the fraction** — 20/20, not 20/35. |
| A sector ETF missing from the build | Dropped from the ranking; the remaining ETFs still band. |

A simulator that punishes you for its own build failing teaches nothing.

## 8. Where the code is

| | |
|---|---|
| Math (pure, tested) | `web/v2/js/sim-market.js` · `tests/web/sim-market.test.js` |
| Page (strip, gate, rule modes) | `web/v2/js/simulator.js` |
| Styles | `web/v2/css/cockpit.css`, `.sim-market` block |
| Universe | `config/market_context.csv` |
| Build | `scripts/site/build_sim_market.py` → `web/v2/data/sim-market.json` |

`marketStatus(market, {sector, date, stock})` is the single entry point and the
client-side twin of the story's
`GET /api/v1/simulator/market-status?ticker={symbol}`. The cockpit has no app
server of its own — pre-built JSON *is* the backend — so the "endpoint" is a
pure function over a file the nightly build already wrote. The response shape is
the endpoint's, and a real HTTP route could serve it unchanged.
