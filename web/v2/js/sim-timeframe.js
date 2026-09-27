// Timeframes for the swing-trading simulator: daily and weekly. Pure functions,
// no DOM, no fetch, so everything here is unit-tested under `node --test`
// (tests/web/sim-timeframe.test.js).
//
// A timeframe is a PROFILE, not a flag: every rule of the game that counts in
// bars (how much history the chart shows, how long WAIT may stand aside, how
// long a trade may run), every indicator period and every word on a button
// comes from one object. The page reads `S.tf.*` and never asks which
// timeframe it is in. Adding a timeframe means adding a profile, not
// sprinkling `if (weekly)` through a 1,500-line module.
//
// Weekly is built for a trader who checks in ONCE A WEEK, on Sunday:
//
//   * You decide on Friday's close (the last session of the week).
//   * Entries AND discretionary exits fill at Monday's open. You cannot sell
//     at a close that happened before you sat down to decide.
//   * The stop is a resting order: it can fill at any time during the week,
//     and at Monday's open if the stock gaps through it.
//   * The default stop sits just under the low of the week you are deciding
//     on. It falls back to half an ATR when that low is too close to the close
//     to survive an ordinary week.
//
// Weekly bars are resampled HERE, from the daily file the page has already
// fetched. That keeps one source of truth, so a weekly candle cannot disagree
// with the days it was built from. It also means `?t=&d=` replays the same
// hand in either timeframe.

/* ---------- the profiles ---------- */

export const DAILY = Object.freeze({
  id: "d",
  unit: "DAY", // button and chip copy: "+1 DAY", "WAIT 1D", "12D HELD"
  short: "D",
  lookback: 35, // bars VISIBLE when you decide — a phone-screen budget
  review: 20, // bars revealed after a pass
  maxWait: 10, // two trading weeks
  maxHold: 60, // hard runway; the trade is closed on the last bar
  exitFill: "close", // discretionary exits fill at the bar's close
  stop: { rule: "atr", atr: 1.5 }, // default stop: 1.5 ATR under the close
  // The lines on the price panel, drawn back to front. `fit` puts a line in the
  // price scale; a line that is not fitted is clipped and, when it is off the
  // chart, named in the corner (`offScale`) instead of silently vanishing.
  lines: Object.freeze([
    { key: "slow", kind: "sma", period: 200, label: "200SMA", cls: "sim-ma200", fit: false, offScale: true },
    { key: "mid", kind: "ema", period: 22, label: "22EMA", cls: "sim-ma22", fit: true },
    { key: "fast", kind: "ema", period: 9, label: "9EMA", cls: "sim-ma9", fit: true },
  ]),
  rsiBands: Object.freeze([30, 70]),
  detect: Object.freeze({ tiers: [1, 2, 3] }), // chart patterns, candles, S/R
  years: null, // decision dates: all of the history (null) or the last N years
});

// Weinstein's weekly chart: the 10-week and the 30-week simple averages, and
// nothing else. The 30-week is the line his stage analysis turns on — a
// stock above a rising 30-week is in Stage 2 — and the 10-week is the one a
// swing trade trails against. Both are fitted into the price scale: on a
// weekly chart the 30-week is close to price, which is the point of it.
export const WEEKLY = Object.freeze({
  id: "w",
  unit: "WEEK",
  short: "W",
  lookback: 35, // about eight months: enough to see a base form
  review: 12, // one quarter revealed after a pass
  maxWait: 4, // a month: long enough for a weekly breakout to confirm
  maxHold: 26, // six months: weekly trades are meant to run
  exitFill: "nextOpen", // Sunday's decision fills at Monday's open
  stop: { rule: "barLow", minAtr: 0.5 }, // under the decision week's low
  lines: Object.freeze([
    { key: "slow", kind: "sma", period: 30, label: "30W SMA", cls: "sim-ma200", fit: true },
    { key: "fast", kind: "sma", period: 10, label: "10W SMA", cls: "sim-ma9", fit: true },
  ]),
  // Weekly RSI rarely reaches 30 or 70. The information is in the regime: a
  // bull trend holds above 40, a bear trend fails below 60.
  rsiBands: Object.freeze([40, 60]),
  // Support and resistance only, for now. The chart-pattern and candlestick
  // gates were calibrated by firing rate on DAILY bars (chart_pattern_spec
  // §13); their bar-counted constants mean something else on a weekly chart,
  // and they stay off until a weekly census says where they belong. S/R is
  // ATR-relative and reads naturally on weekly bars. 60 weeks of history is
  // a bit over a year of levels.
  detect: Object.freeze({ tiers: [3], detectBars: 60 }),
  years: null,
});

export const TIMEFRAMES = Object.freeze({ d: DAILY, w: WEEKLY });

/** The profile for an id, falling back to daily for anything unknown. */
export const timeframe = (id) => TIMEFRAMES[id] || DAILY;

/**
 * Warm-up in bars before the first possible decision day: the longest
 * average on the chart, plus the visible window. The MACD's slow leg (26 + 9)
 * and the ATR (14) are always shorter than the regime line.
 */
export const warmupBars = (tf) => Math.max(...tf.lines.map((l) => l.period)) + tf.lookback;

/** Bars needed AFTER the decision day: the whole hold, plus a next-open exit. */
export const runwayBars = (tf) => tf.maxHold + 2;

/* ---------- weekly bars ---------- */

/**
 * ISO-8601 week key: the date of that week's Thursday. Thursday decides which
 * year a week belongs to, so week 1 of 2021 starts on 4 January 2021 and
 * 1 January 2021 is in week 53 of 2020. sim-market.js buckets its weekly
 * trend with the same function, so the two can never disagree about where a
 * week begins.
 */
export function weekKey(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  const day = (d.getUTCDay() + 6) % 7; // Monday = 0
  d.setUTCDate(d.getUTCDate() - day + 3); // the week's Thursday
  return d.toISOString().slice(0, 10);
}

/**
 * Resample daily bars ({d, o, h, l, c, v}) into weekly bars.
 *
 *   o   the first session's open        h / l   the week's extremes
 *   c   the last session's close        v       the week's total volume
 *   d   the LAST session's date — usually Friday, the close you decide on
 *   di  the index of that last session in the daily array, so the page can
 *       read anything daily (the market feed, relative strength) as of the
 *       same moment
 *
 * A holiday-shortened week is still one bar. An incomplete final week is
 * dropped: weekly mode decides on completed weeks only, and a final bar that
 * silently gained sessions tomorrow would be a different candle from the one
 * the next build ships. "Incomplete" means the week has not yet reached its
 * Friday AND it is the end of the file. A holiday Friday only affects a
 * week that is still in progress.
 *
 * `asOf` (optional ISO date, the day the data was built) lets a caller say
 * the file ends mid-week. Without it, a final week that stops before Friday
 * is treated as unfinished.
 */
export function toWeekly(daily, asOf = null) {
  const out = [];
  let key = null;
  let cur = null;
  for (let i = 0; i < daily.length; i++) {
    const b = daily[i];
    const k = weekKey(b.d);
    if (k !== key) {
      if (cur) out.push(cur);
      key = k;
      cur = { d: b.d, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0, di: i };
      continue;
    }
    cur.d = b.d;
    cur.h = Math.max(cur.h, b.h);
    cur.l = Math.min(cur.l, b.l);
    cur.c = b.c;
    cur.v += b.v || 0;
    cur.di = i;
  }
  if (cur && weekIsComplete(cur.d, asOf)) out.push(cur);
  return out;
}

/**
 * Has the week whose last seen session is `lastIso` finished? Yes if that
 * session is a Friday. Otherwise it is finished only if we know the data runs
 * past it (`asOf` is in a later week), for example a Thursday before a Good
 * Friday holiday.
 */
function weekIsComplete(lastIso, asOf) {
  const day = new Date(`${lastIso}T00:00:00Z`).getUTCDay();
  if (day === 5) return true;
  return asOf != null && weekKey(asOf) > weekKey(lastIso);
}

/* ---------- the default stop ---------- */

/**
 * Where the stop starts before you drag it, for a long off the close of bar
 * `i`. It is only a starting point: the page lets you drag it anywhere, and a
 * short needs it dragged above the price anyway.
 *
 *   atr     `tf.stop.atr` ATRs under the close (daily: 1.5)
 *   barLow  one tick under the low of the bar being decided on — "below last
 *           week's low", the classic weekly swing stop — unless that low is
 *           within `tf.stop.minAtr` ATRs of the close. A week that closed on
 *           its low would put a stop right on top of the price. In that case
 *           the stop falls back to `minAtr` ATRs under the close.
 *
 * With no ATR yet (too little history), 2% of the close stands in.
 */
export function defaultStop(tf, bars, atrArr, i, tick = 0.01) {
  const close = bars[i].c;
  const a = atrArr[i] || close * 0.02;
  if (tf.stop.rule === "barLow") {
    const stop = bars[i].l - tick;
    const floor = close - tf.stop.minAtr * a;
    return stop < floor ? stop : floor;
  }
  return close - tf.stop.atr * a;
}

/* ---------- price precision ---------- */

/**
 * Decimal places to quote a price at. Two for anything a dollar or more,
 * because US listings trade in cents. Below a dollar, enough places to keep
 * four significant figures, because a split-adjusted 1960s price can be $0.04,
 * and at two places every candle on the chart would be the same flat line.
 * The build (build_sim.py) rounds with the same rule.
 */
export function priceDecimals(price) {
  if (!(price > 0) || price >= 1) return 2;
  return Math.min(8, 3 - Math.floor(Math.log10(price)));
}
