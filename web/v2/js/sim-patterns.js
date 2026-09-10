// Chart pattern annotation for the swing-trading simulator: triangles, wedges,
// flags, channels, double tops and bottoms, head-and-shoulders, and the
// support/resistance levels underneath them — plus the tier ladder that falls
// back to a candlestick and then to a level, and the state machine that plays
// the pattern out as the hand does.
//
// Spec: docs/web_v2/chart_pattern_spec.md. Head-and-shoulders follows Lo,
// Mamaysky & Wang (2000), "Foundations of Technical Analysis", with their
// fixed 1.5% symmetry tolerances replaced by ATR-relative ones so that one
// constant serves a 500-name universe.
//
// Pure: no DOM, no fetch. Covered by tests/web/sim-patterns.test.js.
//
// Three rules run through the whole module and are worth stating once.
//
//   * NO LOOK-AHEAD. `detectPattern(bars, atr, A)` reads nothing past `A`, and
//     `resolvePattern(p, bars, T)` nothing past `T`. This is the one bug that
//     would ruin the simulator silently — nothing on screen would say the
//     chart had peeked — so it is a mandatory test, not a convention.
//   * ONE PATTERN, EVER. Across all three tiers, at most one annotation is
//     returned. `null` is the common outcome and must render as nothing at
//     all: the chart already carries four panels, three moving averages, a
//     decision divider and a draggable stop.
//   * DETECTION IS PINNED. It runs once, at deal time. The shape is frozen for
//     the hand and only its STATE evolves. A label that churns as you tap
//     +1 DAY teaches nothing, and the pattern you acted on is the one whose
//     fate you want to watch.

import { CANDLE_IDS, candlesAt } from "./sim-candles.js";
import {
  MIN_SWING_ATR,
  PIVOT_K,
  SR_MIN_TOUCHES,
  SR_NEAR_ATR,
  SR_RECENT_BARS,
  SR_TOL_ATR,
  TOUCH_ATR,
  countTouches,
  fitLine,
  levels,
  lineAt,
  pivotsOf,
  zigzag,
} from "./sim-structure.js";

/* ---------- how far back the detector may look ---------- */

/**
 * The chart shows 35 sessions because that is what fits a phone screen legibly
 * — it is a DISPLAY budget, not a claim about how much history a pattern is
 * made of. Detection reads back over `DETECT_BARS` instead, which is what lets
 * a head-and-shoulders or a two-month channel be found at all; a shape that
 * starts before the left edge is drawn from the edge, which is honest and is
 * what every charting platform does when you scroll.
 */
export const DETECT_BARS = 90;

// Re-exported so the page module has one import site for everything pattern:
// evaluating a fitted line at a bar index is drawing, not analysis.
export { lineAt } from "./sim-structure.js";

/** Longest pattern the detector will accept, in bars. */
const MAX_SPAN = 60;

/** Shortest allowed pattern span. */
const MIN_BARS = 8;

/** A two-line pattern's last bar must be within this many bars of the anchor. */
const CHART_RECENCY = 5;

/**
 * A neckline pattern's last EXTREME may be further back — its trigger is a
 * level price has yet to cross, so the shape stays live long after the second
 * bottom printed. `CHART_RECENCY` cannot serve here: the second low of a
 * double bottom is a confirmed pivot, so it is never within five bars of the
 * anchor and the pattern would be undetectable. Ten, not the twenty this
 * started at: a neckline pattern found twenty bars after its second extreme
 * has usually already broken by the time the hand is dealt, and the census
 * showed that pushing `forming` at the decision bar below its band.
 */
const NECK_RECENCY = 10;

/* ---------- shared geometry ---------- */

const BREAK_ATR = 0.25; // close this far outside a boundary => broken
const FLAT_SLOPE = 0.15; // |rise over the span| <= this * width => horizontal
const CONVERGE = 0.75; // endWidth <= this * startWidth => converging
const PARALLEL = 0.25; // |endWidth - startWidth| <= this * startWidth
const APEX_MAX = 0.85; // reject past this fraction of the way to the apex
const MIN_WIDTH_ATR = 1.0; // a pattern narrower than this is noise

/* ---------- flags and pennants ---------- */

const POLE_MIN = 4;
const POLE_MAX = 15;
const POLE_ATR = 3.0; // minimum pole height, in ATR(14)
const POLE_CLEAN = 0.35; // max counter-move inside the pole, as a fraction of it
const FLAG_MIN = 3;
const FLAG_MAX = 15;
const FLAG_DEPTH = 0.5; // max retracement of the pole
const FLAG_DRIFT = 0.1; // max with-trend overshoot during the flag
const FLAG_TILT = 0.05; // max with-trend tilt of the flag, per pole height

/* ---------- double top / bottom ---------- */
// DB_TOL_ATR and HS_TOL_ATR below are both half the figures the spec derives
// from Lo, Mamaysky & Wang. Those tolerances describe one shape a person is
// looking at; here they are applied to every consecutive triple and quintuple
// in a ninety-session zigzag, and at 0.6/0.7 ATR the neckline families alone
// took half of all decision points. The census is what set them.

const DB_TOL_ATR = 0.35; // how equal the two extremes must be
const DB_MIN_GAP = 5;
const DB_MAX_GAP = 25; // bars between them
const DB_RISE_ATR = 2.0; // the intervening peak must be a real peak

/* ---------- head and shoulders ---------- */

const HS_TOL_ATR = 0.35; // shoulder / trough symmetry tolerance
const HS_HEAD_ATR = 2.0; // the head must clear the troughs by this much
/**
 * A neckline may slope, but not so steeply that "below the neckline" stops
 * meaning anything. Capped at one head-height of drift across the pattern.
 */
const HS_NECK_TILT = 1.0;

/* ---------- the catalogue ---------- */

/**
 * `hitRate` is Bulkowski's measured share of breakouts that reach the full
 * measured move; it is what makes `zoneNear` an honest target rather than a
 * textbook one. The `source` column is not decoration — three of these are
 * assumptions and the census must revisit them.
 *
 * `rank` is the tie-break of last resort, best first, following Bulkowski's
 * measured performance. It is not cosmetic: the rising wedge is 36th of 36
 * bearish patterns and the pennant fails 54% of the time, so both sort below
 * patterns nobody puts on a T-shirt.
 */
export const CHART_PATTERNS = [
  { id: "ascending-triangle", label: "ASC TRIANGLE", bias: "bull", kind: "continuation", hitRate: 0.7 },
  { id: "descending-triangle", label: "DESC TRIANGLE", bias: "bear", kind: "continuation", hitRate: 0.44 },
  { id: "double-bottom", label: "DOUBLE BOTTOM", bias: "bull", kind: "reversal", hitRate: 0.66 },
  { id: "double-top", label: "DOUBLE TOP", bias: "bear", kind: "reversal", hitRate: 0.66 },
  { id: "inverse-head-and-shoulders", label: "INV H&S", bias: "bull", kind: "reversal", hitRate: 0.55 },
  { id: "head-and-shoulders", label: "H&S", bias: "bear", kind: "reversal", hitRate: 0.55 },
  // "either" carries no zone until it breaks: the pattern has not chosen a
  // side, and drawing a directional target before the break would invent a
  // claim it does not make. hitRate is then read per direction.
  { id: "symmetrical-triangle", label: "SYM TRIANGLE", bias: "either", kind: "continuation", hitRate: 0.58, hitRateDown: 0.36 },
  { id: "falling-wedge", label: "FALLING WEDGE", bias: "bull", kind: "reversal", hitRate: 0.58 },
  { id: "rectangle", label: "RECTANGLE", bias: "either", kind: "continuation", hitRate: 0.58, hitRateDown: 0.58 },
  { id: "ascending-channel", label: "ASC CHANNEL", bias: "bull", kind: "continuation", hitRate: null },
  { id: "descending-channel", label: "DESC CHANNEL", bias: "bear", kind: "continuation", hitRate: null },
  { id: "bull-flag", label: "BULL FLAG", bias: "bull", kind: "continuation", hitRate: 0.46 },
  { id: "bear-flag", label: "BEAR FLAG", bias: "bear", kind: "continuation", hitRate: 0.46 },
  { id: "rising-wedge", label: "RISING WEDGE", bias: "bear", kind: "reversal", hitRate: 0.32 },
  { id: "bull-pennant", label: "BULL PENNANT", bias: "bull", kind: "continuation", hitRate: 0.35 },
  { id: "bear-pennant", label: "BEAR PENNANT", bias: "bear", kind: "continuation", hitRate: 0.35 },
];

const BY_ID = new Map(CHART_PATTERNS.map((p, rank) => [p.id, { ...p, rank }]));

/** The §5.3 classification table: one lookup replaces eight detectors. */
const TWO_LINE = {
  "flat|up|converging": "ascending-triangle",
  "down|flat|converging": "descending-triangle",
  "down|up|converging": "symmetrical-triangle",
  "up|up|converging": "rising-wedge",
  "down|down|converging": "falling-wedge",
  "flat|flat|parallel": "rectangle",
  "up|up|parallel": "ascending-channel",
  "down|down|parallel": "descending-channel",
};

/**
 * Every id `?p=<id>` will accept, across all three tiers — so the page module
 * has one place to validate against rather than three.
 */
export const PATTERN_IDS = [
  ...CHART_PATTERNS.map((p) => p.id),
  ...CANDLE_IDS,
  "support",
  "resistance",
];

/* ---------- state ---------- */

/** @typedef {"forming"|"broken-out"|"throwback"|"confirmed"|"failed"|"expired"|"abandoned"} PatternState */

const TERMINAL = new Set(["confirmed", "failed", "expired", "abandoned"]);

/**
 * Has this pattern finished? For tiers 1 and 2 that is the four terminal
 * states. A level is also finished the moment it breaks: there is no target
 * beyond it to reach and no invalidation to fail, so "broken" is the end of
 * what a level has to say.
 */
function isTerminal(p) {
  return TERMINAL.has(p.state) || (p.tier === 3 && p.state === "broken-out");
}

/**
 * Has this pattern nothing left to say? The same question `isTerminal` answers,
 * asked from outside the module, with `null` — no pattern at all — counting as
 * over. The simulator uses it to decide whether a decision day that has moved
 * (WAIT) is entitled to a fresh look, without the page module having to know
 * what any state name means.
 */
export function isPatternOver(p) {
  return !p || isTerminal(p);
}

/**
 * How each state is worded, per tier. The raw state names are right for a
 * chart pattern and wrong for the other two: a completed engulfing is not
 * "forming", it is an unconfirmed setup, and a support level is never
 * "forming" at all — it either holds or it has been broken. Keeping the
 * mapping here rather than in the page module is what lets simulator.js draw
 * the annotation without knowing what any of it means.
 */
const STATE_TEXT = {
  1: {
    forming: "FORMING",
    "broken-out": "BREAKOUT",
    throwback: "THROWBACK",
    confirmed: "TARGET",
    failed: "FAILED",
    expired: "EXPIRED",
    abandoned: "VOID",
  },
  2: {
    forming: "SETUP",
    "broken-out": "TRIGGERED",
    throwback: "THROWBACK",
    confirmed: "TARGET",
    failed: "FAILED",
    expired: "EXPIRED",
    abandoned: "VOID",
  },
  3: { forming: "", "broken-out": "BROKEN" },
};

/**
 * The annotation's one line of text: `"ASC TRIANGLE · FORMING"`. On a narrow
 * chart the state is dropped — the line style still separates a forming shape
 * from a broken one, and two truncated words say less than one whole one.
 */
export function patternText(p, narrow = false) {
  if (!p) return "";
  const state = (STATE_TEXT[p.tier] || STATE_TEXT[1])[p.state] || "";
  if (narrow || !state) return p.label;
  return `${p.label} · ${state}`;
}

/* ---------- detection ---------- */

/**
 * The one pattern to annotate this deal, or `null`.
 *
 * @param {Array} bars   {d,o,h,l,c,v}, full history
 * @param {Array} atrArr `atr(bars, 14)` — same length, leading nulls
 * @param {number} anchorIdx  the decision bar; nothing past it is read
 * @param {Object} [opts]
 * @param {number} [opts.detectBars]  history the detector may read (DETECT_BARS)
 * @param {number} [opts.visibleFrom] the chart's left edge, for the drawability guard
 * @param {number[]} [opts.tiers]     which tiers to run — the census uses this
 * @returns {Object|null}
 */
export function detectPattern(bars, atrArr, anchorIdx, opts = {}) {
  const A = anchorIdx;
  if (!Array.isArray(bars) || A == null || A < 0 || A >= bars.length) return null;
  if (!Array.isArray(atrArr) || atrArr[A] == null || !(atrArr[A] > 0)) return null;

  const detectBars = opts.detectBars ?? DETECT_BARS;
  const from = Math.max(0, A - detectBars + 1);
  const visibleFrom = opts.visibleFrom ?? Math.max(0, A - 34);
  const tiers = opts.tiers ?? [1, 2, 3];
  if (A - from + 1 < MIN_BARS) return null;

  const ctx = { bars, atr: atrArr, A, from, visibleFrom };
  ctx.pivots = pivotsOf(bars, from, A, PIVOT_K);
  ctx.zz = zigzag(ctx.pivots, bars, atrArr, MIN_SWING_ATR);

  // The ladder: take the first tier that yields anything. Geometry is the
  // stronger claim; a candle marks a moment and is worth naming only when
  // there is no larger structure to name instead; a level is the honest empty
  // state, because when no shape fits there is usually still a price that
  // price is pressing against.
  for (const tier of tiers) {
    const found =
      tier === 1 ? bestChart(ctx) : tier === 2 ? bestCandle(ctx) : bestLevel(ctx);
    if (found) return found;
  }
  return null;
}

/* ---------- tier 1: the chart catalogue ---------- */

function bestChart(ctx) {
  const cands = [];
  for (let e = ctx.A - CHART_RECENCY + 1; e <= ctx.A; e++) {
    if (e < ctx.from + MIN_BARS - 1) continue;
    for (const sp of ctx.zz) {
      if (sp.provisional) continue; // a shape may not START on an unconfirmed turn
      const s = sp.i;
      const span = e - s + 1;
      if (s < ctx.from || span < MIN_BARS || span > MAX_SPAN) continue;
      const c = twoLine(ctx, s, e);
      if (c) cands.push(c);
    }
    const f = flag(ctx, e);
    if (f) cands.push(f);
  }
  // Necklines are found once, at the anchor: their trigger is a horizontal (or
  // gently sloping) level, so sliding `e` back would produce the same shape.
  for (const c of doubles(ctx)) cands.push(c);
  for (const c of headShoulders(ctx)) cands.push(c);

  return pickBest(cands, ctx);
}

/**
 * Precedence within tier 1: quality, then recency, then catalogue rank.
 *
 * Quality leads here, unlike the candlestick tier where recency leads. A chart
 * pattern's span already CONTAINS the recent bars, so recency barely
 * discriminates; how well-formed the shape is does.
 */
function pickBest(cands, ctx) {
  const usable = cands.filter((c) => drawable(c, ctx));
  if (!usable.length) return null;
  usable.sort(
    (a, b) =>
      b.quality - a.quality ||
      b.endIdx - a.endIdx ||
      (BY_ID.get(a.id)?.rank ?? 99) - (BY_ID.get(b.id)?.rank ?? 99) ||
      a.startIdx - b.startIdx
  );
  return usable[0];
}

/**
 * Enough of the shape has to land on the visible chart for the annotation to
 * mean anything. A pattern that starts before the left edge is fine — it is
 * clipped there, the way every platform clips — but one whose visible remnant
 * is shorter than the shortest pattern we would detect in the first place is
 * a label with no picture under it.
 */
function drawable(c, ctx) {
  return c.endIdx - Math.max(c.startIdx, ctx.visibleFrom) + 1 >= MIN_BARS;
}

/* ---------- the two-line families ---------- */

function twoLine(ctx, s, e) {
  const { atr } = ctx;
  const P = ctx.zz.filter((p) => p.i >= s && p.i <= e);
  const highs = P.filter((p) => p.type === "high");
  const lows = P.filter((p) => p.type === "low");
  if (highs.length < 2 || lows.length < 2) return null;

  const upper = fitLine(highs);
  const lower = fitLine(lows);
  if (!upper || !lower) return null;

  const w0 = lineAt(upper, s) - lineAt(lower, s);
  const w1 = lineAt(upper, e) - lineAt(lower, e);
  if (!(w0 > 0) || !(w1 > 0)) return null;
  if (!(atr[s] > 0) || w0 < MIN_WIDTH_ATR * atr[s]) return null;

  const meanW = (w0 + w1) / 2;
  const su = slopeClass(upper, s, e, meanW);
  const sl = slopeClass(lower, s, e, meanW);
  const shape =
    w1 <= CONVERGE * w0 ? "converging" : Math.abs(w1 - w0) <= PARALLEL * w0 ? "parallel" : null;
  if (!shape) return null;

  const id = TWO_LINE[`${su}|${sl}|${shape}`];
  if (!id) return null;

  // Bulkowski, exactly: three touches on one line and two on the other. Only
  // CONFIRMED pivots count — countTouches drops the provisional ones.
  const tu = countTouches(upper, highs, atr, TOUCH_ATR);
  const tl = countTouches(lower, lows, atr, TOUCH_ATR);
  // Bulkowski's rule is three touches on one line and two on the other, which
  // is right for a human reading one chart. This is an automated scan over
  // ~80 candidate spans per deal, where two touches on a fitted line is not a
  // finding — two points always lie on their own line. Three on each side is
  // the smallest rule that survives that many attempts; the census puts the
  // difference at 25% of decision points against 36%.
  if (Math.max(tu, tl) < 3 || Math.min(tu, tl) < 3) return null;
  if (!respected(ctx, upper, lower, s, e)) return null;

  let apexIdx = null;
  if (shape === "converging") {
    apexIdx = apexOf(upper, lower);
    // Bulkowski's rule: ascending-triangle breakouts happen ~64% of the way to
    // the apex, and a triangle that reaches its apex has expired.
    if (apexIdx == null || apexIdx <= s || (e - s) / (apexIdx - s) >= APEX_MAX) return null;
  }

  const def = BY_ID.get(id);
  const upperAt = lineAt(upper, e);
  const lowerAt = lineAt(lower, e);
  const bull = def.bias === "bull";
  const either = def.bias === "either";

  return finish(ctx, {
    id,
    def,
    startIdx: s,
    endIdx: e,
    shape: { kind: "lines", lines: [upper, lower], x0: s, x1: e },
    trigger: either || bull ? upperAt : lowerAt,
    triggerDown: either ? lowerAt : null,
    invalidate: either ? null : bull ? lowerAt : upperAt,
    upperAt,
    lowerAt,
    height: w0,
    apexIdx,
    touches: tu + tl,
  });
}

function slopeClass(line, s, e, w) {
  const r = (lineAt(line, e) - lineAt(line, s)) / w;
  if (Math.abs(r) <= FLAT_SLOPE) return "flat";
  return r > 0 ? "up" : "down";
}

/** Every close in [s,e] stays inside the two lines, within BREAK_ATR. */
function respected(ctx, upper, lower, s, e) {
  const { bars, atr } = ctx;
  for (let i = s; i <= e; i++) {
    const a = atr[i];
    if (a == null || !(a > 0)) return false;
    if (bars[i].c > lineAt(upper, i) + BREAK_ATR * a) return false;
    if (bars[i].c < lineAt(lower, i) - BREAK_ATR * a) return false;
  }
  return true;
}

/** The bar index where the two lines meet, or null if they never do. */
function apexOf(upper, lower) {
  const dm = upper.m - lower.m;
  if (Math.abs(dm) < 1e-12) return null;
  return (lower.b - upper.b) / dm;
}

/* ---------- flags and pennants ---------- */

/**
 * A pole and the drift that follows it, ending at `e`.
 *
 * Deviation from the spec's §5.4, taken deliberately: the trigger is the
 * fitted upper (bull) or lower (bear) envelope at the flag's last bar, not the
 * flag's extreme high or low. Those are almost the same number, but only one
 * of them is the line the chart actually draws — and a chart whose drawn
 * boundary and stated trigger are different objects is lying about where the
 * break is. `height` stays `poleH`, which is Bulkowski's rule for both
 * patterns and the whole point of the measure rule here.
 */
function flag(ctx, e) {
  const { bars, atr } = ctx;
  // Many pole/flag splits describe the same rally. Collect them and keep the
  // tallest pole, so the annotation names the move a trader would point at
  // rather than whichever split the loop reached first. Height is compared in
  // raw price, NOT in ATRs: every candidate here is the same instrument at the
  // same moment, and dividing by ATR at the pole's top would quietly reward
  // splits that push the top into the flag, where volatility has already
  // fallen. ATR still sets the threshold a pole must clear; it just has no
  // business ranking candidates against each other.
  let best = null;
  let bestPole = 0;
  for (const dir of [1, -1]) {
    // The pole starts on a zigzag pivot — a swing low for a bull flag, a swing
    // high for a bear one. Without that anchor the pole can start anywhere,
    // including part-way through a quiet stretch that adds height to it while
    // contributing no actual move, and every measurement downstream is then
    // taken off a pole that was never there.
    const poleStarts = ctx.zz.filter(
      (pt) => !pt.provisional && pt.type === (dir > 0 ? "low" : "high")
    );
    for (let flagLen = FLAG_MIN; flagLen <= FLAG_MAX; flagLen++) {
      const p1 = e - flagLen;
      for (const pt of poleStarts) {
        const p0 = pt.i;
        const poleLen = p1 - p0;
        if (poleLen < POLE_MIN || poleLen > POLE_MAX) continue;
        if (p0 < ctx.from) continue;
        const a = atr[p1];
        if (a == null || !(a > 0)) continue;

        const poleH = dir * (bars[p1].c - bars[p0].c);
        if (poleH < POLE_ATR * a) continue;

        // The pole must be a clean run, not a round trip with a net move.
        let worst = 0;
        let extreme = bars[p0].c;
        for (let i = p0; i <= p1; i++) {
          const px = dir > 0 ? bars[i].h : bars[i].l;
          if (dir * (px - extreme) > 0) extreme = px;
          worst = Math.max(worst, dir * (extreme - (dir > 0 ? bars[i].l : bars[i].h)));
        }
        if (worst > POLE_CLEAN * poleH) continue;

        const F = [];
        for (let i = p1 + 1; i <= e; i++) F.push(bars[i]);
        if (F.length < FLAG_MIN) continue;
        const fHi = Math.max(...F.map((b) => b.h));
        const fLo = Math.min(...F.map((b) => b.l));
        const depth = dir * (bars[p1].c - (dir > 0 ? fLo : fHi));
        if (depth > FLAG_DEPTH * poleH) continue;
        const over = dir * ((dir > 0 ? fHi : fLo) - bars[p1].c);
        if (over > FLAG_DRIFT * poleH) continue;
        // Contraction: the flag breathes less than the pole did.
        const meanRange = (arr) => arr.reduce((t, b) => t + (b.h - b.l), 0) / arr.length;
        const pole = bars.slice(p0, p1 + 1);
        if (!(meanRange(F) < meanRange(pole))) continue;
        // Tilt: a flag drifts against the pole or sideways, never with it.
        const closes = F.map((b, i) => ({ i: p1 + 1 + i, price: b.c }));
        const fit = fitLine(closes);
        if (dir * fit.m * F.length > FLAG_TILT * poleH) continue;

        const upper = envelope(bars, p1 + 1, e, "high");
        const lower = envelope(bars, p1 + 1, e, "low");
        const w0 = lineAt(upper, p1 + 1) - lineAt(lower, p1 + 1);
        if (!(w0 > 0)) continue;

        // Flag or pennant, decided on the envelope's own width rather than on
        // the raw high-low range of each half. The spec reaches for a range
        // test because it assumes too few pivots for a two-line fit, but these
        // envelopes are fitted to EVERY bar, so the width is always available
        // — and it is the better measure, because a raw range test is biased.
        // The flag's first bar opens at the pole's top, so the first half
        // always inherits the drop off the pole and reads wider than it is;
        // every parallel flag would be filed as a pennant. Width detrends that
        // away, and reuses the same CONVERGE constant the two-line families
        // are classified by.
        const w1 = lineAt(upper, e) - lineAt(lower, e);
        const pennant = w1 <= CONVERGE * w0;
        const id = `${dir > 0 ? "bull" : "bear"}-${pennant ? "pennant" : "flag"}`;
        const def = BY_ID.get(id);

        if (poleH <= bestPole) continue;
        bestPole = poleH;

        const upperAt = lineAt(upper, e);
        const lowerAt = lineAt(lower, e);
        best = finish(ctx, {
          id,
          def,
          startIdx: p0,
          endIdx: e,
          shape: {
            kind: "lines",
            lines: [upper, lower],
            path: [
              [p0, bars[p0].c],
              [p1, bars[p1].c],
            ],
            x0: p1 + 1,
            x1: e,
          },
          trigger: dir > 0 ? upperAt : lowerAt,
          triggerDown: null,
          invalidate: dir > 0 ? lowerAt : upperAt,
          upperAt,
          lowerAt,
          height: poleH,
          apexIdx: null,
          // A flag is defined by its pole and its containment, not by counted
          // touches; three is the floor the two-line families must clear, so
          // scoring it as three keeps the quality scale comparable.
          touches: 3,
        });
      }
    }
  }
  return best;
}

/**
 * A least-squares line through the bars' highs (or lows), shifted until no bar
 * pokes through it. The result is a channel boundary that touches the extreme
 * and contains everything — which is what a flag's edge is drawn as.
 */
function envelope(bars, s, e, which) {
  const pts = [];
  for (let i = s; i <= e; i++) pts.push({ i, price: which === "high" ? bars[i].h : bars[i].l });
  const line = fitLine(pts);
  let shift = 0;
  for (const p of pts) {
    const d = p.price - lineAt(line, p.i);
    if (which === "high" ? d > shift : d < shift) shift = d;
  }
  return { m: line.m, b: line.b + shift };
}

/* ---------- double top / double bottom ---------- */

function doubles(ctx) {
  const { bars, atr, A } = ctx;
  const out = [];
  for (let k = 0; k + 2 < ctx.zz.length; k++) {
    const [e1, mid, e2] = [ctx.zz[k], ctx.zz[k + 1], ctx.zz[k + 2]];
    if (e1.provisional || mid.provisional || e2.provisional) continue;
    if (e1.type !== e2.type || mid.type === e1.type) continue;
    const bottom = e1.type === "low";
    const a = atr[e2.i];
    if (a == null || !(a > 0)) continue;

    const gap = e2.i - e1.i;
    if (gap < DB_MIN_GAP || gap > DB_MAX_GAP) continue;
    if (A - e2.i > NECK_RECENCY) continue;
    if (Math.abs(e1.price - e2.price) > DB_TOL_ATR * a) continue;

    const am = atr[mid.i];
    if (am == null || !(am > 0)) continue;
    const rise = bottom
      ? mid.price - Math.max(e1.price, e2.price)
      : Math.min(e1.price, e2.price) - mid.price;
    if (rise < DB_RISE_ATR * am) continue;

    // Price must have held the level between the two extremes: a close through
    // it means the shape was already broken and never was a double bottom.
    const guard = bottom ? Math.min(e1.price, e2.price) : Math.max(e1.price, e2.price);
    let breached = false;
    for (let i = e1.i; i <= e2.i && !breached; i++) {
      const ai = atr[i];
      if (ai == null) continue;
      breached = bottom
        ? bars[i].c < guard - BREAK_ATR * ai
        : bars[i].c > guard + BREAK_ATR * ai;
    }
    if (breached) continue;

    const id = bottom ? "double-bottom" : "double-top";
    const def = BY_ID.get(id);
    const neck = mid.price;
    out.push(
      finish(ctx, {
        id,
        def,
        startIdx: e1.i,
        endIdx: e2.i,
        shape: {
          kind: "neckline",
          lines: [{ m: 0, b: neck }],
          path: [
            [e1.i, e1.price],
            [mid.i, mid.price],
            [e2.i, e2.price],
          ],
          x0: e1.i,
          x1: null, // a neckline runs to the current bar: it is what price must cross
        },
        trigger: neck,
        triggerDown: null,
        invalidate: guard,
        height: Math.abs(neck - guard),
        apexIdx: null,
        touches: 3,
      })
    );
  }
  return out;
}

/* ---------- head and shoulders ---------- */

function headShoulders(ctx) {
  const { atr, A } = ctx;
  const out = [];
  for (let k = 0; k + 4 < ctx.zz.length; k++) {
    const E = ctx.zz.slice(k, k + 5);
    if (E.some((p) => p.provisional)) continue;
    const bear = E[0].type === "high"; // high, low, high, low, high
    if (E.some((p, i) => (i % 2 === 0) !== (p.type === (bear ? "high" : "low")))) continue;
    if (A - E[4].i > NECK_RECENCY) continue;

    const sgn = bear ? 1 : -1;
    const head = E[2].price;
    if (sgn * (head - E[0].price) <= 0 || sgn * (head - E[4].price) <= 0) continue;

    const avgTop = (E[0].price + E[4].price) / 2;
    const avgBot = (E[1].price + E[3].price) / 2;
    const tolOk = [E[0], E[4]].every(
      (p) => atr[p.i] > 0 && Math.abs(p.price - avgTop) <= HS_TOL_ATR * atr[p.i]
    );
    const botOk = [E[1], E[3]].every(
      (p) => atr[p.i] > 0 && Math.abs(p.price - avgBot) <= HS_TOL_ATR * atr[p.i]
    );
    if (!tolOk || !botOk) continue;
    if (!(atr[E[2].i] > 0) || sgn * (head - avgBot) < HS_HEAD_ATR * atr[E[2].i]) continue;

    const neck = fitLine([E[1], E[3]]);
    const height = sgn * (head - lineAt(neck, E[2].i));
    if (!(height > 0)) continue;
    if (Math.abs(lineAt(neck, E[4].i) - lineAt(neck, E[0].i)) > HS_NECK_TILT * height) continue;

    const id = bear ? "head-and-shoulders" : "inverse-head-and-shoulders";
    const def = BY_ID.get(id);
    out.push(
      finish(ctx, {
        id,
        def,
        startIdx: E[0].i,
        endIdx: E[4].i,
        shape: {
          kind: "neckline",
          lines: [neck],
          path: E.map((p) => [p.i, p.price]),
          x0: E[0].i,
          x1: null,
        },
        // The trigger tracks the sloping neckline, so it is evaluated per bar
        // rather than frozen: `neckLine` on the pattern is what resolvePattern
        // reads. `trigger` holds its value at the last extreme, for display.
        trigger: lineAt(neck, E[4].i),
        neckLine: neck,
        triggerDown: null,
        invalidate: head,
        height,
        apexIdx: null,
        touches: 5,
      })
    );
  }
  return out;
}

/* ---------- tier 2: candlesticks ---------- */

/**
 * Precedence within tier 2 follows the candlestick spec's §7.3: directional
 * beats neutral always (a doji is the most common candle in the catalogue and
 * would otherwise become wallpaper), then recency, then size — the three-bar
 * reading of the same bars is the more specific claim — then catalogue order.
 */
const CANDLE_RECENCY = 2;
/** Sessions a candle gets to trigger — classical practice waits for the next one. */
const CANDLE_TRIGGER = 3;
/** …and then to reach its measure-rule target. */
const CANDLE_TARGET = 10;

function bestCandle(ctx) {
  const { bars, atr, A } = ctx;
  const cands = [];
  for (let e = A - CANDLE_RECENCY + 1; e <= A; e++) {
    if (e < ctx.from) continue;
    let rank = 0;
    for (const m of candlesAt(bars, atr, e)) {
      cands.push({ ...m, rank: rank++ });
    }
  }
  if (!cands.length) return null;
  cands.sort(
    (a, b) =>
      (a.entry.bias === "neutral" ? 1 : 0) - (b.entry.bias === "neutral" ? 1 : 0) ||
      b.endIdx - a.endIdx ||
      b.entry.size - a.entry.size ||
      a.rank - b.rank
  );
  const m = cands[0];

  let hi = -Infinity;
  let lo = Infinity;
  for (let i = m.startIdx; i <= m.endIdx; i++) {
    hi = Math.max(hi, bars[i].h);
    lo = Math.min(lo, bars[i].l);
  }
  const bull = m.entry.bias === "bull";
  const neutral = m.entry.bias === "neutral";

  return finish(ctx, {
    id: m.entry.id,
    def: {
      id: m.entry.id,
      label: m.label,
      bias: m.entry.bias,
      kind: m.entry.kind,
      hitRate: neutral ? null : m.hitRate,
    },
    tier: 2,
    startIdx: m.startIdx,
    endIdx: m.endIdx,
    shape: { kind: "box", hi, lo, x0: m.startIdx, x1: m.endIdx },
    trigger: neutral ? null : bull ? hi : lo,
    triggerDown: null,
    invalidate: neutral ? null : bull ? lo : hi,
    height: hi - lo,
    apexIdx: null,
    touches: 0,
  });
}

/* ---------- tier 3: support and resistance ---------- */

function bestLevel(ctx) {
  const { bars, atr, A } = ctx;
  const found = levels(ctx.pivots, bars, atr, {
    anchor: A,
    tolAtr: SR_TOL_ATR,
    minTouches: SR_MIN_TOUCHES,
    nearAtr: SR_NEAR_ATR,
    recentBars: SR_RECENT_BARS,
  });
  if (!found.length) return null;
  const lv = found[0];
  const above = lv.price >= bars[A].c;
  const id = above ? "resistance" : "support";

  return finish(ctx, {
    id,
    def: {
      id,
      label: `${above ? "RESISTANCE" : "SUPPORT"} ×${lv.touches}`,
      bias: "neutral",
      kind: "level",
      hitRate: null,
    },
    tier: 3,
    startIdx: Math.max(ctx.from, lv.firstIdx),
    endIdx: A,
    shape: { kind: "level", level: lv.price, band: lv.band, x0: ctx.from, x1: null },
    // A level makes no forecast, so it has no zone and cannot fail — but it
    // can be broken, and watching price take it out is the whole reason it is
    // worth drawing when nothing else fits.
    trigger: above ? lv.price + lv.band : lv.price - lv.band,
    // A level's bias is neutral — it predicts nothing — but it is still broken
    // in a direction, and "neutral" alone cannot say which. Resistance gives
    // way upwards, support downwards.
    breakSign: above ? 1 : -1,
    triggerDown: null,
    invalidate: null,
    height: 0,
    apexIdx: null,
    touches: lv.touches,
    quality: lv.touches * 10,
  });
}

/* ---------- assembling a Pattern ---------- */

function finish(ctx, c) {
  const def = c.def;
  const tier = c.tier ?? 1;
  const span = c.endIdx - c.startIdx + 1;
  const p = {
    id: c.id,
    label: def.label,
    tier,
    bias: def.bias,
    kind: def.kind,
    state: "forming",
    startIdx: c.startIdx,
    endIdx: c.endIdx,
    shape: c.shape,
    trigger: c.trigger ?? null,
    triggerDown: c.triggerDown ?? null,
    invalidate: c.invalidate ?? null,
    neckLine: c.neckLine ?? null,
    upperAt: c.upperAt ?? null,
    lowerAt: c.lowerAt ?? null,
    height: c.height ?? 0,
    hitRate: def.hitRate ?? null,
    hitRateDown: def.hitRateDown ?? null,
    apexIdx: c.apexIdx ?? null,
    breakSign: c.breakSign ?? null,
    zoneNear: null,
    zoneFar: null,
    // Autochartist's construction: a forecast is time-boxed to the pattern's
    // own length. Levels make no forecast, so they never expire.
    // Two horizons, because a shape and a candle wait on different clocks.
    // A chart pattern is time-boxed to its own length, Autochartist's
    // construction. A candle gets the classical three sessions to trigger —
    // any longer and the label hangs around all hand — and then a swing's
    // worth of room to reach its target.
    triggerUntil:
      tier === 3 ? null : tier === 2 ? c.endIdx + CANDLE_TRIGGER : c.endIdx + span,
    zoneUntil:
      tier === 3
        ? null
        : tier === 2
          ? c.endIdx + CANDLE_TRIGGER + CANDLE_TARGET
          : c.endIdx + span,
    breakoutIdx: null,
    resolvedIdx: null,
    scanIdx: c.endIdx,
    quality: c.quality ?? c.touches * 10 + span,
  };
  if (def.bias !== "either") setZone(p);
  p.text = patternText(p);
  return p;
}

function setZone(p) {
  const rate = p.bias === "bear" && p.hitRateDown != null ? p.hitRateDown : p.hitRate;
  if (rate == null || !(p.height > 0) || p.trigger == null) return;
  const d = p.bias === "bull" ? 1 : -1;
  p.zoneNear = p.trigger + d * p.height * rate;
  p.zoneFar = p.trigger + d * p.height;
}

/* ---------- the state machine ---------- */

/**
 * Advance a pinned pattern through the bars revealed since it was last
 * resolved. Pure and idempotent: the same inputs give the same output, a
 * terminal pattern comes back unchanged, and a twenty-session jump (what PASS
 * does) resolves exactly as twenty single steps would.
 *
 * The per-bar order is pessimistic first, mirroring `stopFill()` in
 * sim-engine.js: on a bar that closes beyond both levels, assume the bad
 * outcome.
 */
export function resolvePattern(p, bars, throughIdx) {
  if (!p) return null;
  if (isTerminal(p)) return p;
  const T = Math.min(throughIdx, bars.length - 1);
  let i = (p.scanIdx ?? p.endIdx) + 1;
  if (i > T) return p;

  const s = { ...p, shape: { ...p.shape } };
  for (; i <= T; i++) {
    s.scanIdx = i;
    const c = bars[i].c;

    if (s.state === "forming") {
      const dir = breakDir(s, bars, i);
      if (dir) {
        breakout(s, i, dir);
        if (isTerminal(s)) break;
        continue;
      }
      // TrendSpider's discard rule: the first close that stops respecting the
      // shape, and is not a breakout through the trigger, ends it.
      if (abandonedAt(s, bars, i)) {
        s.state = "abandoned";
        s.resolvedIdx = i;
        break;
      }
      if (s.apexIdx != null && i >= s.apexIdx) {
        s.state = "abandoned";
        s.resolvedIdx = i;
        break;
      }
      if (s.triggerUntil != null && i > s.triggerUntil) {
        s.state = "expired";
        s.resolvedIdx = i;
        break;
      }
      continue;
    }

    // broken-out or throwback
    const d = sideOf(s) || 1;
    if (s.invalidate != null && d * (c - s.invalidate) < 0) {
      s.state = "failed";
      s.resolvedIdx = i;
      break;
    }
    if (s.zoneNear != null && d * (c - s.zoneNear) >= 0) {
      s.state = "confirmed";
      s.resolvedIdx = i;
      break;
    }
    // Throwbacks happen on 62-72% of breakouts. A learner who does not know
    // that reads every one of them as a failure, which is why this is a state
    // and not silence.
    const level = triggerAt(s, i);
    s.state = d * (c - level) > 0 ? "broken-out" : "throwback";
    if (s.zoneUntil != null && i > s.zoneUntil) {
      s.state = "expired";
      s.resolvedIdx = i;
      break;
    }
  }
  s.text = patternText(s);
  return s;
}

/**
 * Which way this pattern breaks: +1 up, -1 down, 0 for a pattern that makes no
 * directional claim at all (a doji, which has no trigger to break either way).
 */
function sideOf(p) {
  if (p.bias === "bull") return 1;
  if (p.bias === "bear") return -1;
  return p.breakSign ?? 0;
}

/** The trigger level at bar `i` — a sloping neckline moves, everything else does not. */
function triggerAt(p, i) {
  return p.neckLine ? lineAt(p.neckLine, i) : p.trigger;
}

/** +1 for an upside break, -1 for a downside one, 0 for neither. */
function breakDir(p, bars, i) {
  const c = bars[i].c;
  if (p.bias === "either") {
    if (p.trigger != null && c > p.trigger) return 1;
    if (p.triggerDown != null && c < p.triggerDown) return -1;
    return 0;
  }
  const level = triggerAt(p, i);
  if (level == null) return 0;
  const d = sideOf(p);
  if (!d) return 0;
  return d * (c - level) > 0 ? d : 0;
}

function breakout(p, i, dir) {
  p.state = "broken-out";
  p.breakoutIdx = i;
  if (p.bias === "either") {
    p.bias = dir > 0 ? "bull" : "bear";
    p.trigger = dir > 0 ? p.trigger : p.triggerDown;
    p.invalidate = dir > 0 ? p.lowerAt : p.upperAt;
    p.triggerDown = null;
  }
  // A level is broken or it is not; there is no target to reach afterwards.
  if (p.tier === 3) {
    p.resolvedIdx = i;
    return;
  }
  setZone(p);
  // A shape stops being drawn past the bar that broke it: after that, price is
  // outside it and extending the lines would claim it was still contained.
  if (p.shape.kind === "lines") p.shape = { ...p.shape, x1: i };
}

/** While forming: has price stopped respecting the shape? */
function abandonedAt(p, bars, i) {
  const c = bars[i].c;
  if (p.tier === 3) return false; // a level cannot be abandoned, only broken
  if (p.shape.kind === "lines" && p.upperAt != null) {
    const [upper, lower] = p.shape.lines;
    const a = atrGuess(p, bars, i);
    return c > lineAt(upper, i) + a || c < lineAt(lower, i) - a;
  }
  // Necklines and candle boxes have one boundary that is not the trigger: the
  // far side of the shape. A close through it says the structure is gone.
  if (p.invalidate == null) return false;
  const d = sideOf(p);
  if (!d) return false;
  return d * (c - p.invalidate) < 0;
}

/**
 * The break tolerance in price terms. `resolvePattern` is deliberately given
 * no ATR array — it must stay callable on nothing but the pattern and the bars
 * — so the tolerance is taken from the shape's own height, which is what ATR
 * was scaling in the first place.
 */
function atrGuess(p, bars, i) {
  return BREAK_ATR * Math.max(p.height * 0.25, bars[i].h - bars[i].l);
}
