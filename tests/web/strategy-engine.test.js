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
  findEvents,
  findStreakEvents,
  liveBounce,
  liveStreak,
  computeStats,
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
