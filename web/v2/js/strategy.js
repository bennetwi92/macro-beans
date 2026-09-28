// The weekly strategy — its RULES, in one place. Pure functions: no DOM, no
// fetch. Covered by tests/web/strategy.test.js.
//
// Spec: docs/web_v2/scorecard_strategy_spec.md. The one-sentence version:
//
//     Only ever buy low relative to a RISING line.
//
// Trend-following on the higher timeframe (Weinstein's stage analysis on the
// 30-week average), mean-reversion or strength at the entry. Three setups, all
// long-only (the book is a cash ISA: no shorting, no margin):
//
//   PULLBACK   an established Stage 2 advance, cooled back to its 10-week line
//   BREAKOUT   a weekly close through a 26-week high that price had paused
//              beneath (a base), the 30-week not falling
//   REVERSAL   a Stage 4 decline that has stopped: flat/turning 30-week, a
//              higher low, momentum back above the midline
//
// Everything that decides WHAT the strategy does lives here, and everything
// that decides how GOOD a candidate is lives in scorecard.js. The split
// matters: the backtest, the like-week analogues, the CARD and the BOOK all
// replay trades with `runTrade`, so the strategy you are shown evidence for is
// exactly the one you are trading, and the one the simulator can train.
//
// The trading model is the simulator's weekly one (sim-engine.js,
// sim-timeframe.js WEEKLY), deliberately unchanged:
//
//   * decide on Friday's close; enter at Monday's open;
//   * the initial stop is one tick under the decision week's low, or 1 ATR
//     under the close if that is too close (`stopFor`) — and it rests all
//     week, filling at the open of whichever DAY gaps through it (`stepWeek`
//     — stricter than the simulator, which fills on the weekly bar);
//   * the stop only ever ratchets up (sim-engine `moveStop`);
//   * discretionary exits fill at the NEXT week's open.
//
// Exits are part of the strategy, not an afterthought (spec §2.4):
//
//   stop     resting, intraweek, as above
//   trail    at +1R the stop goes to break-even; from then on it follows the
//            10-week SMA less one weekly ATR. "Sell high" is the trail's job —
//            there is no fixed profit target, because a target caps exactly the
//            trades that pay for all the others.
//   thesis   a weekly CLOSE below the 30-week SMA ends the trade (Weinstein's
//            sell rule: Stage 2 is over). Armed from the first weekly close
//            above the 30-week at or after the decision, so a REVERSAL bought
//            under the line is not thrown out on its first week.
//   time     WEEKLY.maxHold weeks (26). A setup that has not worked in six
//            months was wrong, not early.
//
// Two rules bind every function below:
//
// 1. **No look-ahead.** Anything evaluated "at week w" reads bars 0..w only.
//    `runTrade` reads forward by design — it IS the outcome — and its results
//    may only be used by a caller standing at or after the trade's exit week
//    (`analogueStats` enforces that). There are mandatory tests.
// 2. **One position per name.** The event table (`eventTable`) never opens a
//    second trade on a name while one is running, because the book never
//    would. Overlapping signals would inflate every sample size here.

import { sma, rsi, atr, macd } from "./sim-indicators.js";
import { WEEKLY, toWeekly, defaultStop } from "./sim-timeframe.js";
import { openTrade, stepTrade, decideExit, moveStop, tradeStats, isOpen } from "./sim-engine.js";
import { pivotsOf, levels } from "./sim-structure.js";

export const SETUPS = Object.freeze(["PULLBACK", "BREAKOUT", "REVERSAL"]);

/**
 * Every constant the strategy's rules turn on. One frozen object, so a change
 * to the strategy is a one-line diff with a test, never a hunt.
 */
export const RULES = Object.freeze({
  maxHold: WEEKLY.maxHold, // 26 weeks
  horizon: 13, // fixed-horizon forward return, in weeks (a quarter)
  // Stage: the 30-week's slope over `slopeWeeks`, in weekly ATRs. Inside
  // ±flatAtr the line is flat. `priorWeeks` back decides whether a flat line
  // follows an advance (Stage 3) or a decline (Stage 1).
  slopeWeeks: 4,
  flatAtr: 0.25,
  priorWeeks: 26,
  pullback: Object.freeze({
    minAge: 6, // weeks in Stage 2 before a dip counts as a dip in an advance
    highWeeks: 13, // the high the pullback is measured from
    depthAtr: 1.0, // at least this far off that high
    near10Atr: 0.5, // and no more than this above the 10-week
    rsi: Object.freeze([40, 60]), // cooled, not broken (WEEKLY.rsiBands)
  }),
  breakout: Object.freeze({
    baseWeeks: 26, // the high to clear: the prior half-year
    // The high being cleared must be at least this many weeks old: price has
    // to have paused beneath it. Without this, every week of a steady grind
    // is a "new 26-week high" and BREAKOUT fires on one name-week in nine —
    // measuring the trend, not a base resolving (O'Neil's and Weinstein's
    // breakout is from a BASE).
    minBaseAge: 4,
    recentWeeks: 2, // a breakout stays buyable this many weeks
    maxExtAtr: 1.5, // ... while no more than this above the level
    watchAtr: 1.0, // coiling within this far under the level is a WATCH
  }),
  reversal: Object.freeze({
    declineWeeks: 13, // of the last 52 spent in Stage 4
    lookback: 52,
    rsiMin: 50,
  }),
  trail: Object.freeze({ beAtR: 1.0, atr: 1.0 }),
  // The initial stop: one tick under the decision week's low, but never closer
  // than `minAtr` weekly ATRs under the close. The simulator's weekly default
  // is 0.5 ATR (sim-timeframe.js WEEKLY.stop). The strategy's is 1.0: of 0.5 /
  // 1.0 / 1.5 / 2.0 it was best on the in-sample years AND held out of sample
  // (docs/scorecard/weekly_strategy_backtest.md §4). At 0.5 the weekly noise
  // stops trades out before they start — the structure block's R:R then
  // measured stop tightness, and ranked outcomes BACKWARDS.
  stop: Object.freeze({ minAtr: 1.0 }),
});

/* ---------- the series ---------- */

/**
 * Everything the rules read, computed once per name. `daily` is
 * [{d,o,h,l,c,v}] ascending; `asOf` is the build date (see `toWeekly`, which
 * drops an unfinished final week).
 */
export function prepareSeries(daily, asOf = null, opts = {}) {
  const bars = toWeekly(daily, asOf);
  const closes = bars.map((b) => b.c);
  const s = {
    bars,
    closes,
    daily,
    dailyCloses: daily.map((b) => b.c),
    sma10: sma(closes, 10),
    sma30: sma(closes, 30),
    rsi: rsi(closes, 14),
    atr: atr(bars, 14),
    macd: macd(closes),
    vma10: sma(bars.map((b) => b.v || 0), 10),
    stage: new Array(bars.length).fill(null),
    age: new Array(bars.length).fill(0),
    // A research override of RULES.stop.minAtr, carried by the series so
    // every rule that reads it (planAt, runTrade) sees the same variant.
    stopAtr: opts.stopAtr ?? null,
  };
  for (let w = 0; w < bars.length; w++) {
    const st = stageAt(s, w);
    s.stage[w] = st;
    s.age[w] = st != null && w > 0 && s.stage[w - 1] === st ? s.age[w - 1] + 1 : st != null ? 1 : 0;
  }
  s.fwd = forwardReturns(s);
  return s;
}

/** The 30-week's slope over RULES.slopeWeeks, in weekly ATRs (null early on). */
export function slope30(s, w) {
  const k = RULES.slopeWeeks;
  const a = s.atr[w];
  if (w < k || s.sma30[w] == null || s.sma30[w - k] == null || !(a > 0)) return null;
  return (s.sma30[w] - s.sma30[w - k]) / a;
}

/**
 * Weinstein stage at week `w`: 1 base, 2 advance, 3 top, 4 decline, or null.
 *
 *   price above a RISING 30-week                 2
 *   price below a FALLING 30-week                4
 *   a FLAT 30-week                               1 after a decline, 3 after an advance
 *   price back above a still-FALLING 30-week     1  (basing; the line has not turned)
 *   price broken below a still-RISING 30-week    3  (topping; the advance is in doubt)
 *
 * "Rising" and "falling" are ATR-relative (RULES.flatAtr), which is what lets
 * one threshold serve a utility and a semiconductor.
 */
export function stageAt(s, w) {
  const sl = slope30(s, w);
  if (sl == null) return null;
  const c = s.closes[w];
  const line = s.sma30[w];
  const dir = sl > RULES.flatAtr ? 1 : sl < -RULES.flatAtr ? -1 : 0;
  const above = c > line;
  if (dir === 1) return above ? 2 : 3;
  if (dir === -1) return above ? 1 : 4;
  const p = w - RULES.priorWeeks;
  const prior = p >= 0 && s.sma30[p] != null ? line - s.sma30[p] : 0;
  return prior < 0 ? 1 : 3;
}

/**
 * Fixed-horizon forward return for a decision at each week: entry at the next
 * week's open, marked at the close `RULES.horizon` weeks after the decision.
 * The calibration yardstick — deliberately NOT the trade result, so the
 * drift baseline it is compared against means the same thing.
 */
function forwardReturns(s) {
  const H = RULES.horizon;
  const out = new Array(s.bars.length).fill(null);
  for (let w = 0; w + H < s.bars.length; w++) {
    const o = s.bars[w + 1].o;
    const c = s.bars[w + H].c;
    if (o > 0 && c > 0) out[w] = c / o - 1;
  }
  return out;
}

/* ---------- the setups ---------- */

const hi = (s, from, to) => {
  let m = -Infinity;
  for (let i = Math.max(0, from); i <= to; i++) m = Math.max(m, s.bars[i].h);
  return m;
};

/** Index of the highest high in [from, to] (the latest, on a tie). */
const hiIdx = (s, from, to) => {
  let m = -Infinity;
  let at = -1;
  for (let i = Math.max(0, from); i <= to; i++) {
    if (s.bars[i].h >= m) {
      m = s.bars[i].h;
      at = i;
    }
  }
  return at;
};

/**
 * Which setups week `w` presents, as `[{setup, status, why, facts}]`.
 *
 *   status "BUY"    every entry condition met; enter at Monday's open
 *   status "WATCH"  the setup is forming but not triggered — look again next
 *                   Sunday. This is the simulator's WAIT, on a weekly clock.
 *
 * Reads bars 0..w only. Scoring, vetoes and ranking happen in scorecard.js.
 */
export function setupsAt(s, w) {
  const out = [];
  const a = s.atr[w];
  const st = s.stage[w];
  if (st == null || !(a > 0) || s.sma10[w] == null || s.rsi[w] == null) return out;
  const b = s.bars[w];
  const c = b.c;

  // PULLBACK — a discount inside an established advance.
  {
    const R = RULES.pullback;
    const high = hi(s, w - R.highWeeks + 1, w);
    const depth = (high - c) / a;
    const vs10 = (c - s.sma10[w]) / a;
    const r = s.rsi[w];
    if (st === 2 && s.age[w] >= R.minAge && depth >= R.depthAtr && vs10 <= R.near10Atr && r >= R.rsi[0] && r <= R.rsi[1]) {
      // The trigger: the week TURNED — an up close, finishing in the upper half
      // of its range. A dip that is still falling is a WATCH.
      const upClose = w > 0 && c > s.closes[w - 1];
      const upperHalf = c >= (b.h + b.l) / 2;
      out.push({
        setup: "PULLBACK",
        status: upClose && upperHalf ? "BUY" : "WATCH",
        why: upClose && upperHalf ? "dipped, then bounced back up this week" : "dipping: wait for a week that closes higher",
        facts: { depthAtr: depth, vs10Atr: vs10, high },
      });
    }
  }

  // BREAKOUT — the resolution of a base, or strength inside a trend.
  {
    const R = RULES.breakout;
    const sl = slope30(s, w);
    // Stage 3 is allowed: a sideways range inside an advance flattens the
    // 30-week, so it reads as a top until it resolves — and a "top" that
    // breaks out to a new high was never a top. Weinstein calls that range a
    // continuation base; the breakout starts a new Stage 2.
    if (st != null && st !== 4 && sl != null && sl >= -RULES.flatAtr && w > R.baseWeeks) {
      let level = null;
      let at = null;
      for (let k = w; k > w - R.recentWeeks && k > R.baseWeeks; k--) {
        const j = hiIdx(s, k - R.baseWeeks, k - 1);
        const lv = s.bars[j].h;
        if (s.closes[k] > lv && k - j >= R.minBaseAge) {
          level = lv;
          at = k;
          break;
        }
      }
      if (level != null && c > level && (c - level) / a <= R.maxExtAtr) {
        out.push({
          setup: "BREAKOUT",
          status: "BUY",
          why: at === w ? "closed above its 6-month high this week" : "broke above its 6-month high last week and is still close to it",
          facts: { level, extAtr: (c - level) / a, breakoutIdx: at },
        });
      } else if (level == null) {
        const j = hiIdx(s, w - R.baseWeeks, w - 1);
        const lv = s.bars[j].h;
        if (lv > c && (lv - c) / a <= R.watchAtr && w - j >= R.minBaseAge) {
          out.push({
            setup: "BREAKOUT",
            status: "WATCH",
            why: "just under its 6-month high: buy if it closes above",
            facts: { level: lv, extAtr: (c - lv) / a, breakoutIdx: null },
          });
        }
      }
    }
  }

  // REVERSAL — a decline that has stopped going down.
  {
    const R = RULES.reversal;
    if (st === 1 && w >= R.lookback) {
      let declined = 0;
      for (let k = w - R.lookback + 1; k <= w; k++) if (s.stage[k] === 4) declined++;
      if (declined >= R.declineWeeks) {
        const lows = pivotsOf(s.bars, w - R.lookback + 1, w).filter((p) => p.type === "low" && !p.provisional);
        const higherLow = lows.length >= 2 && lows[lows.length - 1].price > lows[lows.length - 2].price;
        const above10 = c > s.sma10[w] && s.sma10[w - 2] != null && s.sma10[w] > s.sma10[w - 2];
        const momentum = s.rsi[w] >= R.rsiMin;
        if (higherLow && (above10 || momentum)) {
          const buy = above10 && momentum;
          out.push({
            setup: "REVERSAL",
            status: buy ? "BUY" : "WATCH",
            why: buy ? "has stopped falling and is climbing again" : "has stopped falling: wait for it to start climbing",
            facts: { declined, lastLow: lows[lows.length - 1].price, prevLow: lows[lows.length - 2].price },
          });
        }
      }
    }
  }
  return out;
}

/* ---------- the trade plan ---------- */

/** Weekly S/R: two years of pivots; two touches on a weekly chart is a level. */
export const LEVEL_WEEKS = 104;
export const LEVEL_TOUCHES = 2;
export const LEVEL_TOL_ATR = 0.5;
/** "Blue sky": no resistance above within two years. Headroom is capped here. */
export const BLUE_SKY_ATR = 6;

/**
 * The trade a decision at week `w` implies, before any fill: estimated entry
 * (this week's close stands in for Monday's open), the stop, the nearest
 * resistance above and support below, and the reward:risk between them.
 *
 * Reward:risk is a ROOM check, not an exit: the trail does the selling. A
 * resistance nearer than the stop is no trade at any score.
 */
export function planAt(s, w) {
  const a = s.atr[w];
  const entry = s.closes[w];
  const stop = stopFor(s, w);
  const risk = entry - stop;
  const piv = pivotsOf(s.bars, Math.max(0, w - LEVEL_WEEKS + 1), w);
  const lv = levels(piv, s.bars, s.atr, {
    anchor: w,
    tolAtr: LEVEL_TOL_ATR,
    minTouches: LEVEL_TOUCHES,
    nearAtr: 1e9,
    recentBars: 13,
  });
  const above = lv.filter((l) => l.price > entry + 0.5 * a).sort((x, y) => x.price - y.price);
  const below = lv.filter((l) => l.price < entry).sort((x, y) => y.price - x.price);
  const res = above[0] || null;
  const sup = below[0] || null;
  const headroom = res ? Math.min(res.price - entry, BLUE_SKY_ATR * a) : BLUE_SKY_ATR * a;
  return {
    entry,
    stop,
    risk,
    riskPct: entry > 0 ? (risk / entry) * 100 : null,
    atr: a,
    resistance: res ? { price: res.price, touches: res.touches } : null,
    support: sup ? { price: sup.price, touches: sup.touches } : null,
    blueSky: !res,
    target: res ? res.price : null,
    rr: risk > 0 ? headroom / risk : null,
  };
}

/**
 * The strategy's initial stop for a decision at week `w`: one tick under the
 * week's low, or `minAtr` ATRs under the close if that is lower. With
 * minAtr = 0.5 this is exactly the simulator's weekly `defaultStop`.
 */
export function stopFor(s, w) {
  const minAtr = s.stopAtr ?? RULES.stop.minAtr;
  return defaultStop({ stop: { rule: "barLow", minAtr } }, s.bars, s.atr, w, tickFor(s.closes[w]));
}

/** One tick: a cent, or finer under a dollar (mirrors sim-timeframe priceDecimals). */
export function tickFor(price) {
  if (!(price > 0) || price >= 1) return 0.01;
  return Math.pow(10, -Math.min(8, 3 - Math.floor(Math.log10(price))));
}

/* ---------- the trade, played out ---------- */

/**
 * Where the trail wants the stop after the close of week `i`, or null. Break-
 * even at +1R; from then on the 10-week SMA less one ATR. The caller hands the
 * result to `moveStop`, which refuses anything that would widen the stop or
 * cross the price — the ratchet is enforced in one place, sim-engine.js.
 */
export function trailStop(s, i, entryPrice, initialStop) {
  const risk = entryPrice - initialStop;
  if (!(risk > 0)) return null;
  if ((s.closes[i] - entryPrice) / risk < RULES.trail.beAtR) return null;
  let stop = entryPrice;
  if (s.sma10[i] != null && s.atr[i] != null) stop = Math.max(stop, s.sma10[i] - RULES.trail.atr * s.atr[i]);
  return stop;
}

/**
 * Play the strategy's trade from a decision at week `w` through to its exit,
 * using ONLY the rules above. Returns:
 *
 *   {w, entryIdx, entryPrice, initialStop, exitIdx, exitPrice, reason,
 *    r, pct, weeks, maeR, open}
 *
 * `reason` is stop | trail | thesis | time | open. A trade still running on
 * the last bar comes back `open: true`, marked at the last close, with
 * `exitIdx: null` — it is not yet an outcome, and `analogueStats` excludes it.
 *
 * `opts.entryPrice` / `opts.initialStop` replay a REAL position (the BOOK):
 * its actual average cost, and the stop the rules would have given it.
 * `opts.trace` adds `stops: [[weekIdx, stopAfterThatWeek], …]` — the stop the
 * rules held going into each following week (the backtest's heat, the BOOK's
 * stop history).
 *
 * Returns null when there is no next week to enter on, or when Monday opens
 * at or below the stop (the order would be cancelled, not filled).
 */
export function runTrade(s, w, opts = {}) {
  const n = s.bars.length;
  if (w + 1 >= n) return null;
  const e = w + 1;
  const entryPrice = opts.entryPrice ?? s.bars[e].o;
  const initialStop = opts.initialStop ?? stopFor(s, w);
  if (!(entryPrice > initialStop)) return null;
  let t = openTrade({ side: "long", stop: initialStop, entryIndex: e, entryPrice });
  let armed = s.closes[w] > (s.sma30[w] ?? Infinity);
  let low = entryPrice;
  let reason = "open";
  let trailed = false;
  const stops = opts.trace ? [] : null;

  for (let i = e; i < n; i++) {
    low = Math.min(low, s.bars[i].l);
    const stepped = stepWeek(s, t, i);
    t = stepped.trade;
    if (stepped.stopped) {
      reason = trailed ? "trail" : "stop";
      break;
    }
    // Friday's close: the three discretionary rules, each filled at Monday's
    // open. Thesis first — a broken Stage 2 is the stronger reason to be out.
    const line = s.sma30[i];
    if (line != null && s.closes[i] > line) armed = true;
    const held = i - e + 1;
    const why = armed && line != null && s.closes[i] < line ? "thesis" : held >= RULES.maxHold ? "time" : null;
    if (why) {
      if (i + 1 >= n) {
        // Decided, but no Monday yet: the exit is known, the fill is not.
        reason = "open";
        break;
      }
      const d = decideExit(t, s.bars, i, { fill: "nextOpen", reason: why });
      t = d.trade;
      if (d.index > i) low = Math.min(low, s.bars[d.index].o);
      reason = why;
      break;
    }
    const want = trailStop(s, i, entryPrice, initialStop);
    if (want != null) {
      const moved = moveStop(t, want, s.closes[i]);
      if (moved.stop !== t.stop) trailed = true;
      t = moved;
    }
    if (stops) stops.push([i, t.stop]);
  }

  const open = isOpen(t);
  const last = t.exits[t.exits.length - 1];
  const mark = open ? s.closes[n - 1] : null;
  const st = tradeStats(t, mark);
  const risk = entryPrice - initialStop;
  return {
    w,
    entryIdx: e,
    entryPrice,
    initialStop,
    stop: t.stop,
    exitIdx: open ? null : last.index,
    exitPrice: open ? null : last.price,
    reason: open ? "open" : reason,
    r: st.r,
    pct: st.total,
    weeks: (open ? n - 1 : last.index) - e + 1,
    maeR: risk > 0 ? (low - entryPrice) / risk : 0,
    open,
    ...(stops ? { stops } : {}),
  };
}

/**
 * Run the resting stop through week `i` on its DAILY bars. A weekly bar only
 * knows its open, high, low and close, so a Wednesday earnings gap straight
 * through the stop would "fill" at the stop on the weekly bar — and the one
 * risk the earnings veto exists for would vanish from the evidence. On the
 * daily bars it fills at Wednesday's open, as a real resting order does.
 *
 * Stricter than the simulator's weekly mode, which fills on the weekly bar
 * (sim-engine.js); a strategy's evidence should be the realistic version.
 * Falls back to the weekly bar when the series has no daily bars attached.
 */
function stepWeek(s, t, i) {
  const bar = s.bars[i];
  if (!s.daily || bar.di == null) return stepTrade(t, bar, i);
  const from = i > 0 && s.bars[i - 1].di != null ? s.bars[i - 1].di + 1 : Math.max(0, bar.di - 4);
  for (let k = from; k <= bar.di; k++) {
    const r = stepTrade(t, s.daily[k], i);
    if (r.stopped) return r;
  }
  return { trade: t, stopped: false };
}

/* ---------- the event table: this strategy's own history on a name ---------- */

/**
 * Every trade the strategy would have taken on this name, one at a time:
 * `[{w, setup, trade}]` in time order. A BUY while a trade is running is
 * ignored, exactly as the book would ignore it. When a week offers two BUY
 * setups, the first in SETUPS order is taken (they are near-exclusive by
 * construction: a PULLBACK is below the 13-week high and a BREAKOUT above the
 * 26-week one).
 *
 * `from` is the first week eligible to trade — enough history for every
 * indicator the setups read.
 */
export function eventTable(s, from = 60) {
  const out = [];
  let busyUntil = -1; // the last bar a running trade occupies
  for (let w = from; w < s.bars.length - 1; w++) {
    if (w <= busyUntil) continue;
    const buy = setupsAt(s, w).find((x) => x.status === "BUY");
    if (!buy) continue;
    const trade = runTrade(s, w);
    if (!trade) continue;
    out.push({ w, setup: buy.setup, trade });
    busyUntil = trade.open ? Infinity : trade.exitIdx;
  }
  return out;
}

/**
 * Like-week analogues for a decision at week `w`: this strategy's completed
 * trades on this name, in the same setup, whose EXIT was at or before `w` —
 * the outcomes a trader standing at `w` could actually have known.
 *
 *   n, win (share of R > 0), meanR, medianR, worstR, maeR (mean)
 *   fwd       mean 13-week forward return of those decisions
 *   base      the name's own mean 13-week forward return over every week whose
 *             outcome was known at `w` — the drift an always-invested holder
 *             earned. fwd − base is the EDGE, as on the Scanner.
 *   shrunkR   meanR shrunk towards `prior` (the universe's expectancy for the
 *             setup) by n / (n + SHRINK_K): with three trades on a name, the
 *             universe says more than the name does.
 */
export const SHRINK_K = 20; // the Scanner's constant (scanner.js)

export function analogueStats(s, events, w, setup, prior = null) {
  const H = RULES.horizon;
  const done = events.filter((e) => e.setup === setup && e.w < w && !e.trade.open && e.trade.exitIdx <= w);
  const rs = done.map((e) => e.trade.r);
  const n = rs.length;
  const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
  const fwds = done.filter((e) => e.w + H <= w && s.fwd[e.w] != null).map((e) => s.fwd[e.w]);
  let bSum = 0;
  let bN = 0;
  for (let j = 0; j + H <= w; j++) {
    if (s.fwd[j] != null) {
      bSum += s.fwd[j];
      bN++;
    }
  }
  const meanR = mean(rs);
  const p = prior?.meanR ?? 0;
  const shrunkR = n ? (n * meanR + SHRINK_K * p) / (n + SHRINK_K) : p;
  const sorted = [...rs].sort((a, b) => a - b);
  return {
    setup,
    n,
    win: n ? rs.filter((r) => r > 0).length / n : null,
    meanR,
    medianR: n ? (n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2) : null,
    worstR: n ? sorted[0] : null,
    maeR: mean(done.map((e) => e.trade.maeR)),
    fwd: mean(fwds),
    base: bN ? bSum / bN : null,
    edge: fwds.length && bN ? mean(fwds) - bSum / bN : null,
    prior: prior?.meanR ?? null,
    shrunkR,
    recent: done.slice(-8).map((e) => ({
      d: s.bars[e.w].d,
      r: e.trade.r,
      reason: e.trade.reason,
      weeks: e.trade.weeks,
    })),
  };
}

/**
 * The universe's expectancy per setup from every name's event table, counting
 * only trades whose exit date is on or before `asOfIso`. The prior the
 * analogue block shrinks towards. `tables` is `[{s, events}]`.
 */
export function universePriors(tables, asOfIso) {
  const acc = Object.fromEntries(SETUPS.map((k) => [k, { n: 0, sum: 0, wins: 0 }]));
  for (const { s, events } of tables) {
    for (const e of events) {
      if (e.trade.open || s.bars[e.trade.exitIdx].d > asOfIso) continue;
      const a = acc[e.setup];
      a.n++;
      a.sum += e.trade.r;
      if (e.trade.r > 0) a.wins++;
    }
  }
  return Object.fromEntries(
    SETUPS.map((k) => [k, { n: acc[k].n, meanR: acc[k].n ? acc[k].sum / acc[k].n : null, win: acc[k].n ? acc[k].wins / acc[k].n : null }])
  );
}

/** Index of the last completed week dated on or before `iso`, or -1. */
export function weekAsOf(s, iso) {
  let lo = 0;
  let hi2 = s.bars.length - 1;
  let out = -1;
  while (lo <= hi2) {
    const mid = (lo + hi2) >> 1;
    if (s.bars[mid].d <= iso) {
      out = mid;
      lo = mid + 1;
    } else hi2 = mid - 1;
  }
  return out;
}
