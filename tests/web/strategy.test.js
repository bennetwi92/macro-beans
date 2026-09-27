// Unit tests for the weekly strategy's rules (web/v2/js/strategy.js).
//
// The load-bearing ones:
//   * "no look-ahead" — everything read at week w (stage, setups, plan, the
//     like-week analogues) must be identical whether or not the future exists.
//     A strategy whose evidence quietly peeks is worse than one with none,
//     because nothing on screen would say so.
//   * the fill model — a resting stop fills at the open of the DAY that gaps
//     through it, which is where a 1R risk becomes a 3R loss.
//   * one position per name — overlapping trades would inflate every sample
//     the scorecard shows.

import assert from "node:assert/strict";
import test from "node:test";

import {
  RULES,
  prepareSeries,
  stageAt,
  setupsAt,
  planAt,
  runTrade,
  eventTable,
  analogueStats,
  universePriors,
  trailStop,
  weekAsOf,
  tickFor,
} from "../../web/v2/js/strategy.js";
import { barsFromCloses, walk, ramp } from "./_weekly-bars.js";

const lastDate = (daily) => daily[daily.length - 1].d;

/* ---------- stage ---------- */

test("stage: a steady advance is Stage 2, a steady decline Stage 4", () => {
  const up = prepareSeries(barsFromCloses(ramp(400, 50, 0.002)));
  const dn = prepareSeries(barsFromCloses(ramp(400, 200, -0.002)));
  const w = up.bars.length - 1;
  assert.equal(up.stage[w], 2);
  assert.equal(dn.stage[dn.bars.length - 1], 4);
  assert.ok(up.age[w] > 20, "a long advance has aged");
});

test("stage: a flat line after a decline is a base (1), after an advance a top (3)", () => {
  const afterDecline = prepareSeries(barsFromCloses([...ramp(300, 200, -0.002), ...new Array(250).fill(200 * Math.pow(0.998, 299))]));
  const afterAdvance = prepareSeries(barsFromCloses([...ramp(300, 50, 0.002), ...new Array(250).fill(50 * Math.pow(1.002, 299))]));
  assert.equal(afterDecline.stage[afterDecline.bars.length - 1], 1);
  assert.equal(afterAdvance.stage[afterAdvance.bars.length - 1], 3);
});

test("stage: null until the 30-week and its slope exist", () => {
  const s = prepareSeries(barsFromCloses(ramp(200, 50, 0.001)));
  assert.equal(stageAt(s, 10), null);
});

/* ---------- no look-ahead ---------- */

test("no look-ahead: stage, setups, plan and analogues at week w ignore everything after it", () => {
  const daily = barsFromCloses(walk(2600, { seed: 5 }));
  const full = prepareSeries(daily);
  const fullEvents = eventTable(full);
  let checked = 0;
  for (let w = 120; w < full.bars.length - 30; w += 7) {
    const cutDaily = daily.slice(0, full.bars[w].di + 1);
    const cut = prepareSeries(cutDaily, lastDate(cutDaily));
    assert.equal(cut.bars.length, w + 1, "the cut series ends on week w");
    assert.equal(cut.stage[w], full.stage[w]);
    assert.deepEqual(setupsAt(cut, w), setupsAt(full, w));
    assert.deepEqual(planAt(cut, w), planAt(full, w));
    for (const setup of ["PULLBACK", "BREAKOUT", "REVERSAL"]) {
      const a = analogueStats(full, fullEvents, w, setup, { meanR: 0.3 });
      const b = analogueStats(cut, eventTable(cut), w, setup, { meanR: 0.3 });
      assert.deepEqual(a, b, `analogues for ${setup} at week ${w}`);
    }
    checked++;
  }
  assert.ok(checked > 50);
});

test("no look-ahead: the analogues count only trades that had EXITED by week w", () => {
  const s = prepareSeries(barsFromCloses(walk(2600, { seed: 9 })));
  const events = eventTable(s);
  const e = events.find((x) => !x.trade.open && x.trade.exitIdx - x.w > 3);
  assert.ok(e, "fixture has a multi-week trade");
  const setup = e.setup;
  const during = analogueStats(s, events, e.trade.exitIdx - 1, setup);
  const after = analogueStats(s, events, e.trade.exitIdx, setup);
  assert.equal(after.n - during.n, 1, "the trade counts from its exit week, not before");
});

/* ---------- the fill model ---------- */

test("runTrade: enters at Monday's open with the stop under the decision week's low", () => {
  const s = prepareSeries(barsFromCloses(ramp(400, 50, 0.002)));
  const w = 60;
  const t = runTrade(s, w);
  assert.equal(t.entryIdx, w + 1);
  assert.equal(t.entryPrice, s.bars[w + 1].o);
  assert.ok(t.initialStop < s.bars[w].l, "under the decision week's low");
});

test("runTrade: a mid-week gap through the stop fills at THAT DAY's open, not at the stop", () => {
  const closes = ramp(400, 50, 0.002);
  const daily = barsFromCloses(closes);
  const s0 = prepareSeries(daily);
  const w = 60;
  const stop = runTrade(s0, w).initialStop;
  // Wednesday of the entry week gaps 15% below the stop.
  const entryWeek = s0.bars[w + 1];
  const wed = entryWeek.di - 2;
  const gapOpen = stop * 0.85;
  const gapped = daily.map((b, i) => (i === wed ? { ...b, o: gapOpen, h: gapOpen * 1.01, l: gapOpen * 0.99, c: gapOpen } : b));
  const s = prepareSeries(gapped);
  const t = runTrade(s, w);
  assert.equal(t.reason, "stop");
  assert.equal(t.exitPrice, gapOpen);
  assert.ok(t.r < -1.5, `a gap loss is worse than 1R (got ${t.r.toFixed(2)})`);
});

test("runTrade: no fill when Monday opens at or below the stop", () => {
  const daily = barsFromCloses(ramp(400, 50, 0.002));
  const s0 = prepareSeries(daily);
  const w = 60;
  const stop = runTrade(s0, w).initialStop;
  const mon = s0.bars[w].di + 1;
  const gapped = daily.map((b, i) => (i === mon ? { ...b, o: stop * 0.95, l: stop * 0.94 } : b));
  assert.equal(runTrade(prepareSeries(gapped), w), null);
});

test("runTrade: the trail takes the stop to break-even at +1R and never lowers it", () => {
  const s = prepareSeries(barsFromCloses(ramp(600, 50, 0.003)));
  const t = runTrade(s, 60, { trace: true });
  const stops = t.stops.map(([, v]) => v);
  for (let i = 1; i < stops.length; i++) assert.ok(stops[i] >= stops[i - 1] - 1e-9, "ratchets one way");
  assert.ok(stops[stops.length - 1] > t.entryPrice, "a strong advance trails above entry");
  assert.equal(trailStop(s, 60, s.closes[60] * 2, s.closes[60]), null, "no trail before +1R");
});

test("runTrade: a steady advance with nothing to stop it is a TIME exit at maxHold", () => {
  const s = prepareSeries(barsFromCloses(ramp(800, 50, 0.0015), { range: 0.002 }));
  const t = runTrade(s, 80);
  assert.equal(t.reason, "time");
  assert.equal(t.exitIdx, 80 + 1 + RULES.maxHold, "decided on the last week, filled the Monday after");
  assert.equal(t.exitPrice, s.bars[t.exitIdx].o);
});

test("runTrade: a weekly close below the 30-week is a THESIS exit at the next open", () => {
  // A long advance, then a slide that is slow enough to stay above the trail
  // for a while but ends under the 30-week.
  const closes = [...ramp(400, 50, 0.002), ...ramp(150, 50 * Math.pow(1.002, 399), -0.0025)];
  const daily = barsFromCloses(closes, { range: 0.001 });
  const s = prepareSeries(daily);
  // Enter late in the advance so the trail has not yet lifted far.
  const w = 78;
  const t = runTrade(s, w, { initialStop: s.closes[w] * 0.5 });
  assert.equal(t.reason, "thesis");
  const decided = t.exitIdx - 1;
  assert.ok(s.closes[decided] < s.sma30[decided], "decided on a close under the line");
  assert.equal(t.exitPrice, s.bars[t.exitIdx].o);
});

test("runTrade: a trade still running on the last bar is open, not an outcome", () => {
  const s = prepareSeries(barsFromCloses(ramp(500, 50, 0.002)));
  const t = runTrade(s, s.bars.length - 5);
  assert.equal(t.open, true);
  assert.equal(t.exitIdx, null);
});

/* ---------- the event table ---------- */

test("eventTable: one position per name — no trade opens before the last one exits", () => {
  const s = prepareSeries(barsFromCloses(walk(3000, { seed: 21 })));
  const ev = eventTable(s);
  assert.ok(ev.length >= 5, `fixture trades (${ev.length})`);
  for (let i = 1; i < ev.length; i++) {
    assert.ok(!ev[i - 1].trade.open);
    assert.ok(ev[i].w > ev[i - 1].trade.exitIdx, "the next decision comes after the last exit");
  }
});

test("universePriors: only trades exited on or before the date count", () => {
  const s = prepareSeries(barsFromCloses(walk(3000, { seed: 21 })));
  const events = eventTable(s);
  const closed = events.filter((e) => !e.trade.open);
  const mid = s.bars[closed[Math.floor(closed.length / 2)].trade.exitIdx].d;
  const p = universePriors([{ s, events }], mid);
  const n = Object.values(p).reduce((a, x) => a + x.n, 0);
  const expect = closed.filter((e) => s.bars[e.trade.exitIdx].d <= mid).length;
  assert.equal(n, expect);
});

/* ---------- setups ---------- */

test("setups: a steady grind is not a breakout — the cleared high must be a base", () => {
  const s = prepareSeries(barsFromCloses(ramp(600, 50, 0.002)));
  for (let w = 60; w < s.bars.length; w++) {
    assert.ok(!setupsAt(s, w).some((x) => x.setup === "BREAKOUT"), `week ${w}`);
  }
});

test("setups: a base that resolves upward is a BREAKOUT", () => {
  // Advance, a 20-week sideways base, then a strong week through its high.
  const closes = [...ramp(300, 50, 0.002)];
  const top = closes[closes.length - 1];
  for (let i = 0; i < 100; i++) closes.push(top * (0.95 + 0.03 * Math.sin(i / 6)));
  for (let i = 0; i < 5; i++) closes.push(top * (1.0 + 0.005 * (i + 1)));
  const s = prepareSeries(barsFromCloses(closes));
  const w = s.bars.length - 1;
  const b = setupsAt(s, w).find((x) => x.setup === "BREAKOUT");
  assert.ok(b, "breakout found");
  assert.equal(b.status, "BUY");
});

test("setups: a breakout that has already run is not chased", () => {
  const closes = [...ramp(300, 50, 0.002)];
  const top = closes[closes.length - 1];
  for (let i = 0; i < 100; i++) closes.push(top * (0.95 + 0.03 * Math.sin(i / 6)));
  for (let i = 0; i < 5; i++) closes.push(top * (1.0 + 0.015 * (i + 1)));
  const s = prepareSeries(barsFromCloses(closes));
  const b = setupsAt(s, s.bars.length - 1).find((x) => x.setup === "BREAKOUT");
  assert.equal(b, undefined, "more than maxExtAtr above the level");
});

test("planAt: reward:risk measures room to resistance per unit of stop distance", () => {
  const s = prepareSeries(barsFromCloses(walk(2000, { seed: 3 })));
  const w = 300;
  const p = planAt(s, w);
  assert.ok(p.stop < p.entry);
  const room = p.blueSky ? 6 * p.atr : Math.min(p.target - p.entry, 6 * p.atr);
  assert.ok(Math.abs(p.rr - room / (p.entry - p.stop)) < 1e-9);
});

test("weekAsOf and tickFor", () => {
  const s = prepareSeries(barsFromCloses(ramp(100, 50, 0.001)));
  assert.equal(weekAsOf(s, s.bars[5].d), 5);
  assert.equal(weekAsOf(s, "1990-01-01"), -1);
  assert.equal(tickFor(12.5), 0.01);
  assert.ok(tickFor(0.05) < 0.01);
});
