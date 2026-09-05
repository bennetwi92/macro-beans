// Unit tests for the simulator's trade accounting (web/v2/js/sim-engine.js).
//
// These encode the rules the simulator trains against — next-open entry, close
// fills for discretionary exits, an intraday stop that fills at the open when
// the bar gaps through it, a stop that trails one way only, and results quoted
// in percent and in R.

import assert from "node:assert/strict";
import test from "node:test";

import {
  LONG,
  SHORT,
  exitTrade,
  isOpen,
  moveStop,
  openTrade,
  stepTrade,
  stopAllows,
  stopFill,
  stopMoveAllows,
  stopOutStats,
  tradeStats,
} from "../../web/v2/js/sim-engine.js";

const bar = (o, h, l, c) => ({ o, h, l, c });
const close = (actual, expected, eps = 1e-9) =>
  assert.ok(Math.abs(actual - expected) < eps, `expected ${expected}, got ${actual}`);

test("a fresh trade is fully open with no fills", () => {
  const t = openTrade({ side: LONG, stop: 95, entryIndex: 10, entryPrice: 100 });
  assert.equal(t.open, 1);
  assert.deepEqual(t.exits, []);
  assert.ok(isOpen(t));
});

test("stopFill: untouched stops do not fill", () => {
  const long = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  assert.equal(stopFill(long, bar(100, 103, 96, 102)), null);
  const short = openTrade({ side: SHORT, stop: 105, entryIndex: 0, entryPrice: 100 });
  assert.equal(stopFill(short, bar(100, 104, 97, 98)), null);
});

test("stopFill: a touched stop fills at the stop", () => {
  const long = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  assert.equal(stopFill(long, bar(99, 100, 94, 97)), 95);
  const short = openTrade({ side: SHORT, stop: 105, entryIndex: 0, entryPrice: 100 });
  assert.equal(stopFill(short, bar(101, 106, 100, 103)), 105);
});

test("stopFill: a gap through the stop fills at the open, not the stop", () => {
  const long = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  assert.equal(stopFill(long, bar(90, 92, 88, 91)), 90);
  const short = openTrade({ side: SHORT, stop: 105, entryIndex: 0, entryPrice: 100 });
  assert.equal(stopFill(short, bar(112, 114, 110, 113)), 112);
});

test("stepTrade: closes the position and flags the stop", () => {
  const t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  const quiet = stepTrade(t, bar(100, 102, 97, 101), 1);
  assert.equal(quiet.stopped, false);
  assert.equal(quiet.trade.open, 1);

  const hit = stepTrade(t, bar(99, 99, 90, 92), 2);
  assert.equal(hit.stopped, true);
  assert.equal(hit.trade.open, 0);
  assert.equal(hit.trade.stopped, true);
  assert.equal(hit.trade.exits[0].price, 95);
  assert.equal(hit.trade.exits[0].reason, "stop");
});

test("half exits: two 50% exits close the trade exactly", () => {
  let t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  t = exitTrade(t, { index: 3, price: 105, fraction: 0.5 });
  close(t.open, 0.5);
  assert.ok(isOpen(t));
  t = exitTrade(t, { index: 6, price: 110, fraction: 0.5 });
  close(t.open, 0);
  assert.equal(isOpen(t), false);
  assert.equal(t.exits.length, 2);
});

test("an oversized exit is clamped to what is still open", () => {
  let t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  t = exitTrade(t, { index: 3, price: 105, fraction: 0.5 });
  t = exitTrade(t, { index: 4, price: 106, fraction: 1 }); // asks for more than is left
  close(t.open, 0);
  close(t.exits[1].fraction, 0.5);
});

test("tradeStats: scaled out long, half realized and half marked", () => {
  let t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  t = exitTrade(t, { index: 3, price: 106, fraction: 0.5 });
  const st = tradeStats(t, 104);
  close(st.realized, 3); // half of +6%
  close(st.unrealized, 2); // half of +4%
  close(st.total, 5);
  close(st.risk, 5); // 100 -> 95
  close(st.r, 1);
});

test("tradeStats: a short makes money when price falls", () => {
  let t = openTrade({ side: SHORT, stop: 105, entryIndex: 0, entryPrice: 100 });
  t = exitTrade(t, { index: 4, price: 90, fraction: 1 });
  const st = tradeStats(t, 90);
  close(st.total, 10);
  close(st.risk, 5);
  close(st.r, 2);
});

test("tradeStats: a stop-out with no slippage is exactly -1R", () => {
  const t = openTrade({ side: LONG, stop: 96, entryIndex: 0, entryPrice: 100 });
  const { trade } = stepTrade(t, bar(99, 99, 95, 95.5), 1);
  const st = tradeStats(trade, 95.5);
  close(st.total, -4);
  close(st.r, -1);
});

test("tradeStats: a gap through the stop costs more than 1R", () => {
  const t = openTrade({ side: LONG, stop: 96, entryIndex: 0, entryPrice: 100 });
  const { trade } = stepTrade(t, bar(92, 93, 91, 92.5), 1);
  const st = tradeStats(trade, 92.5);
  close(st.total, -8);
  close(st.r, -2);
});

test("stopAllows: the stop has to sit on the losing side of the price", () => {
  assert.equal(stopAllows(LONG, 95, 100), true);
  assert.equal(stopAllows(LONG, 105, 100), false);
  assert.equal(stopAllows(SHORT, 105, 100), true);
  assert.equal(stopAllows(SHORT, 95, 100), false);
  // A stop exactly at the price is no stop at all.
  assert.equal(stopAllows(LONG, 100, 100), false);
  assert.equal(stopAllows(SHORT, 100, 100), false);
});

/* ---------- trailing the stop while the trade runs ---------- */

test("moveStop: a long's stop only travels up", () => {
  const t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  assert.equal(moveStop(t, 98, 106).stop, 98); // tighter — allowed
  assert.equal(moveStop(t, 92, 106).stop, 95); // wider — refused, unchanged
  assert.equal(moveStop(t, 95, 106).stop, 95); // no move at all
});

test("moveStop: a short's stop only travels down", () => {
  const t = openTrade({ side: SHORT, stop: 105, entryIndex: 0, entryPrice: 100 });
  assert.equal(moveStop(t, 101, 94).stop, 101);
  assert.equal(moveStop(t, 108, 94).stop, 105);
});

test("moveStop: the stop may not be dragged through the price", () => {
  const long = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  assert.equal(moveStop(long, 107, 106).stop, 95); // above the close is no stop
  assert.equal(moveStop(long, 106, 106).stop, 95); // exactly at it, likewise
  const short = openTrade({ side: SHORT, stop: 105, entryIndex: 0, entryPrice: 100 });
  assert.equal(moveStop(short, 93, 94).stop, 105);
});

test("moveStop: a closed position has no stop left to move", () => {
  let t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  t = exitTrade(t, { index: 3, price: 106, fraction: 1 });
  assert.equal(stopMoveAllows(t, 98, 106), false);
  assert.equal(moveStop(t, 98, 106).stop, 95);
});

test("moveStop: trailing does not rescale R — risk stays at the original stop", () => {
  let t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  t = moveStop(t, 102, 108); // locked in, well past the entry
  const st = tradeStats(t, 108);
  close(st.risk, 5); // 100 -> 95, not 100 -> 102
  close(st.total, 8);
  close(st.r, 1.6);
});

test("a trailed stop is what actually fills when the bar breaks it", () => {
  let t = openTrade({ side: LONG, stop: 95, entryIndex: 0, entryPrice: 100 });
  t = moveStop(t, 104, 108);
  const { trade, stopped } = stepTrade(t, bar(107, 109, 103, 105), 5);
  assert.equal(stopped, true);
  assert.equal(trade.exits[0].price, 104);
  const st = tradeStats(trade, 105);
  close(st.total, 4);
  close(st.r, 0.8); // +4% on 5% of risk — a win taken by the stop
});

test("stopOutStats: what the stop is worth, before and after breakeven", () => {
  const t = openTrade({ side: LONG, stop: 96, entryIndex: 0, entryPrice: 100 });
  close(stopOutStats(t).r, -1); // untouched: the full 1R still at risk
  close(stopOutStats(moveStop(t, 100, 105)).r, 0); // at the entry: a free trade
  close(stopOutStats(moveStop(t, 102, 105)).r, 0.5); // past it: half an R banked
});

test("stopOutStats: counts what is already realized on a scaled-out trade", () => {
  let t = openTrade({ side: LONG, stop: 96, entryIndex: 0, entryPrice: 100 });
  t = exitTrade(t, { index: 3, price: 108, fraction: 0.5 }); // +4% banked
  t = moveStop(t, 104, 110);
  close(stopOutStats(t).r, 1.5); // +4% realized, +2% if the rest stops out
});
