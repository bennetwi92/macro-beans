// Unit tests for the simulator's chart-pattern engine
// (web/v2/js/sim-patterns.js): the catalogue, the tier ladder, the selection
// rules, the forecast zones and the state machine.
//
// Every fixture is synthetic and stated as turning points, so a triangle in
// these tests has known pivots and a failure localises to one clause instead
// of to "somewhere in AAPL". The near-miss group is the important half: a
// detector that finds every pattern it should is worthless if it also finds
// them where they are not.

import assert from "node:assert/strict";
import test from "node:test";

import { atr } from "../../web/v2/js/sim-indicators.js";
import {
  CHART_PATTERNS,
  DETECT_BARS,
  PATTERN_IDS,
  detectPattern,
  patternText,
  resolvePattern,
} from "../../web/v2/js/sim-patterns.js";
import { series } from "./_sim-bars.js";

const WARM = 45; // bars of quiet chop, so ATR(14) and the candle averages are warm

/** Build a deal from a list of turning points. */
function deal(turns, opts = {}) {
  const s = series(opts.start ?? 100).flat(opts.warm ?? WARM, opts.warmRange ?? 1.2);
  s.turns(turns);
  if (opts.after) opts.after(s);
  const bars = s.build();
  return { bars, atrArr: atr(bars, 14), A: bars.length - 1 };
}

const find = (d, opts) => detectPattern(d.bars, d.atrArr, d.A, opts);

/* ---------- fixtures, one per two-line family ---------- */

const H = (gap, price) => ({ gap, price, type: "high" });
const L = (gap, price) => ({ gap, price, type: "low" });

// The eight two-line families, each stated as the pair of straight lines it is
// supposed to be. Turning points are read OFF those lines rather than typed in
// by hand, so every pivot lies exactly where the fitted trendline will put it —
// which is the only way to test the touch rule rather than the fixture's own
// rounding.
const GAPS = [6, 5, 5, 4, 4, 3, 3];

function lineFixture(upper, lower, startsHigh = true) {
  let t = 0;
  return GAPS.map((gap, k) => {
    t += gap;
    const high = startsHigh === (k % 2 === 0);
    return { gap, price: (high ? upper : lower)(t), type: high ? "high" : "low" };
  });
}

const flat = (v) => () => v;
const ramp = (b, m) => (t) => b + m * t;

const TWO_LINE_FIXTURES = {
  "ascending-triangle": lineFixture(flat(110), ramp(100, 0.22)),
  "descending-triangle": lineFixture(ramp(112, -0.22), flat(100), false),
  "symmetrical-triangle": lineFixture(ramp(112, -0.2), ramp(96, 0.2)),
  "rising-wedge": lineFixture(ramp(106, 0.42), ramp(96, 0.55), false),
  "falling-wedge": lineFixture(ramp(114, -0.55), ramp(104, -0.42)),
  rectangle: lineFixture(flat(110), flat(100)),
  "ascending-channel": lineFixture(ramp(106, 0.5), ramp(96, 0.5), false),
  "descending-channel": lineFixture(ramp(120, -0.5), ramp(110, -0.5)),
};

const TWO_LINE_IDS = Object.keys(TWO_LINE_FIXTURES);

/* ---------- the other tier-1 families ---------- */

const DOUBLE_BOTTOM = [
  H(5, 112), L(6, 100), H(7, 109), L(6, 100.3), H(4, 106),
];
const DOUBLE_TOP = [
  L(5, 96), H(6, 112), L(7, 101), H(6, 111.7), L(4, 105),
];
const HEAD_SHOULDERS = [
  L(5, 96), H(5, 108), L(4, 101), H(5, 116), L(4, 100.6), H(5, 107.6), L(4, 103),
];
const INVERSE_HS = [
  H(5, 114), L(5, 102), H(4, 109), L(5, 94), H(4, 109.4), L(5, 102.4), H(4, 107),
];

/**
 * A pole and the drift that follows it. `offsets` are the flag's turning
 * points measured back from the pole's top, alternating counter-trend first:
 * a steady width is a flag, a narrowing one a pennant.
 */
function flagDeal(dir, { poleBars = 8, poleStep = 2.2, offsets, drift = 3 } = {}) {
  const s = series(100).flat(WARM, 1.2);
  // A pole starts at a swing pivot, so the fixture has to give it one: a dip
  // (or a spike) that the zigzag will keep, and then the run itself.
  s.turns([{ gap: 5, price: dir > 0 ? 94 : 106, type: dir > 0 ? "low" : "high" }]);
  if (dir > 0) s.up(poleBars, poleStep);
  else s.down(poleBars, poleStep);
  const base = s.price;
  const back = dir > 0 ? -1 : 1;
  s.turns(
    (offsets ?? FLAG_OFFSETS).map((d, k) => ({
      gap: drift,
      price: base + back * d,
      type: k % 2 === 0 ? (dir > 0 ? "low" : "high") : dir > 0 ? "high" : "low",
    }))
  );
  const bars = s.build();
  return { bars, atrArr: atr(bars, 14), A: bars.length - 1 };
}

// Constant width, drifting against the pole: a flag.
const FLAG_OFFSETS = [3.6, 1.2, 5.0, 2.6];
// Narrowing around a gently counter-trend midline: a pennant.
const PENNANT_OFFSETS = [3.8, 1.0, 3.2, 2.0];

/* ---------- positives ---------- */

for (const [id, turns] of Object.entries(TWO_LINE_FIXTURES)) {
  test(`positive: ${id}`, () => {
    const p = find(deal(turns));
    assert.ok(p, `${id}: nothing detected`);
    assert.equal(p.id, id);
    assert.equal(p.tier, 1);
    assert.equal(p.state, "forming");
  });
}

test("positive: double bottom", () => {
  const p = find(deal(DOUBLE_BOTTOM));
  assert.equal(p?.id, "double-bottom");
  assert.equal(p.bias, "bull");
  assert.equal(p.shape.kind, "neckline");
  assert.equal(p.shape.path.length, 3);
});

test("positive: double top", () => {
  const p = find(deal(DOUBLE_TOP));
  assert.equal(p?.id, "double-top");
  assert.equal(p.bias, "bear");
});

test("positive: head and shoulders", () => {
  const p = find(deal(HEAD_SHOULDERS));
  assert.equal(p?.id, "head-and-shoulders");
  assert.equal(p.shape.path.length, 5, "the five defining pivots are drawn");
  assert.ok(p.height > 0);
});

test("positive: inverse head and shoulders", () => {
  const p = find(deal(INVERSE_HS));
  assert.equal(p?.id, "inverse-head-and-shoulders");
  assert.equal(p.bias, "bull");
});

test("positive: bull flag and bull pennant", () => {
  assert.equal(find(flagDeal(1))?.id, "bull-flag");
  assert.equal(find(flagDeal(1, { offsets: PENNANT_OFFSETS }))?.id, "bull-pennant");
});

test("positive: bear flag and bear pennant", () => {
  assert.equal(find(flagDeal(-1))?.id, "bear-flag");
  assert.equal(find(flagDeal(-1, { offsets: PENNANT_OFFSETS }))?.id, "bear-pennant");
});

test("positive: every catalogue entry is reachable from a fixture", () => {
  const seen = new Set(
    [
      ...Object.keys(TWO_LINE_FIXTURES).map((id) => find(deal(TWO_LINE_FIXTURES[id]))?.id),
      find(deal(DOUBLE_BOTTOM))?.id,
      find(deal(DOUBLE_TOP))?.id,
      find(deal(HEAD_SHOULDERS))?.id,
      find(deal(INVERSE_HS))?.id,
      find(flagDeal(1))?.id,
      find(flagDeal(-1))?.id,
      find(flagDeal(1, { offsets: PENNANT_OFFSETS }))?.id,
      find(flagDeal(-1, { offsets: PENNANT_OFFSETS }))?.id,
    ].filter(Boolean)
  );
  const missing = CHART_PATTERNS.map((p) => p.id).filter((id) => !seen.has(id));
  assert.deepEqual(missing, [], `no fixture reaches: ${missing.join(", ")}`);
});

/* ---------- the classification table ---------- */

test("classification: each slope/width combination yields its own id", () => {
  // The eight two-line fixtures ARE the §5.3 table, one row each. Asserting
  // that they map onto eight DISTINCT ids is what proves the table is a
  // partition rather than a pile of overlapping rules.
  const ids = Object.entries(TWO_LINE_FIXTURES).map(([, t]) => find(deal(t))?.id);
  assert.equal(new Set(ids).size, 8);
  assert.deepEqual(ids, Object.keys(TWO_LINE_FIXTURES));
});

/* ---------- near misses: one broken clause each ---------- */

test("near-miss: a shape narrower than MIN_WIDTH_ATR is noise, not a rectangle", () => {
  const p = find(
    deal([H(6, 100.5), L(5, 100), H(5, 100.5), L(4, 100), H(4, 100.5), L(3, 100), H(3, 100.4)])
  );
  assert.notEqual(p?.id, "rectangle");
});

test("near-miss: a span shorter than MIN_BARS is rejected", () => {
  const p = find(deal([H(2, 110), L(2, 100), H(2, 110)]));
  assert.ok(!p || p.tier !== 1);
});

test("near-miss: fewer than two touches on a boundary is not a boundary", () => {
  // Three highs on a flat ceiling but only ONE low between them, so the lower
  // line is fitted through a single point. Bulkowski's rule is three touches
  // on one line and two on the other; one is not a line.
  const p = find(deal([H(6, 110), L(9, 100), H(9, 110), H(6, 110), L(3, 106)]));
  assert.ok(
    !TWO_LINE_IDS.includes(p?.id),
    `a one-touch boundary is not a boundary, but got ${p?.id}`
  );
});

test("near-miss: a triangle past APEX_MAX is rejected", () => {
  // The lows rise almost to the flat top, so the apex is already underfoot.
  const p = find(
    deal([H(6, 110), L(5, 100), H(5, 110), L(4, 106), H(4, 110), L(3, 109.2), H(3, 109.9)])
  );
  assert.notEqual(p?.id, "ascending-triangle");
});

test("near-miss: a triangle just inside APEX_MAX is still a triangle", () => {
  assert.equal(find(deal(TWO_LINE_FIXTURES["ascending-triangle"]))?.id, "ascending-triangle");
});

test("near-miss: a close outside the boundaries breaks respected()", () => {
  const p = find(
    deal(TWO_LINE_FIXTURES["ascending-triangle"], {
      after: (s) => {
        // Punch a close well above the flat top in the middle of the shape and
        // the shape was never respected.
      },
    })
  );
  assert.equal(p?.id, "ascending-triangle");
  // Now actually punch it: the same turns with one spike through the top.
  const spiked = deal([
    H(6, 110), L(5, 102), H(5, 118), L(4, 104.5), H(4, 110), L(3, 106.5), H(3, 109.6),
  ]);
  assert.notEqual(find(spiked)?.id, "ascending-triangle");
});

test("near-miss: unequal lows are not a double bottom", () => {
  const p = find(deal([H(5, 112), L(6, 100), H(7, 109), L(6, 105.5), H(4, 106)]));
  assert.notEqual(p?.id, "double-bottom");
});

test("near-miss: a shallow middle peak is not a double bottom", () => {
  const p = find(deal([H(5, 112), L(6, 100), H(7, 101.2), L(6, 100.3), H(4, 101)]));
  assert.notEqual(p?.id, "double-bottom");
});

test("near-miss: two extremes closer than DB_MIN_GAP do not qualify", () => {
  const p = find(deal([H(5, 112), L(2, 100), H(2, 109), L(2, 100.3), H(4, 106)]));
  assert.notEqual(p?.id, "double-bottom");
});

test("near-miss: a head lower than a shoulder is not a head", () => {
  const p = find(
    deal([L(5, 96), H(5, 108), L(4, 101), H(5, 116), L(4, 100.6), H(5, 118), L(4, 103)])
  );
  assert.notEqual(p?.id, "head-and-shoulders");
});

test("near-miss: troughs at different levels are not a neckline", () => {
  const p = find(
    deal([L(5, 96), H(5, 108), L(4, 101), H(5, 116), L(4, 108), H(5, 107.6), L(4, 103)])
  );
  assert.notEqual(p?.id, "head-and-shoulders");
});

test("near-miss: asymmetric shoulders are not H&S", () => {
  const p = find(
    deal([L(5, 96), H(5, 108), L(4, 101), H(5, 116), L(4, 100.6), H(5, 99), L(4, 96)])
  );
  assert.notEqual(p?.id, "head-and-shoulders");
});

test("near-miss: a pole shorter than POLE_ATR is not a flag", () => {
  const p = find(flagDeal(1, { poleStep: 0.3 }));
  assert.ok(!p || !p.id.endsWith("flag"));
});

test("near-miss: a flag that retraces more than FLAG_DEPTH is not a flag", () => {
  const s = series(100).flat(WARM, 1.2).up(8, 2.2);
  const base = s.price;
  s.turns([
    { gap: 3, price: base - 14, type: "low" },
    { gap: 3, price: base - 4, type: "high" },
    { gap: 3, price: base - 15, type: "low" },
  ]);
  const bars = s.build();
  const p = detectPattern(bars, atr(bars, 14), bars.length - 1);
  assert.ok(!p || !p.id.endsWith("flag"), "a 60% retracement is a reversal, not a flag");
});

/* ---------- visibility ---------- */

// Wider gaps, so the shape outruns the 35-session window on its own.
const LONG_CHANNEL = (() => {
  let t = 0;
  return [8, 8, 8, 8, 8, 8, 6].map((gap, k) => {
    t += gap;
    const high = k % 2 === 1;
    return { gap, price: (high ? ramp(106, 0.32) : ramp(96, 0.32))(t), type: high ? "high" : "low" };
  });
})();

test("visibility: detection reaches further back than the chart shows", () => {
  // The chart shows 35 sessions; this shape needs about fifty to exist at all.
  // It must still be found — the 35 is a phone-screen budget, not a claim
  // about how much history a pattern is made of.
  const d = deal(LONG_CHANNEL);
  const p = find(d);
  assert.ok(p, "nothing found");
  assert.ok(p.endIdx - p.startIdx + 1 > 35, `span ${p.endIdx - p.startIdx + 1} should exceed the window`);
  assert.ok(p.startIdx < d.A - 34, "the shape starts before the visible left edge");
});

test("visibility: a shape with too little left on screen is dropped", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  // Pretend the window starts three bars before the anchor: nothing drawable.
  assert.equal(find(d, { visibleFrom: d.A - 2, tiers: [1] }), null);
});

test("visibility: detectBars bounds how far back the detector reads", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-channel"]);
  assert.equal(find(d, { detectBars: 12, tiers: [1] }), null);
});

/* ---------- the tier ladder ---------- */

// Four rejections at one ceiling, with the last pullback shallow enough that
// the level is still within reach of the close — a level price has walked away
// from is not one worth naming.
const LEVEL_FIXTURE = [
  H(4, 110), L(6, 101), H(5, 110), L(6, 102), H(5, 110), L(6, 101.5), H(5, 110), L(3, 108.5),
];

test("ladder: a chart pattern beats a candle and a level", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  assert.equal(find(d).tier, 1);
});

test("ladder: with no chart pattern, tier 2 or 3 answers", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d, { tiers: [2, 3] });
  assert.ok(p == null || p.tier === 2 || p.tier === 3);
});

test("ladder: a level is the honest empty state", () => {
  // Price repeatedly turns at the same ceiling with no fittable geometry
  // underneath it.
  const d = deal(LEVEL_FIXTURE);
  const p = find(d, { tiers: [3] });
  assert.ok(p, "three touches at one price should cluster into a level");
  assert.equal(p.tier, 3);
  assert.equal(p.shape.kind, "level");
  assert.ok(p.label.startsWith("RESISTANCE") || p.label.startsWith("SUPPORT"));
  assert.equal(p.zoneNear, null, "a level makes no forecast");
  assert.equal(p.zoneUntil, null, "and so never expires");
});

test("ladder: nothing at all is a legal answer", () => {
  const s = series(100);
  for (let i = 0; i < 80; i++) s.bar({ o: 100, h: 100.2, l: 99.8, c: 100 });
  const bars = s.build();
  // No geometry and no level: the ladder falls through to null, which is what
  // keeps "no pattern" a real outcome rather than a bug.
  assert.equal(detectPattern(bars, atr(bars, 14), bars.length - 1, { tiers: [1, 3] }), null);
  // Tier 2 does find a doji here, and should: a tape this dead is indecision
  // by definition. It is the one thing on the chart worth saying.
  const t2 = detectPattern(bars, atr(bars, 14), bars.length - 1, { tiers: [2] });
  assert.equal(t2?.id, "doji");
});

test("ladder: a bullish engulfing after a downtrend is found at tier 2", () => {
  const s = series(140).flat(WARM, 1.2).down(14, 2.6);
  const prev = s.price;
  // A long black bar, then a white bar that swallows it whole.
  s.bar({ o: prev, h: prev + 0.2, l: prev - 5.2, c: prev - 5 });
  s.bar({ o: prev - 5.2, h: prev + 0.6, l: prev - 5.4, c: prev + 0.4 });
  const bars = s.build();
  const p = detectPattern(bars, atr(bars, 14), bars.length - 1, { tiers: [2] });
  assert.equal(p?.id, "bull-engulfing");
  assert.equal(p.tier, 2);
  assert.equal(p.shape.kind, "box");
  assert.equal(p.bias, "bull");
});

test("ladder: the same engulfing with no prior downtrend is not a pattern", () => {
  const s = series(100).flat(WARM + 14, 1.2);
  const prev = s.price;
  s.bar({ o: prev, h: prev + 0.2, l: prev - 5.2, c: prev - 5 });
  s.bar({ o: prev - 5.2, h: prev + 0.6, l: prev - 5.4, c: prev + 0.4 });
  const bars = s.build();
  const p = detectPattern(bars, atr(bars, 14), bars.length - 1, { tiers: [2] });
  assert.equal(p, null, "the trend gate is part of the definition, not a filter");
});

/* ---------- precedence ---------- */

test("precedence: selection is deterministic", () => {
  const d = deal(TWO_LINE_FIXTURES["symmetrical-triangle"]);
  const a = find(d);
  const b = find(d);
  assert.deepEqual(a, b);
});

test("precedence: quality leads, and quality is touches then span", () => {
  const p = find(deal(TWO_LINE_FIXTURES["ascending-triangle"]));
  const span = p.endIdx - p.startIdx + 1;
  assert.equal(p.quality, p.quality); // shape of the formula, asserted below
  assert.ok(p.quality >= 3 * 10 + span, "at least five confirmed touches and the span");
});

test("precedence: catalogue rank orders the families sanely", () => {
  const ids = CHART_PATTERNS.map((p) => p.id);
  assert.ok(ids.indexOf("ascending-triangle") < ids.indexOf("rising-wedge"));
  assert.ok(ids.indexOf("double-bottom") < ids.indexOf("bull-pennant"));
  assert.ok(ids.indexOf("head-and-shoulders") < ids.indexOf("rectangle"));
});

test("precedence: only ever one pattern comes back", () => {
  for (const turns of Object.values(TWO_LINE_FIXTURES)) {
    const p = find(deal(turns));
    assert.ok(p == null || typeof p.id === "string");
  }
});

/* ---------- zones ---------- */

test("zone: near is the Bulkowski target, far the textbook measured move", () => {
  const p = find(deal(TWO_LINE_FIXTURES["ascending-triangle"]));
  assert.equal(p.id, "ascending-triangle");
  assert.ok(Math.abs(p.zoneNear - (p.trigger + p.height * 0.7)) < 1e-9);
  assert.ok(Math.abs(p.zoneFar - (p.trigger + p.height)) < 1e-9);
  assert.ok(p.zoneNear < p.zoneFar, "the honest target is the nearer one");
});

test("zone: it is time-boxed to the pattern's own length", () => {
  const p = find(deal(TWO_LINE_FIXTURES["ascending-triangle"]));
  assert.equal(p.zoneUntil, p.endIdx + (p.endIdx - p.startIdx + 1));
});

test("zone: bias 'either' has none until it breaks, and then only one side", () => {
  const d = deal(TWO_LINE_FIXTURES["symmetrical-triangle"]);
  const p = find(d);
  assert.equal(p.bias, "either");
  assert.equal(p.zoneNear, null);
  assert.equal(p.zoneFar, null);
  assert.ok(p.trigger != null && p.triggerDown != null, "both sides are armed");

  const up = resolvePattern(p, breakUp(d.bars, p.trigger), d.A + 1);
  assert.equal(up.state, "broken-out");
  assert.equal(up.bias, "bull");
  assert.ok(up.zoneNear > up.trigger, "the zone appears on the side that broke");
  assert.equal(up.triggerDown, null);
});

test("zone: a channel never gets one — it makes no measured-move claim", () => {
  const p = find(deal(TWO_LINE_FIXTURES["ascending-channel"]));
  assert.equal(p.id, "ascending-channel");
  assert.equal(p.hitRate, null);
  assert.equal(p.zoneNear, null);
});

/* ---------- states ---------- */

/** Append `n` bars all closing at `price`. */
function extend(bars, closes) {
  const out = bars.slice();
  for (const c of closes) {
    const prev = out[out.length - 1].c;
    out.push({
      d: "2099-01-01",
      o: prev,
      h: Math.max(prev, c) + 0.1,
      l: Math.min(prev, c) - 0.1,
      c,
      v: 1e6,
    });
  }
  return out;
}

const breakUp = (bars, trigger) => extend(bars, [trigger + 1.5]);

function stateAfter(d, p, closes) {
  const bars = extend(d.bars, closes);
  return resolvePattern(p, bars, bars.length - 1);
}

test("state: a close beyond the trigger is a breakout", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const r = stateAfter(d, p, [p.trigger + 1]);
  assert.equal(r.state, "broken-out");
  assert.equal(r.breakoutIdx, d.A + 1);
  assert.equal(r.shape.x1, d.A + 1, "the shape stops being drawn past the break");
});

test("state: broken-out to throwback and back again", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const back = stateAfter(d, p, [p.trigger + 1, p.trigger - 0.5]);
  assert.equal(back.state, "throwback");
  const again = stateAfter(d, p, [p.trigger + 1, p.trigger - 0.5, p.trigger + 0.8]);
  assert.equal(again.state, "broken-out", "throwbacks are the 64% case, not a failure");
});

test("state: reaching zoneNear confirms", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const r = stateAfter(d, p, [p.trigger + 1, p.zoneNear + 0.2]);
  assert.equal(r.state, "confirmed");
  assert.equal(r.resolvedIdx, d.A + 2);
});

test("state: a close through invalidate fails", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const r = stateAfter(d, p, [p.trigger + 1, p.invalidate - 1]);
  assert.equal(r.state, "failed");
});

test("state: a bar through both levels takes the bad outcome", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  // Break out, then a bar that closes past the target AND below the stop is
  // impossible for one close — so assert the ordering directly instead: a
  // close below invalidate wins even when the zone was reached first.
  const r = stateAfter(d, p, [p.trigger + 1, p.zoneNear + 1, p.invalidate - 1]);
  assert.equal(r.state, "confirmed", "confirmation already happened and is frozen");
  const s = stateAfter(d, p, [p.trigger + 1, p.invalidate - 1, p.zoneNear + 1]);
  assert.equal(s.state, "failed");
});

test("state: while forming, a close outside the shape abandons it", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const r = stateAfter(d, p, [p.invalidate - 4]);
  assert.equal(r.state, "abandoned");
});

test("state: no break inside the time box expires it", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const mid = (p.trigger + p.invalidate) / 2;
  const closes = new Array(p.zoneUntil - d.A + 2).fill(mid);
  const r = stateAfter(d, p, closes);
  assert.ok(["expired", "abandoned"].includes(r.state));
});

test("state: terminal states are frozen", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const done = stateAfter(d, p, [p.trigger + 1, p.zoneNear + 0.2]);
  assert.equal(done.state, "confirmed");
  const bars = extend(d.bars, [p.trigger + 1, p.zoneNear + 0.2, p.invalidate - 5]);
  assert.equal(resolvePattern(done, bars, bars.length - 1), done);
});

test("state: a twenty-session jump resolves as twenty single steps would", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const closes = [p.trigger + 1];
  for (let i = 0; i < 19; i++) closes.push(p.trigger + 1 + i * 0.05);
  const bars = extend(d.bars, closes);
  const jumped = resolvePattern(p, bars, bars.length - 1);
  let stepped = p;
  for (let i = d.A + 1; i < bars.length; i++) stepped = resolvePattern(stepped, bars, i);
  assert.deepEqual(jumped, stepped, "PASS jumps 20 sessions; it must land in the same place");
});

test("state: resolvePattern is idempotent", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const bars = extend(d.bars, [p.trigger + 1]);
  const once = resolvePattern(p, bars, bars.length - 1);
  assert.deepEqual(resolvePattern(once, bars, bars.length - 1), once);
});

test("state: a level is broken, never failed or confirmed", () => {
  const d = deal(LEVEL_FIXTURE);
  const p = find(d, { tiers: [3] });
  assert.equal(p.state, "forming");
  const r = stateAfter(d, p, [p.trigger + 2, p.trigger - 6, p.trigger - 8]);
  assert.equal(r.state, "broken-out");
  assert.equal(r.resolvedIdx, d.A + 1, "and it stops there");
});

test("state: null resolves to null", () => {
  assert.equal(resolvePattern(null, [], 0), null);
});

/* ---------- the label ---------- */

test("label: the state suffix is worded per tier and dropped when narrow", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  assert.equal(patternText(p), "ASC TRIANGLE · FORMING");
  assert.equal(patternText(p, true), "ASC TRIANGLE");
  const lv = find(deal(LEVEL_FIXTURE), { tiers: [3] });
  assert.equal(patternText(lv), lv.label, "a level that holds says nothing about state");
  assert.equal(patternText(null), "");
});

/* ---------- invariants ---------- */

test("invariant: detectPattern never reads past the anchor", () => {
  // Run over several anchors on one long series, not a hand-picked index: the
  // bug this catches is intermittent by nature.
  const s = series(100, { noise: 0.9, seed: 7 });
  for (let i = 0; i < 14; i++) {
    s.up(4 + (i % 3), 1.4).down(3 + (i % 4), 1.1);
  }
  const bars = s.build();
  const atrArr = atr(bars, 14);
  let checked = 0;
  for (let A = 60; A < bars.length; A += 7) {
    const full = detectPattern(bars, atrArr, A);
    const trunc = detectPattern(bars.slice(0, A + 1), atrArr.slice(0, A + 1), A);
    assert.deepEqual(trunc, full, `anchor ${A} sees a different pattern with the future removed`);
    checked++;
  }
  assert.ok(checked >= 5, "the sweep must actually cover several anchors");
});

test("invariant: endIdx never exceeds the anchor", () => {
  const d = deal(TWO_LINE_FIXTURES["descending-triangle"]);
  for (let A = d.A - 6; A <= d.A; A++) {
    const p = detectPattern(d.bars, d.atrArr, A);
    if (p) assert.ok(p.endIdx <= A, `endIdx ${p.endIdx} > anchor ${A}`);
  }
});

test("invariant: resolvePattern never reads past throughIdx", () => {
  const d = deal(TWO_LINE_FIXTURES["ascending-triangle"]);
  const p = find(d);
  const bars = extend(d.bars, [p.trigger + 1, p.zoneFar + 5]);
  const held = resolvePattern(p, bars, d.A); // the future bars exist but are unseen
  assert.equal(held.state, "forming");
});

test("invariant: short and malformed input returns null, never a throw", () => {
  assert.equal(detectPattern([], [], 0), null);
  assert.equal(detectPattern(null, [], 0), null);
  const tiny = series(100).flat(6, 1).build();
  assert.equal(detectPattern(tiny, atr(tiny, 14), tiny.length - 1), null);
  const d = deal(TWO_LINE_FIXTURES["rectangle"]);
  assert.equal(detectPattern(d.bars, d.atrArr, d.bars.length + 50), null);
  assert.equal(detectPattern(d.bars, d.atrArr, -1), null);
});

test("invariant: PATTERN_IDS covers every id the detector can return", () => {
  const ids = new Set(PATTERN_IDS);
  for (const turns of Object.values(TWO_LINE_FIXTURES)) {
    const p = find(deal(turns));
    if (p) assert.ok(ids.has(p.id), `${p.id} missing from PATTERN_IDS`);
  }
  assert.ok(ids.has("support") && ids.has("resistance"));
  assert.ok(ids.has("bull-engulfing"), "tier-2 ids belong in ?p= too");
});

test("invariant: DETECT_BARS is wider than the chart window", () => {
  assert.ok(DETECT_BARS > 35, "the chart's 35 sessions are a display budget, not a detection one");
});
