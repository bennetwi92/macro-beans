/* Unit tests for the seasonality engine (the Best Months pages).

   Locks the month-of-year aggregation that drives the heatmap and the
   "sell in May" split. Run with:  node --test tests/web/ */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  MONTH_NAMES,
  monthlyReturns,
  computeMonths,
  seasonHalves,
} from "../../web/js/seasonality-engine.js";

const bar = (date, close) => [date, close, close]; // [date, open, close]

const approx = (a, b, eps = 1e-9) =>
  assert.ok(Math.abs(a - b) <= eps, `expected ${a} ≈ ${b}`);

/* monthlyReturns collapses daily bars to one return per calendar month,
   using the last close of each month vs the last close of the prior month,
   and drops the first month (no prior to compare against). */
test("monthlyReturns: month-over-month on last close, first month dropped", () => {
  const bars = [
    bar("2020-01-10", 100),
    bar("2020-01-31", 110), // Jan last close = 110
    bar("2020-02-15", 120),
    bar("2020-02-28", 121), // Feb last close = 121
    bar("2020-03-31", 121), // Mar last close = 121
  ];
  const rets = monthlyReturns(bars, { range: "all" });
  // Jan dropped (no prior). Feb = 121/110-1, Mar = 121/121-1 = 0.
  assert.equal(rets.length, 2);
  assert.deepEqual(rets.map(r => [r.y, r.m]), [[2020, 2], [2020, 3]]);
  approx(rets[0].ret, 121 / 110 - 1, 1e-12);
  approx(rets[1].ret, 0, 1e-12);
});

test("monthlyReturns: range '10y' drops months older than the cutoff", () => {
  const bars = [
    bar("2008-06-30", 100),
    bar("2008-07-31", 110), // 2008-07 return — older than 10y, must be dropped
    bar("2020-06-30", 100),
    bar("2020-07-31", 120), // 2020-07 return — within 10y, must be kept
  ];
  const all = monthlyReturns(bars, { range: "all" });
  const recent = monthlyReturns(bars, { range: "10y" });
  // last bar 2020-07 -> cutoff "2010-07"
  assert.ok(all.some(r => r.y === 2008), "all keeps the 2008 month");
  assert.ok(!recent.some(r => r.y === 2008), "10y drops the 2008 month");
  assert.ok(recent.length < all.length);
  assert.ok(recent.every(r => r.y === 2020), "10y keeps only recent months");
});

test("computeMonths: returns 12 buckets with green %, avg, med", () => {
  // two Januaries: +10% and -10%; everything else flat or absent
  const bars = [
    bar("2018-12-31", 100),
    bar("2019-01-31", 110), // Jan 2019 = +10%
    bar("2019-12-31", 100),
    bar("2020-01-31", 90),  // Jan 2020 = -10%
  ];
  const months = computeMonths(bars, { range: "all" });
  assert.equal(months.length, 12);
  const jan = months[0];
  assert.equal(jan.m, 1);
  assert.equal(jan.name, "Jan");
  assert.equal(jan.n, 2);
  approx(jan.green, 50, 1e-9); // one of two positive
  approx(jan.avg, 0, 1e-9);    // +10 and -10 average to 0
  approx(jan.med, 0, 1e-9);
});

test("computeMonths: a month with no data is n=0 with NaN stats", () => {
  const bars = [
    bar("2019-12-31", 100),
    bar("2020-01-31", 110),
  ];
  const months = computeMonths(bars, { range: "all" });
  const jul = months.find(m => m.name === "Jul");
  assert.equal(jul.n, 0);
  assert.ok(Number.isNaN(jul.green));
  assert.ok(Number.isNaN(jul.avg));
});

test("seasonHalves: winter Nov–Apr vs summer May–Oct", () => {
  // build clear month returns: a positive winter month and a negative summer month
  const bars = [
    bar("2019-10-31", 100),
    bar("2019-11-30", 110), // Nov (winter) = +10%
    bar("2020-05-31", 99),  // May (summer): vs Nov last close 110 -> -10%
  ];
  const { winter, summer } = seasonHalves(bars, { range: "all" });
  assert.equal(winter.n, 1);
  approx(winter.avg, 10, 1e-9);
  approx(winter.green, 100, 1e-9);
  assert.equal(summer.n, 1);
  approx(summer.avg, (99 / 110 - 1) * 100, 1e-9);
  approx(summer.green, 0, 1e-9);
});

test("MONTH_NAMES has 12 entries starting at Jan", () => {
  assert.equal(MONTH_NAMES.length, 12);
  assert.equal(MONTH_NAMES[0], "Jan");
  assert.equal(MONTH_NAMES[11], "Dec");
});
