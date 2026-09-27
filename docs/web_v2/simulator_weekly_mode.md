# Simulator: a weekly mode

A plan for letting the swing simulator deal **weekly** charts as well as daily
ones, with a toggle between the two. §0 records what shipped and which of the
plan's open questions were settled how; the rest is the original plan, kept
for its reasoning.

## 0. Status: shipped

The four open questions (§11) were decided as:

| Question | Decision | Where it lives |
|---|---|---|
| Weekly exit fill | **Monday's open** (`exitFill: "nextOpen"`) | `sim-engine.js` `decideExit` |
| Default weekly stop | **One tick under the decision week's low**, falling back to 0.5 weekly ATR under the close when that low is closer than that | `sim-timeframe.js` `defaultStop` |
| Moving averages | **Weinstein: 10- and 30-week SMAs only** (replaces §3's 10/20 EMA + 40 SMA) | `WEEKLY.lines` |
| History | **Everything the cache holds**, for both timeframes | `build_sim.py`, `build_sim_market.py`, `deploy.yml` |

Phases 1–4 of §10 shipped together. The profile refactor, the engine's
next-open exits, the weekly bars, indicators and toggle, and the weekly market
confluence are all in. Phase 5, weekly chart patterns, has **not** been done:
weekly hands run the ladder with S/R only until a weekly census calibrates the
chart-pattern and candlestick gates. Phase 6's longer history is done, as
full history rather than 10 years. The "flip the same hand" peek is not.

Taking the whole history changes some of the numbers below. Warm-up is no
longer tight (§3's table), so the 30-week SMA was chosen on Weinstein's merits,
not to save bars. Deals also now reach back to 1962 on both timeframes.
Split-adjusted prices there run under a dollar, so the build keeps four
significant figures and the page quotes each hand at its own precision. Hands
dealt before 1993 have no market strip, because SPY did not exist yet; the
strip fails open, as it does for any gap in the feed.

The CI cache key moved to `market-duckdb-v3-` so the first deploy seeds every
S&P 500 name with `period="max"`. The old caches only hold them from 2019, and
incremental refresh never reaches backwards. Expect that first deploy to take
noticeably longer. The published `sim/` directory also grows to a few hundred
MB (long-listed names are ~750 KB of JSON each).

## 1. Is weekly the right move?

For a Sunday routine, mostly yes. The reasons are about the trader more than
about the chart:

- **It matches how you can actually trade.** A daily system you can only look
  at once a week is a daily system traded badly: signals age for up to four
  sessions before you see them. A weekly system checked on Sunday is traded as
  designed.
- **Less noise per decision.** One weekly bar folds five days of intraday
  whipsaw into one candle. Trends, bases and support/resistance read more
  cleanly, and the moving averages carry more weight because big funds look
  at them.
- **The simulator helps more on weekly than on daily.** Daily feedback comes
  quickly in real life. Weekly feedback doesn't: a year of Sundays gives you
  about 52 decisions per name. Reps are the scarce thing, and a trainer that
  deals a year of weekly history in a minute is where you get them.

Three costs to go in knowing:

- **Wider stops.** Weekly ATR is roughly 2–2.5× daily ATR, about √5 on a
  random walk. The same 1R therefore means a smaller position. The simulator
  quotes everything in R, which is scale-free, so it handles this correctly.
  It is still the first thing that feels different with real money.
- **Earnings and weekend gaps sit inside the bars.** A 26-week hold crosses
  two earnings reports. The engine already fills a stop at the open when price
  gaps through it, so the simulator will show you this. You can't avoid it,
  but you'll see it priced in.
- **Fewer trades.** A good weekly setup is rarer. Expect to pass more often.
  The simulator's PASS and WAIT answers already treat that as a skill.

## 2. The good news: the engine is already bar-agnostic

`sim-engine.js` never mentions days. It says:

- decide on a bar's **close**;
- enter at the **next bar's open**;
- the stop is live **inside** each bar and fills at the open on a gap;
- the stop only ever moves towards the price.

Read with "bar = week", that's already the Sunday routine: decide on Friday's
close over the weekend, get filled at Monday's open, and leave a resting GTC
stop that the market can hit any time during the week. Trailing the stop
between bars is the same as moving it on the following Sunday.

**One rule does need to change: discretionary exits.** Daily mode fills EXIT
and EXIT 50% at the bar's **close**. That's honest when you're watching the
close. On a Sunday routine you can't sell at Friday's close, because you
decided after it. Weekly exits should fill at the **next bar's open**, the
same way entries do.

→ Add an `exitFill: "close" | "nextOpen"` option to the engine's model, with
daily defaulting to `close` and weekly using `nextOpen`. It belongs in
`sim-engine.js` with tests, not in the page (skill rule 1).

## 3. Adapting the indicators

Weekly traders don't just divide the daily periods by five. They use a small
set of standard weekly lines, and most of them are the daily lines converted
to weeks: the 40-week SMA *is* the 200-day, and the 10-week is the 50-day.
Use those standard values, because they are the lines other traders on weekly
charts are watching.

| Panel | Daily today | Weekly proposal | Why |
|---|---|---|---|
| Fast MA | EMA 9 (~2 wks) | **EMA 10** (~50-day) | The standard weekly "trend line" swing traders trail against |
| Slow MA | EMA 22 (~1 month) | **EMA 20** (~100-day, ~5 months) | Keeps a fast/slow pair for crosses and pullback depth |
| Regime MA | SMA 200 | **SMA 40** (= 200-day) | Same line, weekly units; Weinstein's stage-analysis anchor |
| MACD | 12/26/9 | **12/26/9** (keep) | Already the standard on weekly charts. Slow leg is about 6 months |
| RSI | 14, bands 30/70 | **14, bands 40/60** (+ faint 30/70) | Weekly RSI rarely reaches 30/70. The 40/60 regime bands carry the signal: a bull trend holds above 40, a bear trend stays below 60 |
| ATR (stop sizing) | 14, stop at 1.5 ATR | **14, stop at ~1.0 ATR** (calibrate) | 1.5 weekly ATR is about 3.5 daily ATR, which is loose. Start at 1.0 and check it against "below the prior week's low" |
| Volume | daily | **weekly sum** | Accumulation weeks are one of the clearest weekly tells |

### Warm-up is the constraint that picks the SMA 40

`build_sim.py` ships `MAX_BARS = 1700` daily bars, about 6.5 years or 340
weekly bars. The weekly warm-up budget:

| | Keep "200" in weekly bars | SMA 40 |
|---|---|---|
| Warm-up (SMA + 35-bar window) | 235 weeks | 75 weeks |
| Runway (`MAX_HOLD` + 2) | 28 weeks | 28 weeks |
| Decision weeks left | ~77 (1.5 yrs) | ~237 (4.5 yrs) |

A 200-week SMA would leave the weekly simulator with about 18 months of
dealable history, much of it in one regime. SMA 40 is right both technically
and practically. If you want more market regimes later, raise `MAX_BARS` (see
§8).

## 4. The "rules of the game" constants

These are all counted in bars in `simulator.js`. Each one needs a weekly
value, which makes them a **profile** rather than a set of constants.

| Constant | Daily | Weekly | Reasoning |
|---|---|---|---|
| `LOOKBACK` | 35 | **35** | A phone-screen budget, not a time budget. 35 weeks is about 8 months, enough to see a base form |
| `REVIEW_DAYS` → `REVIEW_BARS` | 20 | **12** | A quarter revealed after a pass |
| `MAX_WAIT` | 10 (2 wks) | **4** (1 month) | Long enough for a weekly breakout to confirm, short enough that WAIT stays a decision |
| `MAX_HOLD` | 60 (~3 months) | **26** (6 months) | Weekly trades are meant to run. 26 still ends a trade kept without a reason |
| `WARMUP` | 200 + 35 | **40 + 35** | Follows the regime MA |
| `YEARS` | 5 | **5** | Unchanged, but see §8 |
| `STOP_ATR` | 1.5 | **1.0** | See §3; calibrate |
| `HUNT_STRIDE` | 3 | **1** | Weekly bars are scarce, so probe every one |

Copy that says "day" (`+1 DAY`, `STOPPED DAY 1`, `WAITED nD`) comes from the
profile too: `+1 WEEK`, `STOPPED WEEK 1`, `WAITED nW`.

## 5. Market confluence on a weekly deal

`sim-market.js` already computes a weekly trend: a running weekly bar using
21 EMA / 50 SMA on weekly closes. Weekly mode swaps what gets **scored**, and
one problem goes away:

- **Score the weekly trend, not the daily.** The 20 trend points ride on
  SPY's weekly state. The strip's two glyphs per index flip order to
  **weekly, then daily**, so the one being scored comes first.
- **Longer lookbacks.** Sector rank `[1, 5, 20]` sessions becomes **1 / 4 / 13
  weeks**, scoring on the **13-week** (one quarter). RS against SPY moves from
  20 sessions to **13 weeks**.
- **The running-week edge case disappears.** A weekly decision is always on a
  Friday close (or the last session of a holiday week), so every read is as of
  a completed week. The `asOf` no-look-ahead rule still applies unchanged.
- **VIX** reads the week's closing value. The spike rule (> 30) holds.

These go in as a `tf` argument threaded through `marketStatus`, which already
accepts `"d"` and `"w"` inside `trendAt`, plus a lookback set per timeframe.
The data stays the same: `sim-market.json` has daily closes, and weekly reads
index into them at week-end dates.

## 6. Patterns, candles and S/R

This is the part that shouldn't be rushed. Every gate in `sim-patterns.js`,
`sim-structure.js` and `sim-candles.js` is one of two kinds:

- **ATR-relative** (`BREAK_ATR`, `POLE_ATR`, `DB_TOL_ATR`, `MIN_SWING_ATR`, and
  so on). These scale on their own, because weekly ATR is used.
- **Bar-counted** (`DETECT_BARS = 90`, `MAX_SPAN = 60`, `POLE_MAX = 15`,
  `DB_MAX_GAP = 25`, `CANDLE_TARGET = 10`, `TREND_N = 10`, `SR_RECENT_BARS`,
  and so on). These **don't** scale. `DETECT_BARS = 90` weekly bars is 1.7
  years; `MAX_SPAN = 60` weeks is a pattern longer than a year.

Chart patterns are broadly fractal. Bulkowski's catalogue covers weekly
charts, and flags, triangles and double bottoms all appear there. But the
gates were **calibrated by firing rate on daily bars** (chart pattern spec
§13), and the skill says to re-run the census after touching any constant.

Proposed sequence:

1. **Weekly v1 ships with chart patterns and S/R only; the candlestick tier is
   off.** Single-candle and two-candle signals are weaker on weekly bars, and
   their trend context (`TREND_N = 10` bars) turns into 10 weeks of
   prerequisite. The ladder falls through to S/R, which works well on weekly
   charts.
2. Move the bar-counted constants into a **per-timeframe profile** passed to
   `detectPattern` (the default profile is today's daily values, so daily
   behaviour stays byte-identical).
3. Run `scripts/tools/pattern_census.mjs` over weekly-resampled bars. Start
   the weekly profile at roughly `DETECT_BARS 60`, `MAX_SPAN 40`,
   `POLE 3–10`, `FLAG 2–8`, `DB gap 4–20`, and tune until firing rates sit in
   the §13 bands.
4. Only then turn weekly candles back on, if the census supports it.

The no-look-ahead tests carry over unchanged, and they need a weekly case each.

## 7. Where the weekly bars come from

**Resample on the client, from the daily file that's already fetched.** Don't
add a second build artefact.

- One source of truth: a weekly bar can never disagree with the daily bars it
  was built from.
- The same `?t=<TICKER>&d=<date>` link replays in either timeframe, and a hand
  logged in one mode can be shown in the other.
- It costs nothing: 1,700 → 340 bars, in one pass.

Add `toWeekly(bars)` in a new pure module (`sim-timeframe.js`, or a function
in `sim-indicators.js`):

- Bucket by **ISO week**, reusing `weekKey` from `sim-market.js`. Move it into
  the new module and import it back, so the two bucketings can never disagree.
- `o` = first session's open, `h`/`l` = max/min, `c` = last session's close,
  `v` = sum. `d` = the **last session's date** (usually Friday), because
  that's the close you decide on.
- A 4-day holiday week is still one bar.
- **Drop an incomplete trailing week** at the end of the file. It never reaches
  a decision day, because the runway keeps it 28 weeks out, but the helper
  shouldn't produce one.

Tests: OHLCV aggregation, holiday weeks, year boundaries (ISO week 53), and
the trailing partial week.

## 8. The toggle

**A timeframe chip on the market strip, beside `[LEARN]`: `[D]` / `[W]`.** It
works exactly like the rule-mode toggle:

- Stored per browser in `localStorage` as `mb.sim.tf`.
- `?tf=w` / `?tf=d` pins it for a link, so a weekly hand is shareable.
- `window.__sim` exposes the timeframe for testing.

**Changing timeframe deals a new hand.** Flipping in the middle of a hand
breaks things: a daily hand on a Wednesday has no completed weekly bar, and an
open trade's stop and R would need re-anchoring. Dealing fresh keeps every
invariant.

**Later: a "flip" peek in decide mode.** Seeing the same chart on the other
timeframe is useful practice, because top-down analysis is what weekly traders
do. Daily → weekly needs a running weekly bar (completed weeks plus today),
which `sim-market.js` already handles for its trend read. This is a
nice-to-have, not part of the first cut.

**Bars budget.** At 1,700 daily bars, weekly gets about 4.5 years of decision
weeks after warm-up. That's workable, but it's mostly one bull market plus
2022. Raising `MAX_BARS` to about 2,600 (10 years) would bring in 2018 and
2020 for both modes. Each of the 503 ticker files would grow by about 50%. The
change goes in `build_sim.py` alone and can be decided later.

## 9. How to structure the code

The core idea: **a `Timeframe` profile object** that the page reads instead of
top-level constants.

```js
// sim-timeframe.js
export const DAILY  = { id: "d", unit: "DAY",  lookback: 35, review: 20, maxWait: 10,
  maxHold: 60, stopAtr: 1.5, exitFill: "close",
  ma: { fast: ["ema", 9], slow: ["ema", 22], regime: ["sma", 200] },
  rsiBands: [30, 70], market: { trendTf: "d", sectorLb: [1, 5, 20], rsLb: 20 },
  patterns: DAILY_PATTERN_PROFILE, candles: true };
export const WEEKLY = { id: "w", unit: "WEEK", lookback: 35, review: 12, maxWait: 4,
  maxHold: 26, stopAtr: 1.0, exitFill: "nextOpen",
  ma: { fast: ["ema", 10], slow: ["ema", 20], regime: ["sma", 40] },
  rsiBands: [40, 60], market: { trendTf: "w", sectorLb: [1, 4, 13], rsLb: 13 },
  patterns: WEEKLY_PATTERN_PROFILE, candles: false };
export function toWeekly(dailyBars) { … }
```

`newSession` does `bars = tf.id === "w" ? toWeekly(daily) : daily`, and
everything downstream reads `S.tf.*`. The indicator keys `e9`/`e22`/`s200`
become `fast`/`slow`/`regime`, so the chart code doesn't care which
timeframe it's drawing.

## 10. Phasing

Each phase ships on its own and leaves daily mode unchanged.

1. **Refactor, no behaviour change.** Add `sim-timeframe.js` with the `DAILY`
   profile, move `weekKey` into it, and route the page's constants and
   indicator keys through `S.tf`. All existing tests pass unchanged.
2. **Engine: `exitFill: "nextOpen"`.** Add the option and tests in
   `sim-engine.js`. Daily stays on `close`.
3. **Weekly bars + indicators + toggle.** Add `toWeekly` with tests, the
   `WEEKLY` profile, the `[D]/[W]` chip, `?tf=`, and the copy. Patterns are
   limited to S/R; candles and chart patterns are off.
4. **Weekly market confluence.** Thread `tf` through `marketStatus`, add the
   weekly lookbacks, and write a weekly no-look-ahead test.
5. **Weekly chart patterns.** Add the per-timeframe pattern profile and run
   the census; switch on only once firing rates are in band.
6. **Optional.** Raise `MAX_BARS`, add the flip-timeframe peek, and try weekly
   candles if the census allows.

Update `docs/web_v2/market_confluence.md` and the simulator section of the
`macro-beans-site` skill as each phase lands.

## 11. Open questions for you

1. **Weekly exits at Monday's open (proposed) or Friday's close?** Monday's
   open is what a Sunday-only routine can actually get. Friday's close assumes
   you'd place a market-on-close order on Friday afternoon.
2. **Default stop: 1.0 weekly ATR, or "below the prior week's low"?** The
   second is a common swing-trader rule and easy to teach. It could be the
   default stop placement in weekly mode, with ATR as the fallback when the
   prior week's low is too close to price.
3. **MA set:** 10/20 EMA + 40 SMA as proposed, or the simpler Weinstein pair
   of 10 and 30/40-week SMAs only?
4. **History:** is 4.5 years of weekly decision dates enough, or go to 10
   years of bars now?
