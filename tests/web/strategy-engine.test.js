/* Unit tests for the shared strategy engine.

   These lock the user-facing numbers (win rate, average/median return, worst
   trade) and the event-detection logic that the strategy pages, league tables
   and scanner all share. Run with:  node --test tests/web/

   The engine functions are pure (no DOM/fetch/state), so the tests just feed
   hand-built bar series with known outcomes and assert the results. */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  HORIZONS,
  STREAK_HORIZONS,
  MULTIDAY_HORIZONS,
  BREAKOUT_HORIZONS,
  RANGE_HORIZONS,
  CROSS_HORIZONS,
  findEvents,
  findStreakEvents,
  findMultiDayEvents,
  findBreakoutEvents,
  findRangeEvents,
  findCrossEvents,
  liveBounce,
  liveStreak,
  liveMultiDay,
  liveBreakout,
  liveRange,
  liveCross,
  valueMetrics,
  computeStats,
  indexAsOf,
  forwardReturn,
  median,
  fmt,
  fmtInt,
  cls,
  escapeHtml,
} from "../../web/js/strategy-engine.js";

// bars are [date_iso, open, close]
const bar = (date, open, close) => [date, open, close];
// build a bar series from closes (open defaults to close) starting at a date
const fromCloses = (closes, opens = null) =>
  closes.map((c, i) => bar(`2020-01-${String(i + 1).padStart(2, "0")}`, opens ? opens[i] : c, c));

const approx = (a, b, eps = 1e-9) =>
  assert.ok(Math.abs(a - b) <= eps, `expected ${a} ≈ ${b}`);

/* ---------- findEvents ---------- */

test("findEvents: detects a single down trigger with correct forward returns", () => {
  // close[3] drops 10% vs close[2]; recovers +5/+10/+10 over the next 3 days.
  const closes = [100, 100, 100, 90, 94.5, 99, 99, 99, 99, 99];
  const bars = fromCloses(closes);
  const events = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "all" });

  assert.equal(events.length, 1);
  const e = events[0];
  assert.equal(e.date, "2020-01-04"); // index 3
  approx(e.trig, -10, 1e-9);
  approx(e.d1, 5, 1e-9);   // 94.5 / 90 - 1
  approx(e.d2, 10, 1e-9);  // 99   / 90 - 1
  approx(e.d3, 10, 1e-9);  // 99   / 90 - 1
});

test("findEvents: direction 'up' fires on a rally, not a drop", () => {
  const closes = [100, 100, 100, 110, 110, 110, 110, 110, 110, 110]; // +10% at index 3
  const bars = fromCloses(closes);
  const up = findEvents(bars, { direction: "up", threshold: 5, entry: "close", range: "all" });
  const down = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "all" });
  assert.equal(up.length, 1);
  assert.equal(up[0].date, "2020-01-04");
  approx(up[0].trig, 10, 1e-9);
  assert.equal(down.length, 0);
});

test("findEvents: entry 'open' enters at the next day's open", () => {
  // same trigger at index 3, but next day's open (index 4) is 90, distinct from its close 94.5
  const closes = [100, 100, 100, 90, 94.5, 99, 99, 99, 99, 99];
  const opens = closes.slice();
  opens[4] = 90;
  const bars = fromCloses(closes, opens);
  const events = findEvents(bars, { direction: "down", threshold: 5, entry: "open", range: "all" });

  assert.equal(events.length, 1);
  const e = events[0];
  // entry = open[4] = 90; exits are closes[5], closes[6], closes[7] = 99,99,99
  approx(e.d1, 10, 1e-9);
  approx(e.d2, 10, 1e-9);
  approx(e.d3, 10, 1e-9);
});

test("findEvents: range '5y' filters out events older than 5 years", () => {
  // two -10% triggers: one in 2010 (old), one in 2020 (recent). last bar is 2020-01-09.
  const bars = [
    bar("2010-01-01", 100, 100),
    bar("2010-01-02", 100, 100),
    bar("2010-01-05", 90, 90),   // i=2 trigger (old)
    bar("2010-01-06", 99, 99),
    bar("2010-01-07", 99, 99),
    bar("2010-01-08", 99, 99),
    bar("2020-01-01", 100, 100),
    bar("2020-01-02", 100, 100),
    bar("2020-01-05", 90, 90),   // i=8 trigger (recent)
    bar("2020-01-06", 99, 99),
    bar("2020-01-07", 99, 99),
    bar("2020-01-08", 99, 99),
    bar("2020-01-09", 99, 99),
  ];
  const all = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "all" });
  const recent = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "5y" });
  assert.equal(all.length, 2);
  assert.equal(recent.length, 1);
  assert.equal(recent[0].date, "2020-01-05");
});

test("findEvents: never fires on the last bars (no forward returns to score)", () => {
  // a -10% drop in the final 3 bars must be ignored (close entry needs 3 forward bars)
  const closes = [100, 100, 100, 100, 100, 100, 100, 90, 88, 87];
  const bars = fromCloses(closes);
  const events = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "all" });
  assert.equal(events.length, 0);
});

test("HORIZONS is the documented [1,2,3]", () => {
  assert.deepEqual(HORIZONS, [1, 2, 3]);
});

/* ---------- findStreakEvents ---------- */

test("findStreakEvents: detects a run of N consecutive down closes", () => {
  // 100,99,98,97 = three down days ending at index 3, then a recovery
  const closes = [100, 99, 98, 97, 98, 99, 100, 101, 102];
  const bars = fromCloses(closes);
  const events = findStreakEvents(bars, { direction: "down", streak: 3, entry: "close", range: "all" });

  assert.equal(events.length, 1);
  const e = events[0];
  assert.equal(e.date, "2020-01-04"); // index 3
  assert.equal(e.streak, 3);
  // entry = close[3] = 97; horizons [1,3,5] -> closes[4], closes[6], closes[8]
  approx(e.d1, (98 / 97 - 1) * 100, 1e-9);
  approx(e.d2, (100 / 97 - 1) * 100, 1e-9);
  approx(e.d3, (102 / 97 - 1) * 100, 1e-9);
});

test("findStreakEvents: a longer run fires once per qualifying day (overlapping)", () => {
  // five consecutive down days; with N=3 the 3rd, 4th and 5th down days each qualify
  const closes = [100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100, 101];
  const bars = fromCloses(closes);
  const events = findStreakEvents(bars, { direction: "down", streak: 3, entry: "close", range: "all" });
  // down days are indices 1..5; runs of >=3 complete at indices 3, 4, 5
  assert.equal(events.length, 3);
  assert.deepEqual(events.map(e => e.date), ["2020-01-04", "2020-01-05", "2020-01-06"]);
});

test("findStreakEvents: streak below 2 is floored to 2", () => {
  const closes = [100, 99, 98, 99, 100, 101, 102, 103, 104];
  const bars = fromCloses(closes);
  const n1 = findStreakEvents(bars, { direction: "down", streak: 1, entry: "close", range: "all" });
  const n2 = findStreakEvents(bars, { direction: "down", streak: 2, entry: "close", range: "all" });
  assert.deepEqual(n1, n2);
  assert.equal(n2.length, 1); // one 2-down run completing at index 2
  assert.equal(n2[0].streak, 2);
});

test("STREAK_HORIZONS is the documented [1,3,5]", () => {
  assert.deepEqual(STREAK_HORIZONS, [1, 3, 5]);
});

/* ---------- live signals (scanner) ---------- */

test("liveBounce: fires on the latest bar's move", () => {
  const down = fromCloses([100, 100, 90]); // -10% on the last bar
  const dRes = liveBounce(down, { direction: "down", threshold: 5 });
  assert.equal(dRes.triggered, true);
  approx(dRes.move, -10, 1e-9);
  assert.equal(liveBounce(down, { direction: "up", threshold: 5 }).triggered, false);

  const up = fromCloses([100, 100, 110]);
  assert.equal(liveBounce(up, { direction: "up", threshold: 5 }).triggered, true);
});

test("liveBounce: guards a too-short series", () => {
  const r = liveBounce([], { direction: "down", threshold: 5 });
  assert.equal(r.triggered, false);
  assert.ok(Number.isNaN(r.move));
});

test("liveStreak: counts the current run and triggers at >= N", () => {
  const bars = fromCloses([100, 99, 98, 97]); // 3 down closes ending now
  assert.deepEqual(liveStreak(bars, { direction: "down", streak: 3 }), { triggered: true, run: 3 });
  assert.equal(liveStreak(bars, { direction: "down", streak: 4 }).triggered, false);
  assert.equal(liveStreak(bars, { direction: "up", streak: 2 }).run, 0);
});

/* ---------- computeStats ---------- */

test("computeStats: rate / avg / med / worst / best per horizon", () => {
  const events = [
    { d1: 10, d2: -10, d3: 0 },
    { d1: 20, d2: 30, d3: 0 },
    { d1: -5, d2: -10, d3: 0 },
  ];
  const [s1, s2, s3] = computeStats(events);

  assert.equal(s1.n, 3);
  assert.equal(s1.wins, 2);
  approx(s1.rate, (2 / 3) * 100, 1e-9);
  approx(s1.avg, 25 / 3, 1e-9);
  assert.equal(s1.med, 10);
  assert.equal(s1.worst, -5);
  assert.equal(s1.best, 20);

  assert.equal(s2.wins, 1);
  assert.equal(s2.med, -10);
  assert.equal(s2.best, 30);

  assert.equal(s3.wins, 0);
  assert.equal(s3.rate, 0);
  assert.equal(s3.best, 0);
});

test("computeStats: empty input yields n=0 and NaN stats", () => {
  const stats = computeStats([]);
  assert.equal(stats.length, 3);
  for (const s of stats) {
    assert.equal(s.n, 0);
    assert.equal(s.wins, 0);
    assert.ok(Number.isNaN(s.rate));
    assert.ok(Number.isNaN(s.avg));
    assert.ok(Number.isNaN(s.med));
  }
});

/* ---------- median ---------- */

test("median: odd and even length", () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([1, 2, 3, 4]), 2.5);
  // must not mutate the input
  const arr = [3, 1, 2];
  median(arr);
  assert.deepEqual(arr, [3, 1, 2]);
});

/* ---------- formatters ---------- */

test("fmt: sign, one decimal, unicode minus, em-dash for non-finite", () => {
  assert.equal(fmt(1.23), "+1.2%");
  assert.equal(fmt(-3.46), "−3.5%"); // U+2212 minus, rounds to 3.5
  assert.equal(fmt(0), "0.0%");
  assert.equal(fmt(NaN), "—");
  assert.equal(fmt(Infinity), "—");
});

test("fmtInt: rounds finite, em-dash otherwise", () => {
  assert.equal(fmtInt(3.4), "3");
  assert.equal(fmtInt(3.6), "4");
  assert.equal(fmtInt(NaN), "—");
});

test("cls: positive/negative/zero/non-finite", () => {
  assert.equal(cls(5), "cell-pos");
  assert.equal(cls(-5), "cell-neg");
  assert.equal(cls(0), "");
  assert.equal(cls(NaN), "");
});

test("escapeHtml: escapes the five HTML-sensitive characters", () => {
  assert.equal(escapeHtml("&"), "&amp;");
  assert.equal(escapeHtml("<"), "&lt;");
  assert.equal(escapeHtml(">"), "&gt;");
  assert.equal(escapeHtml('"'), "&quot;");
  assert.equal(escapeHtml("'"), "&#39;");
  assert.equal(escapeHtml("a<b>&c"), "a&lt;b&gt;&amp;c");
});

/* ---------- horizon constants ---------- */

test("new horizon constants are the documented values", () => {
  assert.deepEqual(MULTIDAY_HORIZONS, [1, 5, 10]);
  assert.deepEqual(BREAKOUT_HORIZONS, [1, 5, 10]);
  assert.deepEqual(RANGE_HORIZONS, [1, 5, 10]);
  assert.deepEqual(CROSS_HORIZONS, [5, 10, 20]);
});

/* ---------- findMultiDayEvents ---------- */

test("findMultiDayEvents: fires on a trailing N-day move past the threshold", () => {
  // index 4 closes 10% below index 1 (the close N=3 days earlier), then flat.
  const closes = [100, 100, 100, 100, 90, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100];
  const bars = fromCloses(closes);
  const ev = findMultiDayEvents(bars, { direction: "down", threshold: 5, window: 3, entry: "close", range: "all" });
  assert.equal(ev.length, 1);
  assert.equal(ev[0].date, "2020-01-05"); // index 4
  approx(ev[0].trig, -10, 1e-9);          // 90 / 100 - 1
  approx(ev[0].d1, (100 / 90 - 1) * 100, 1e-9);
});

test("findMultiDayEvents: 'up' fires on a multi-day rally, not a fall", () => {
  const closes = [100, 100, 100, 100, 110, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100];
  const bars = fromCloses(closes);
  const up = findMultiDayEvents(bars, { direction: "up", threshold: 5, window: 3, entry: "close", range: "all" });
  const down = findMultiDayEvents(bars, { direction: "down", threshold: 5, window: 3, entry: "close", range: "all" });
  assert.equal(up.length, 1);
  approx(up[0].trig, 10, 1e-9);
  assert.equal(down.length, 0);
});

/* ---------- findBreakoutEvents ---------- */

test("findBreakoutEvents: 'up' fires when the close clears the prior N-day high", () => {
  // flat at 10, then a jump to 20 that tops the prior 3-day high of 10.
  const closes = [10, 10, 10, 10, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20];
  const bars = fromCloses(closes);
  const ev = findBreakoutEvents(bars, { direction: "up", lookback: 3, entry: "close", range: "all" });
  assert.equal(ev.length, 1);
  assert.equal(ev[0].date, "2020-01-05"); // index 4
  approx(ev[0].trig, 100, 1e-9);          // 20 / 10 - 1 beyond the broken high
  approx(ev[0].d1, 0, 1e-9);              // flat afterwards
});

test("findBreakoutEvents: 'down' fires on a fresh N-day low", () => {
  const closes = [10, 10, 10, 10, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5];
  const bars = fromCloses(closes);
  const up = findBreakoutEvents(bars, { direction: "up", lookback: 3, entry: "close", range: "all" });
  const down = findBreakoutEvents(bars, { direction: "down", lookback: 3, entry: "close", range: "all" });
  assert.equal(down.length, 1);
  approx(down[0].trig, -50, 1e-9);        // 5 / 10 - 1
  assert.equal(up.length, 0);
});

/* ---------- findRangeEvents ---------- */

test("findRangeEvents: fires once when a fresh tight range completes", () => {
  // a noisy ramp, then four flat closes at 100 (a +-2% range), then a ramp up.
  const closes = [50, 60, 70, 80, 100, 100, 100, 100, 110, 115, 120, 125, 130, 135, 140, 145, 150, 155];
  const bars = fromCloses(closes);
  const ev = findRangeEvents(bars, { band: 2, window: 4, entry: "close", range: "all" });
  assert.equal(ev.length, 1);
  assert.equal(ev[0].date, "2020-01-08"); // index 7 — last of the four flat closes
  approx(ev[0].trig, 0, 1e-9);            // zero spread
  approx(ev[0].d1, 10, 1e-9);            // 110 / 100 - 1
});

/* ---------- findCrossEvents ---------- */

test("findCrossEvents: 'up' fires when the close crosses above its N-day average", () => {
  const closes = [10, 10, 10, 9, 8, ...Array(25).fill(12)]; // dips below, then jumps above
  const bars = fromCloses(closes);
  const ev = findCrossEvents(bars, { direction: "up", period: 3, entry: "close", range: "all" });
  assert.equal(ev.length, 1);
  assert.equal(ev[0].date, "2020-01-06"); // index 5 — first close above the 3-day MA
  approx(ev[0].trig, (12 / (29 / 3) - 1) * 100, 1e-9); // 12 vs MA of (9+8+12)/3
  approx(ev[0].d1, 0, 1e-9);             // flat at 12 afterwards
});

test("findCrossEvents: up- and down-crosses never share a bar", () => {
  const closes = [10, 10, 10, 9, 8, ...Array(25).fill(12)];
  const bars = fromCloses(closes);
  const up = findCrossEvents(bars, { direction: "up", period: 3, entry: "close", range: "all" });
  const down = findCrossEvents(bars, { direction: "down", period: 3, entry: "close", range: "all" });
  // the dip below the MA is a down-cross (index 3); the recovery is an up-cross
  // (index 5). Each bar is at most one kind of cross — the dates must be disjoint.
  assert.equal(down.length, 1);
  assert.equal(down[0].date, "2020-01-04"); // index 3
  assert.equal(up.length, 1);
  const overlap = up.filter(e => down.some(d => d.date === e.date));
  assert.equal(overlap.length, 0);
});

/* ---------- live signals: new strategies ---------- */

test("liveMultiDay: fires on the trailing window move of the latest bar", () => {
  const bars = fromCloses([100, 100, 100, 100, 90]); // -10% over 3 days at the end
  const r = liveMultiDay(bars, { direction: "down", threshold: 5, window: 3 });
  assert.equal(r.triggered, true);
  approx(r.move, -10, 1e-9);
  assert.equal(liveMultiDay(bars, { direction: "up", threshold: 5, window: 3 }).triggered, false);
});

test("liveBreakout: fires when the latest close is a fresh N-day extreme", () => {
  const up = fromCloses([10, 10, 10, 10, 20]);
  assert.equal(liveBreakout(up, { direction: "up", lookback: 3 }).triggered, true);
  approx(liveBreakout(up, { direction: "up", lookback: 3 }).beyond, 100, 1e-9);
  assert.equal(liveBreakout(up, { direction: "down", lookback: 3 }).triggered, false);
});

test("liveRange: fires when the latest window sits inside the band", () => {
  const tight = fromCloses([50, 60, 70, 100, 100, 100, 100]);
  assert.equal(liveRange(tight, { band: 2, window: 4 }).triggered, true);
  const wide = fromCloses([50, 60, 70, 80, 90, 100, 110]);
  assert.equal(liveRange(wide, { band: 2, window: 4 }).triggered, false);
});

test("liveCross: fires when the latest bar crosses its N-day average", () => {
  const bars = fromCloses([10, 10, 10, 9, 8, 12]); // crosses up on the last bar
  assert.equal(liveCross(bars, { direction: "up", period: 3 }).triggered, true);
  assert.equal(liveCross(bars, { direction: "down", period: 3 }).triggered, false);
});

/* ---------- valueMetrics ---------- */

test("valueMetrics: rich/cheap snapshots are correct on a short series", () => {
  const rich = valueMetrics(fromCloses([10, 20, 30, 40, 50])); // at its high
  approx(rich.offHigh52, 0, 1e-9);
  approx(rich.vsSma200, (50 / 30 - 1) * 100, 1e-9);
  approx(rich.rangePos5y, 100, 1e-9);
  assert.equal(rich.nCheap, 0); // too short for the forward-return evidence

  const cheap = valueMetrics(fromCloses([50, 40, 30, 20, 10])); // at its low
  approx(cheap.offHigh52, -80, 1e-9);
  approx(cheap.vsSma200, (10 / 30 - 1) * 100, 1e-9);
  approx(cheap.rangePos5y, 0, 1e-9);
});

test("valueMetrics: fwdWhenCheap is a median, robust to a price-spike outlier", () => {
  // 200 flat closes at 100, then 30 at 90 (a step below the 200-day average so
  // those days count as 'cheap'). One forward close is spiked to 900 — the kind
  // of tiny-base ratio blow-up that wrecks a mean. The median must shrug it off.
  const closes = [...Array(200).fill(100), ...Array(30).fill(90)];
  closes[221] = 900; // 21 days ahead of the first cheap day (index 200)
  const v = valueMetrics(closes.map((c, i) => [`d${i}`, c, c]));
  assert.equal(v.nCheap, 9);            // cheap days at indices 200..208
  approx(v.fwdWhenCheap, 0, 1e-9);      // median forward return is 0, not ~100%
});

test("valueMetrics: empty series yields a NaN snapshot", () => {
  const v = valueMetrics([]);
  assert.ok(Number.isNaN(v.last));
  assert.equal(v.nCheap, 0);
});

/* ---------- indexAsOf (scanner rewind) ---------- */

const dateBars = (...dates) => dates.map(d => [d, 1, 1]);

test("indexAsOf: exact date match returns that index", () => {
  const bars = dateBars("2020-01-01", "2020-01-02", "2020-01-03");
  assert.equal(indexAsOf(bars, "2020-01-02"), 1);
});

test("indexAsOf: a date between bars returns the earlier (on-or-before) index", () => {
  // no bar on the 4th (weekend/holiday) — snap back to the 3rd
  const bars = dateBars("2020-01-01", "2020-01-03", "2020-01-06");
  assert.equal(indexAsOf(bars, "2020-01-04"), 1);
  assert.equal(indexAsOf(bars, "2020-01-05"), 1);
});

test("indexAsOf: a date before the first bar returns -1", () => {
  const bars = dateBars("2020-01-02", "2020-01-03");
  assert.equal(indexAsOf(bars, "2020-01-01"), -1);
});

test("indexAsOf: a date at or after the last bar returns the last index", () => {
  const bars = dateBars("2020-01-01", "2020-01-02", "2020-01-03");
  assert.equal(indexAsOf(bars, "2020-01-03"), 2);
  assert.equal(indexAsOf(bars, "2020-06-01"), 2);
});

test("indexAsOf: an empty series returns -1", () => {
  assert.equal(indexAsOf([], "2020-01-01"), -1);
});

/* ---------- forwardReturn (scanner outcome) ---------- */

test("forwardReturn: known forward close-to-close return, in percent", () => {
  // enter at close 100 (index 0), exit two bars later at 110 -> +10%
  const bars = [["d0", 1, 100], ["d1", 1, 105], ["d2", 1, 110]];
  approx(forwardReturn(bars, 0, 2), 10, 1e-9);
});

test("forwardReturn: exit beyond the series is NaN (window not elapsed)", () => {
  const bars = [["d0", 1, 100], ["d1", 1, 105]];
  assert.ok(Number.isNaN(forwardReturn(bars, 1, 3)));
  assert.ok(Number.isNaN(forwardReturn(bars, 0, 2)));   // exit index == length
});

test("forwardReturn: an invalid (negative) index is NaN", () => {
  const bars = [["d0", 1, 100], ["d1", 1, 105]];
  assert.ok(Number.isNaN(forwardReturn(bars, -1, 1)));
});

/* ---------- Phase 3: max adverse excursion + regime filter ---------- */

test("findEvents: event carries max adverse excursion (mae) over the hold", () => {
  // trigger at index 3 (90, -10%); gradual dip to 86 (each step < 5% so it is
  // not itself a second trigger) before recovering.
  const closes = [100, 100, 100, 90, 88, 86, 99, 99, 99, 99];
  const bars = fromCloses(closes);
  const events = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "all" });
  assert.equal(events.length, 1);
  // entry 90; path 88/86/99 -> worst drawdown = 86/90 - 1 = -4.4444%
  approx(events[0].mae, (86 / 90 - 1) * 100, 1e-9);
});

test("findEvents: mae is 0 when the hold never dips below entry", () => {
  const closes = [100, 100, 100, 90, 94.5, 99, 99, 99, 99, 99]; // only rises after entry
  const bars = fromCloses(closes);
  const events = findEvents(bars, { direction: "down", threshold: 5, entry: "close", range: "all" });
  approx(events[0].mae, 0, 1e-9);
});

test("findEvents: regime 'up' keeps only events that fired at/above the 200-day", () => {
  // 205 flat bars at 100, then a -10% drop -> the drop sits BELOW the ~100 SMA.
  const closes = new Array(205).fill(100).concat([90, 95, 99, 99]);
  const bars = fromCloses(closes);
  const base = { direction: "down", threshold: 5, entry: "close", range: "all" };
  assert.equal(findEvents(bars, base).length, 1);                       // no filter
  assert.equal(findEvents(bars, { ...base, regime: "down" }).length, 1); // below 200d -> kept
  assert.equal(findEvents(bars, { ...base, regime: "up" }).length, 0);   // not above 200d -> dropped
});
