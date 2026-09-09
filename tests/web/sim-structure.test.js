// Unit tests for the simulator's price-structure primitives
// (web/v2/js/sim-structure.js).
//
// Stage 1 of the chart-pattern pipeline decides everything downstream: a
// triangle is three pivots and two lines, so a pivot engine that is off by one
// bar produces a catalogue that cannot be debugged. These tests are written
// against hand-built series with known extrema, so a failure names the clause.

import assert from "node:assert/strict";
import test from "node:test";

import {
  PIVOT_K,
  SR_MIN_TOUCHES,
  TOUCH_ATR,
  countTouches,
  fitLine,
  levels,
  lineAt,
  pivotsOf,
  zigzag,
} from "../../web/v2/js/sim-structure.js";
import { flatAtr, series } from "./_sim-bars.js";

const close = (actual, expected, eps = 1e-9) =>
  assert.ok(
    Math.abs(actual - expected) < eps,
    `expected ${expected}, got ${actual} (delta ${Math.abs(actual - expected)})`
  );

const confirmed = (pivots) => pivots.filter((p) => !p.provisional);
const at = (pivots, i) => pivots.filter((p) => p.i === i);

/* ---------- pivots ---------- */

// Up 5, down 5, up 5, down 5 over 20 bars: swing highs at 4 and 14, swing
// lows at 0, 9 and 19 — the two at the ends being unconfirmable by design.
const ZIG = series(100).up(5, 2).down(5, 2).up(5, 2).down(5, 2).build();

test("pivotsOf: finds the local extrema of a hand-built zigzag", () => {
  const p = confirmed(pivotsOf(ZIG, 0, ZIG.length - 1, 2));
  const highs = p.filter((x) => x.type === "high").map((x) => x.i);
  const lows = p.filter((x) => x.type === "low").map((x) => x.i);
  assert.deepEqual(highs, [4, 14]);
  assert.deepEqual(lows, [9]);
  // Index 0 is the series low and 19 its last low, but both sit inside `k` of
  // an end, so neither can be confirmed — that is the point of §4.3, not an
  // oversight.
  assert.deepEqual(at(p, 0), []);
  assert.deepEqual(confirmed(pivotsOf(ZIG, 0, ZIG.length - 1, 2)).filter((x) => x.i === 19), []);
});

test("pivotsOf: pivots carry the bar's own high or low", () => {
  const p = confirmed(pivotsOf(ZIG, 0, ZIG.length - 1, 2));
  const top = p.find((x) => x.i === 4 && x.type === "high");
  close(top.price, ZIG[4].h, 1e-9);
});

test("pivotsOf: a tie makes neither bar a pivot", () => {
  // Two bars share the highest high, three bars either side of them.
  const s = series(100);
  for (const h of [101, 102, 105, 103, 105, 102, 101]) {
    s.bar({ o: h - 1, h, l: h - 2, c: h - 1 });
  }
  const bars = s.build();
  const p = confirmed(pivotsOf(bars, 0, bars.length - 1, 2));
  assert.deepEqual(
    p.filter((x) => x.type === "high"),
    [],
    "a shared high is not a strict local extreme"
  );
});

test("pivotsOf: nothing within k of either end is confirmed", () => {
  const p = confirmed(pivotsOf(ZIG, 3, 17, 2));
  assert.ok(p.length > 0);
  assert.ok(p.every((x) => x.i >= 5 && x.i <= 15));
});

test("pivotsOf: emits exactly one provisional high and one provisional low", () => {
  const p = pivotsOf(ZIG, 0, ZIG.length - 1, 2);
  const prov = p.filter((x) => x.provisional);
  assert.equal(prov.length, 2);
  assert.equal(prov.filter((x) => x.type === "high").length, 1);
  assert.equal(prov.filter((x) => x.type === "low").length, 1);
  // Both are drawn from the last k bars, which is where confirmation cannot
  // reach.
  assert.ok(prov.every((x) => x.i > ZIG.length - 1 - PIVOT_K));
  // The series falls into its right edge, so the provisional low is the last
  // bar and the provisional high the first of the two.
  assert.equal(prov.find((x) => x.type === "low").i, ZIG.length - 1);
});

test("pivotsOf: degenerate input returns an empty list, never a throw", () => {
  assert.deepEqual(pivotsOf([], 0, 0, 2), []);
  assert.deepEqual(pivotsOf(ZIG, 0, 0, 0), []);
  assert.equal(pivotsOf(ZIG, 10, 3, 2).length, 0);
});

/* ---------- zigzag ---------- */

const ATR1 = flatAtr(ZIG, 1);

test("zigzag: the output strictly alternates", () => {
  const z = zigzag(pivotsOf(ZIG, 0, ZIG.length - 1, 2), ZIG, ATR1, 0.75);
  assert.ok(z.length >= 3);
  for (let i = 1; i < z.length; i++) assert.notEqual(z[i].type, z[i - 1].type);
});

test("zigzag: a run of same-type pivots keeps the most extreme", () => {
  const pivots = [
    { i: 2, type: "high", price: 110, provisional: false },
    { i: 5, type: "high", price: 114, provisional: false },
    { i: 8, type: "high", price: 112, provisional: false },
    { i: 12, type: "low", price: 100, provisional: false },
  ];
  const z = zigzag(pivots, ZIG, ATR1, 0.75);
  assert.deepEqual(
    z.map((p) => p.i),
    [5, 12]
  );
  assert.equal(z[0].price, 114);
});

test("zigzag: a swing smaller than MIN_SWING_ATR is dropped", () => {
  const pivots = [
    { i: 2, type: "high", price: 110, provisional: false },
    { i: 5, type: "low", price: 109.5, provisional: false }, // 0.5 ATR — too small
    { i: 9, type: "low", price: 105, provisional: false },
  ];
  const z = zigzag(pivots, ZIG, ATR1, 0.75);
  assert.deepEqual(
    z.map((p) => p.i),
    [2, 9],
    "the shallow low is skipped and the deeper one taken in its place"
  );
});

test("zigzag: a null ATR drops the swing rather than throwing", () => {
  const atrArr = ATR1.slice();
  atrArr[5] = null;
  const pivots = [
    { i: 2, type: "high", price: 110, provisional: false },
    { i: 5, type: "low", price: 100, provisional: false },
  ];
  assert.deepEqual(
    zigzag(pivots, ZIG, atrArr, 0.75).map((p) => p.i),
    [2]
  );
});

/* ---------- lines ---------- */

test("fitLine: two points give the exact line through them", () => {
  const l = fitLine([
    { i: 10, price: 100 },
    { i: 20, price: 110 },
  ]);
  close(l.m, 1);
  close(l.b, 90);
  close(lineAt(l, 15), 105);
});

test("fitLine: collinear points are exact and the slope sign is right", () => {
  const pts = [12, 15, 19, 24].map((i) => ({ i, price: 200 - 0.5 * i }));
  const l = fitLine(pts);
  close(l.m, -0.5, 1e-9);
  close(lineAt(l, 30), 185, 1e-9);
});

test("fitLine: one point is horizontal, no points is null", () => {
  assert.deepEqual(fitLine([{ i: 4, price: 7 }]), { m: 0, b: 7 });
  assert.equal(fitLine([]), null);
});

test("fitLine: least squares splits the difference on a scattered fit", () => {
  const l = fitLine([
    { i: 0, price: 100 },
    { i: 10, price: 100 },
    { i: 20, price: 106 },
  ]);
  close(l.m, 0.3, 1e-9);
});

/* ---------- touches ---------- */

test("countTouches: a pivot exactly TOUCH_ATR away counts, further does not", () => {
  const l = { m: 0, b: 100 };
  const atrArr = flatAtr(ZIG, 2);
  const exact = { i: 5, type: "high", price: 100 + TOUCH_ATR * 2, provisional: false };
  const just = { i: 6, type: "high", price: 100 + TOUCH_ATR * 2 + 1e-6, provisional: false };
  assert.equal(countTouches(l, [exact], atrArr), 1);
  assert.equal(countTouches(l, [just], atrArr), 0);
});

test("countTouches: provisional pivots never count", () => {
  const l = { m: 0, b: 100 };
  const p = { i: 5, type: "high", price: 100, provisional: true };
  assert.equal(countTouches(l, [p], ATR1), 0);
});

/* ---------- levels ---------- */

// A flat series, so the anchor's close sits among whatever pivots a test hands
// in and the clustering is exercised on prices the test chose rather than on
// the builder's own wiggle.
function levelBars() {
  const s = series(100);
  s.flat(60, 1);
  return s.build();
}

const LEVEL_BARS = levelBars();
const LEVEL_ATR = flatAtr(LEVEL_BARS, 2);
const anchor = LEVEL_BARS.length - 1;
const near = LEVEL_BARS[anchor].c;

const pv = (i, price, type = "high") => ({ i, type, price, provisional: false });

test("levels: pivots inside tolerance cluster into one level", () => {
  const prices = [0.2, 0.4, 0.1, 0.3];
  const out = levels(
    prices.map((d, k) => pv(10 + k * 10, near + d)),
    LEVEL_BARS,
    LEVEL_ATR,
    { anchor }
  );
  assert.equal(out.length, 1);
  assert.equal(out[0].touches, SR_MIN_TOUCHES);
  close(out[0].price, near + prices.reduce((a, b) => a + b) / prices.length, 1e-9);
  assert.equal(out[0].firstIdx, 10);
  assert.equal(out[0].lastIdx, 40);
});

test("levels: one touch short does not qualify", () => {
  const out = levels(
    Array.from({ length: SR_MIN_TOUCHES - 1 }, (_, k) => pv(10 + k * 10, near + k * 0.1)),
    LEVEL_BARS,
    LEVEL_ATR,
    { anchor }
  );
  assert.deepEqual(out, []);
});

test("levels: a cluster far from the close is dropped", () => {
  const far = near + 40; // way beyond SR_NEAR_ATR * atr
  const out = levels(
    [10, 20, 30, 40].map((i) => pv(i, far)),
    LEVEL_BARS,
    LEVEL_ATR,
    { anchor }
  );
  assert.deepEqual(out, []);
});

test("levels: recent touches break the tie between equal clusters", () => {
  const out = levels(
    [
      // Four old touches just above the close…
      pv(2, near + 0.9),
      pv(6, near + 0.9),
      pv(9, near + 0.9),
      pv(13, near + 0.9),
      // …against four that include three inside SR_RECENT_BARS.
      pv(20, near - 0.9),
      pv(anchor - 8, near - 0.9),
      pv(anchor - 5, near - 0.9),
      pv(anchor - 2, near - 0.9),
    ],
    LEVEL_BARS,
    LEVEL_ATR,
    { anchor }
  );
  assert.equal(out.length, 2);
  assert.ok(out[0].price < near, "the level with recent touches sorts first");
  assert.equal(out[0].recent, 3);
});

test("levels: provisional pivots are excluded from the clusters", () => {
  const confirmedOnly = Array.from({ length: SR_MIN_TOUCHES - 1 }, (_, k) => pv(10 + k * 10, near));
  const out = levels(
    [...confirmedOnly, { ...pv(40, near), provisional: true }],
    LEVEL_BARS,
    LEVEL_ATR,
    { anchor }
  );
  assert.deepEqual(out, [], "the provisional pivot must not make up the numbers");
});

test("levels: a null ATR at the anchor returns nothing rather than throwing", () => {
  const atrArr = LEVEL_ATR.slice();
  atrArr[anchor] = null;
  assert.deepEqual(levels([pv(10, near)], LEVEL_BARS, atrArr, { anchor }), []);
});
