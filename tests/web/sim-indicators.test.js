// Unit tests for the simulator's indicator math (web/v2/js/sim-indicators.js).
//
// The chart is the whole product here: if the 9EMA or the RSI is subtly wrong,
// every rep trains the wrong instinct and nothing on screen says so. So the
// expected values below come from an independent Python implementation of the
// textbook definitions (SMA-seeded EMA, Wilder RSI, MACD 12/26/9) over a fixed
// deterministic series, and the rest are properties that must hold for any
// correct implementation.

import assert from "node:assert/strict";
import test from "node:test";

import { atr, ema, macd, rsi, sma } from "../../web/v2/js/sim-indicators.js";

// 100 + 10*sin(i/5) + 0.1*i — trends up, oscillates, never repeats.
const SERIES = Array.from({ length: 120 }, (_, i) =>
  Number((100 + 10 * Math.sin(i / 5) + 0.1 * i).toFixed(4))
);

const close = (actual, expected, eps = 1e-6) =>
  assert.ok(
    Math.abs(actual - expected) < eps,
    `expected ${expected}, got ${actual} (delta ${Math.abs(actual - expected)})`
  );

test("sma: leading nulls, then the rolling mean", () => {
  const out = sma(SERIES, 20);
  assert.equal(out.length, SERIES.length);
  assert.equal(out[18], null);
  close(out[19], 105.259525);
  close(out[119], 111.364525);
  // A flat series averages to itself.
  assert.deepEqual(sma([5, 5, 5, 5], 2), [null, 5, 5, 5]);
});

test("ema: seeded with the SMA of the first `period` values", () => {
  const out = ema(SERIES, 9);
  assert.equal(out[7], null);
  close(out[8], 106.654022); // the seed = SMA(first 9)
  close(out[119], 104.619368);
  close(ema(SERIES, 22)[119], 107.982984);
});

test("ema: a constant series stays constant", () => {
  const flat = new Array(30).fill(42);
  const out = ema(flat, 9);
  assert.equal(out[8], 42);
  assert.equal(out[29], 42);
});

test("ema: skips leading nulls (so it can smooth the MACD line)", () => {
  const withGap = [null, null, null, 1, 2, 3, 4, 5];
  const out = ema(withGap, 3);
  assert.equal(out[4], null); // only two defined values so far
  close(out[5], 2); // seed = mean(1,2,3)
  close(out[6], 3); // 4*0.5 + 2*0.5
});

test("macd: 12/26/9, hist = line - signal", () => {
  const { line, signal, hist } = macd(SERIES);
  assert.equal(line[24], null);
  assert.notEqual(line[25], null);
  // Signal needs 9 defined MACD values, so the histogram starts at 25 + 8.
  assert.equal(hist[32], null);
  assert.notEqual(hist[33], null);
  close(line[119], -2.482659);
  close(signal[119], -0.967691);
  close(hist[119], -1.514968);
  for (let i = 33; i < SERIES.length; i++) close(hist[i], line[i] - signal[i]);
});

test("rsi: Wilder smoothing, 14 by default", () => {
  const out = rsi(SERIES, 14);
  assert.equal(out[13], null);
  close(out[14], 64.101772);
  close(out[60], 48.329217);
  close(out[119], 28.631362);
});

test("rsi: pinned at the extremes, bounded in between", () => {
  const up = Array.from({ length: 40 }, (_, i) => 100 + i);
  const down = Array.from({ length: 40 }, (_, i) => 100 - i);
  assert.equal(rsi(up, 14)[39], 100);
  assert.equal(rsi(down, 14)[39], 0);
  for (const v of rsi(SERIES, 14)) {
    if (v != null) assert.ok(v >= 0 && v <= 100, `RSI out of range: ${v}`);
  }
});

test("rsi: too short a series yields no values at all", () => {
  assert.deepEqual(
    rsi([1, 2, 3], 14),
    [null, null, null]
  );
});

test("atr: Wilder's true range average", () => {
  // Every bar has a 2-wide range and no gaps, so the ATR is exactly 2.
  const bars = Array.from({ length: 30 }, (_, i) => ({
    h: 101 + i * 0.0,
    l: 99,
    c: 100,
  }));
  const out = atr(bars, 14);
  assert.equal(out[13], null);
  close(out[14], 2);
  close(out[29], 2);
});

test("atr: a gap counts against the previous close, not the bar's own range", () => {
  const bars = [];
  for (let i = 0; i < 16; i++) bars.push({ h: 101, l: 99, c: 100 });
  bars.push({ h: 111, l: 110, c: 110 }); // gaps 10 above the prior close
  const out = atr(bars, 14);
  // TR of the gap bar is 11 (110-99... no: high 111 vs prior close 100), and
  // Wilder folds it in at 1/14 weight: 2*(13/14) + 11/14.
  close(out[16], (out[15] * 13 + 11) / 14);
});
