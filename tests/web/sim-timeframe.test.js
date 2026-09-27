// Unit tests for the simulator's timeframes (web/v2/js/sim-timeframe.js).
//
// The load-bearing ones are the resampler's: a weekly candle must be exactly
// the days it was built from, it must never include a day that had not
// happened by the week's last session, and an unfinished final week must not
// be presented as a finished one.

import assert from "node:assert/strict";
import test from "node:test";

import {
  DAILY,
  WEEKLY,
  defaultStop,
  priceDecimals,
  runwayBars,
  timeframe,
  toWeekly,
  warmupBars,
  weekKey,
} from "../../web/v2/js/sim-timeframe.js";

/** Daily bars on the given ISO dates, with distinct, checkable prices. */
function days(dates) {
  return dates.map((d, i) => ({
    d,
    o: 100 + i,
    h: 110 + i,
    l: 90 + i,
    c: 105 + i,
    v: 1000 * (i + 1),
  }));
}

/* ---------- weekKey ---------- */

test("weekKey: Monday to Sunday is one ISO week, keyed by its Thursday", () => {
  const mon = weekKey("2024-06-03");
  for (const d of ["2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07", "2024-06-09"]) {
    assert.equal(weekKey(d), mon, d);
  }
  assert.equal(mon, "2024-06-06");
  assert.notEqual(weekKey("2024-06-10"), mon);
});

test("weekKey: the year boundary follows ISO 8601, not the calendar", () => {
  // Fri 1 Jan 2021 belongs to week 53 of 2020, alongside Mon 28 Dec 2020.
  assert.equal(weekKey("2021-01-01"), weekKey("2020-12-28"));
  assert.notEqual(weekKey("2021-01-04"), weekKey("2021-01-01"));
});

/* ---------- toWeekly ---------- */

test("toWeekly: open first, close last, extremes and summed volume", () => {
  const daily = days(["2024-06-03", "2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07"]);
  daily[2].h = 150; // the week's high is on Wednesday
  daily[3].l = 50; // ...and its low on Thursday
  const [w] = toWeekly(daily);
  assert.deepEqual(w, {
    d: "2024-06-07", // dated on the close you decide on
    o: 100,
    h: 150,
    l: 50,
    c: 109,
    v: 15000,
    di: 4, // the daily index of that close
  });
});

test("toWeekly: a holiday week is still one bar", () => {
  // Juneteenth 2024 was a Wednesday: a four-session week.
  const daily = days([
    "2024-06-10", "2024-06-11", "2024-06-12", "2024-06-13", "2024-06-14",
    "2024-06-17", "2024-06-18", "2024-06-20", "2024-06-21",
  ]);
  const weeks = toWeekly(daily);
  assert.equal(weeks.length, 2);
  assert.equal(weeks[1].o, daily[5].o);
  assert.equal(weeks[1].c, daily[8].c);
  assert.equal(weeks[1].di, 8);
});

test("toWeekly: a week across New Year is one bar", () => {
  const daily = days(["2020-12-28", "2020-12-29", "2020-12-30", "2020-12-31", "2021-01-04"]);
  const weeks = toWeekly(daily, "2021-01-11"); // built after that week ended
  assert.equal(weeks.length, 2);
  assert.equal(weeks[0].d, "2020-12-31");
  assert.equal(weeks[0].c, daily[3].c);
});

test("toWeekly: an unfinished final week is dropped", () => {
  const daily = days(["2024-06-03", "2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07", "2024-06-10", "2024-06-11"]);
  const weeks = toWeekly(daily);
  assert.equal(weeks.length, 1, "Mon-Tue of a week in progress is not a weekly bar");
  assert.equal(weeks[0].d, "2024-06-07");
  // ...unless the caller knows the data runs past it (e.g. a Good Friday).
  const goodFriday = days(["2024-03-25", "2024-03-26", "2024-03-27", "2024-03-28"]);
  assert.equal(toWeekly(goodFriday).length, 0);
  assert.equal(toWeekly(goodFriday, "2024-04-01").length, 1);
});

test("toWeekly: no look-ahead — a week's bar only reads its own days", () => {
  const dates = [];
  const d = new Date("2024-01-01T00:00:00Z");
  while (dates.length < 60) {
    if (d.getUTCDay() > 0 && d.getUTCDay() < 6) dates.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  const daily = days(dates);
  const full = toWeekly(daily);
  // Every completed week built from a truncated history is identical.
  for (let k = 0; k < full.length; k++) {
    const cut = toWeekly(daily.slice(0, full[k].di + 1));
    assert.deepEqual(cut[k], full[k], `week ${k} changed when the future was removed`);
  }
});

/* ---------- profiles ---------- */

test("profiles: weekly is the Sunday routine, daily is unchanged", () => {
  assert.equal(timeframe("w"), WEEKLY);
  assert.equal(timeframe("d"), DAILY);
  assert.equal(timeframe("nonsense"), DAILY);

  assert.equal(DAILY.exitFill, "close");
  assert.equal(WEEKLY.exitFill, "nextOpen");
  // Weinstein's pair and nothing else.
  assert.deepEqual(
    WEEKLY.lines.map((l) => [l.kind, l.period]),
    [["sma", 30], ["sma", 10]]
  );
  assert.deepEqual(
    DAILY.lines.map((l) => [l.kind, l.period]),
    [["sma", 200], ["ema", 22], ["ema", 9]]
  );
  // Warm-up covers the longest average plus the visible window.
  assert.equal(warmupBars(DAILY), 235);
  assert.equal(warmupBars(WEEKLY), 65);
  assert.equal(runwayBars(DAILY), 62);
  assert.equal(runwayBars(WEEKLY), 28);
});

/* ---------- default stop ---------- */

test("defaultStop: daily sits 1.5 ATR under the close", () => {
  const bars = [{ o: 100, h: 102, l: 98, c: 100 }];
  assert.equal(defaultStop(DAILY, bars, [2], 0), 97);
});

test("defaultStop: weekly sits a tick under the decision week's low", () => {
  const bars = [{ o: 100, h: 106, l: 94, c: 104 }];
  assert.equal(defaultStop(WEEKLY, bars, [4], 0), 94 - 0.01);
});

test("defaultStop: a week that closed on its low falls back to half an ATR", () => {
  // Low 99.5 under a 100 close is a stop an ordinary Monday takes out.
  const bars = [{ o: 105, h: 106, l: 99.5, c: 100 }];
  assert.equal(defaultStop(WEEKLY, bars, [4], 0), 98);
});

test("defaultStop: no ATR yet stands in 2% of the close", () => {
  const bars = [{ o: 100, h: 101, l: 99.9, c: 100 }];
  // Half of the 2% stand-in: one point under.
  assert.equal(defaultStop(WEEKLY, bars, [null], 0), 99);
});

/* ---------- price precision ---------- */

test("priceDecimals: cents from a dollar up, four significant figures below", () => {
  assert.equal(priceDecimals(150), 2);
  assert.equal(priceDecimals(1), 2);
  assert.equal(priceDecimals(0.5), 4); // 0.5000
  assert.equal(priceDecimals(0.0442), 5); // 0.04420 — KO in 1962, adjusted
  assert.equal(priceDecimals(0), 2);
  assert.equal(priceDecimals(NaN), 2);
});
