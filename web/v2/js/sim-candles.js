// Tier-2 candlestick patterns for the swing-trading simulator: the seventeen
// signed entries of the Finviz retail set, with TA-Lib's relative-threshold
// system and a trend gate TA-Lib deliberately leaves to its caller.
//
// Spec: docs/web_v2/candlestick_pattern_spec.md §4-§6. Selection, states and
// rendering come from the CHART pattern spec instead (chart_pattern_spec.md
// §8), which supersedes this module's own §7-§9: candles are consulted only
// when no chart pattern is found, so this file exports a catalogue and a
// matcher, and sim-patterns.js owns everything after that.
//
// Pure: no DOM, no fetch. Covered by tests/web/sim-candles.test.js.
//
// Two things are worth knowing before changing a rule here.
//
//   * Every notion of "long", "short" and "near" is a multiple of a TRAILING
//     average, never a fixed percentage, so one rule works on a $9 stock and a
//     $900 one. `avg()` has two behaviours and conflating them is the classic
//     way a home-grown detector goes wrong — see its comment.
//   * The trend gate is part of the definition, not a filter bolted on top.
//     TA-Lib's own source says three times over that it does not check trend.
//     A hammer with no prior downtrend is not a weak hammer; it is not a
//     hammer, because the shape means "rejection at the low of a move" and
//     there was no move to reject.

/* ---------- per-bar primitives ---------- */

const body = (b) => Math.abs(b.c - b.o);
const upper = (b) => b.h - Math.max(b.o, b.c);
const lower = (b) => Math.min(b.o, b.c) - b.l;
const hl = (b) => b.h - b.l;
const top = (b) => Math.max(b.o, b.c);
const base = (b) => Math.min(b.o, b.c);
const isUp = (b) => b.c >= b.o;
const isDn = (b) => b.c < b.o;

const RANGE = {
  body,
  hl,
  shadows: (b) => upper(b) + lower(b),
};

/**
 * TA-Lib's threshold settings, verbatim from `ta_global.c`. `range` picks the
 * primitive that is averaged, `n` the averaging period, `f` the multiplier.
 */
export const CANDLE = {
  bodyLong: { range: "body", n: 10, f: 1.0 },
  bodyVeryLong: { range: "body", n: 10, f: 3.0 },
  bodyShort: { range: "body", n: 10, f: 1.0 },
  bodyDoji: { range: "hl", n: 10, f: 0.1 },
  shadowLong: { range: "body", n: 0, f: 1.0 },
  shadowVeryLong: { range: "body", n: 0, f: 2.0 },
  shadowShort: { range: "shadows", n: 10, f: 1.0 },
  shadowVeryShort: { range: "hl", n: 10, f: 0.1 },
  near: { range: "hl", n: 5, f: 0.2 },
  far: { range: "hl", n: 5, f: 0.6 },
  equal: { range: "hl", n: 5, f: 0.05 },
};

/**
 * The threshold `kind` at bar `i`, or `null` when there is not enough history.
 *
 * `n === 0` compares against THIS bar: "a long shadow" means longer than this
 * candle's own body, not longer than usual. `n > 0` averages the `n` bars
 * STRICTLY BEFORE `i` — a bar is never part of its own average, which is what
 * TA-Lib does and what stops a big bar from raising the bar it must clear.
 *
 * Every rule that reads a `null` here fails closed: no pattern, never a throw
 * and never `null` silently read as zero.
 */
export function avg(kind, bars, i) {
  if (i < 0 || i >= bars.length) return null;
  const fn = RANGE[kind.range];
  if (kind.n === 0) return kind.f * fn(bars[i]);
  if (i - kind.n < 0) return null;
  let sum = 0;
  for (let j = i - kind.n; j < i; j++) sum += fn(bars[j]);
  return (kind.f * sum) / kind.n;
}

/* ---------- the trend gate ---------- */

/** Bars of prior move measured by the trend gate. */
export const TREND_N = 10;
/** How big that move must be to count as a trend, in ATR(14). */
export const TREND_ATR = 1.5;

/**
 * The trend over the run of bars ending immediately BEFORE `startIdx` —
 * "up", "down", "flat", or `null` when there is not enough history.
 *
 * Reading only up to `startIdx - 1` is the whole point of the signature: a
 * three-bar bullish pattern whose own candles rally hard must never be allowed
 * to count that rally as the prior downtrend it is supposed to be reversing.
 */
export function trendBefore(bars, atrArr, startIdx) {
  const j = startIdx - 1;
  if (j - TREND_N < 0) return null;
  const a = atrArr[j];
  if (a == null || !(a > 0)) return null;
  const move = (bars[j].c - bars[j - TREND_N].c) / a;
  if (move >= TREND_ATR) return "up";
  if (move <= -TREND_ATR) return "down";
  return "flat";
}

/** What `trendBefore` must return for a pattern of this kind and bias. */
function trendOk(entry, trend) {
  if (entry.kind === "indecision") return true;
  if (trend == null || trend === "flat") return false;
  const want =
    entry.kind === "reversal"
      ? entry.bias === "bull"
        ? "down"
        : "up"
      : entry.bias === "bull"
        ? "up"
        : "down";
  return trend === want;
}

/* ---------- the catalogue ---------- */

const PENETRATION_2BAR = 0.5;
const PENETRATION_3BAR = 0.3;

/**
 * How often a candle pattern reaches its measure-rule target once it has
 * broken out — Bulkowski, over 4.7M candle lines (research note §3.4). Only
 * three of these are published figures; the rest borrow `DEFAULT_HIT`, which
 * is an assumption the census must revisit rather than a measurement.
 */
const DEFAULT_HIT = 0.7;

/**
 * The catalogue, best first. The order IS the tie-break of last resort in
 * sim-patterns.js, so it follows Bulkowski's overall-performance ranking with
 * the low-information continuation and indecision candles last.
 */
export const CANDLES = [
  {
    id: "three-white-soldiers",
    label: "3 WHITE SOLDIERS",
    bias: "bull",
    kind: "reversal",
    size: 3,
    test: (b, i) => {
      const [b0, b1, b2] = [b[i], b[i - 1], b[i - 2]];
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      const svs1 = avg(CANDLE.shadowVeryShort, b, i - 1);
      const svs2 = avg(CANDLE.shadowVeryShort, b, i - 2);
      const near1 = avg(CANDLE.near, b, i - 1);
      const near2 = avg(CANDLE.near, b, i - 2);
      const far1 = avg(CANDLE.far, b, i - 1);
      const far2 = avg(CANDLE.far, b, i - 2);
      const short0 = avg(CANDLE.bodyShort, b, i);
      if ([svs0, svs1, svs2, near1, near2, far1, far2, short0].some((v) => v == null))
        return false;
      return (
        isUp(b0) &&
        isUp(b1) &&
        isUp(b2) &&
        upper(b2) < svs2 &&
        upper(b1) < svs1 &&
        upper(b0) < svs0 &&
        b0.c > b1.c &&
        b1.c > b2.c &&
        b1.o > b2.o &&
        b1.o <= b2.c + near2 &&
        b0.o > b1.o &&
        b0.o <= b1.c + near1 &&
        body(b1) > body(b2) - far2 &&
        body(b0) > body(b1) - far1 &&
        body(b0) > short0
      );
    },
  },
  {
    id: "three-black-crows",
    label: "3 BLACK CROWS",
    bias: "bear",
    kind: "reversal",
    size: 3,
    test: (b, i) => {
      const [b0, b1, b2] = [b[i], b[i - 1], b[i - 2]];
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      const svs1 = avg(CANDLE.shadowVeryShort, b, i - 1);
      const svs2 = avg(CANDLE.shadowVeryShort, b, i - 2);
      const near1 = avg(CANDLE.near, b, i - 1);
      const near2 = avg(CANDLE.near, b, i - 2);
      const far1 = avg(CANDLE.far, b, i - 1);
      const far2 = avg(CANDLE.far, b, i - 2);
      const short0 = avg(CANDLE.bodyShort, b, i);
      if ([svs0, svs1, svs2, near1, near2, far1, far2, short0].some((v) => v == null))
        return false;
      return (
        isDn(b0) &&
        isDn(b1) &&
        isDn(b2) &&
        lower(b2) < svs2 &&
        lower(b1) < svs1 &&
        lower(b0) < svs0 &&
        b0.c < b1.c &&
        b1.c < b2.c &&
        b1.o < b2.o &&
        b1.o >= b2.c - near2 &&
        b0.o < b1.o &&
        b0.o >= b1.c - near1 &&
        body(b1) > body(b2) - far2 &&
        body(b0) > body(b1) - far1 &&
        body(b0) > short0
      );
    },
  },
  {
    id: "morning-star",
    label: "MORNING STAR",
    bias: "bull",
    kind: "reversal",
    size: 3,
    // TA-Lib demands a strict body gap either side of the star. Daily US
    // equities gap far less than the rice market the rule came from, so the
    // gap is relaxed to `near` — the same relaxation applied to piercing and
    // the inverted hammer.
    test: (b, i) => {
      const [b0, b1, b2] = [b[i], b[i - 1], b[i - 2]];
      const long2 = avg(CANDLE.bodyLong, b, i - 2);
      const short1 = avg(CANDLE.bodyShort, b, i - 1);
      const short0 = avg(CANDLE.bodyShort, b, i);
      const near2 = avg(CANDLE.near, b, i - 2);
      if ([long2, short1, short0, near2].some((v) => v == null)) return false;
      return (
        isDn(b2) &&
        body(b2) > long2 &&
        body(b1) <= short1 &&
        top(b1) < base(b2) + near2 &&
        isUp(b0) &&
        body(b0) > short0 &&
        b0.c > b2.c + body(b2) * PENETRATION_3BAR
      );
    },
    labelOf: (b, i) =>
      body(b[i - 1]) <= (avg(CANDLE.bodyDoji, b, i - 1) ?? 0) ? "MORNING DOJI STAR" : "MORNING STAR",
  },
  {
    id: "evening-star",
    label: "EVENING STAR",
    bias: "bear",
    kind: "reversal",
    size: 3,
    test: (b, i) => {
      const [b0, b1, b2] = [b[i], b[i - 1], b[i - 2]];
      const long2 = avg(CANDLE.bodyLong, b, i - 2);
      const short1 = avg(CANDLE.bodyShort, b, i - 1);
      const short0 = avg(CANDLE.bodyShort, b, i);
      const near2 = avg(CANDLE.near, b, i - 2);
      if ([long2, short1, short0, near2].some((v) => v == null)) return false;
      return (
        isUp(b2) &&
        body(b2) > long2 &&
        body(b1) <= short1 &&
        base(b1) > top(b2) - near2 &&
        isDn(b0) &&
        body(b0) > short0 &&
        b0.c < b2.c - body(b2) * PENETRATION_3BAR
      );
    },
    labelOf: (b, i) =>
      body(b[i - 1]) <= (avg(CANDLE.bodyDoji, b, i - 1) ?? 0) ? "EVENING DOJI STAR" : "EVENING STAR",
  },
  {
    id: "piercing",
    label: "PIERCING LINE",
    bias: "bull",
    kind: "reversal",
    size: 2,
    // TA-Lib requires an open below the prior LOW. Relaxed to the prior close,
    // which is Nison's formulation and the one every retail source teaches.
    // `b0.c < b1.o` is what keeps piercing and engulfing mutually exclusive.
    test: (b, i) => {
      const [b0, b1] = [b[i], b[i - 1]];
      const long1 = avg(CANDLE.bodyLong, b, i - 1);
      const long0 = avg(CANDLE.bodyLong, b, i);
      if ([long1, long0].some((v) => v == null)) return false;
      return (
        isDn(b1) &&
        body(b1) > long1 &&
        isUp(b0) &&
        body(b0) > long0 &&
        b0.o < b1.c &&
        b0.c < b1.o &&
        b0.c > b1.c + body(b1) * PENETRATION_2BAR
      );
    },
  },
  {
    id: "dark-cloud",
    label: "DARK CLOUD",
    bias: "bear",
    kind: "reversal",
    size: 2,
    test: (b, i) => {
      const [b0, b1] = [b[i], b[i - 1]];
      const long1 = avg(CANDLE.bodyLong, b, i - 1);
      const long0 = avg(CANDLE.bodyLong, b, i);
      if ([long1, long0].some((v) => v == null)) return false;
      return (
        isUp(b1) &&
        body(b1) > long1 &&
        isDn(b0) &&
        body(b0) > long0 &&
        b0.o > b1.c &&
        b0.c > b1.o &&
        b0.c < b1.c - body(b1) * PENETRATION_2BAR
      );
    },
  },
  {
    id: "bull-engulfing",
    label: "BULL ENGULFING",
    bias: "bull",
    kind: "reversal",
    size: 2,
    hitRate: 0.67, // measured
    // TA-Lib's rule plus two size floors it omits: without them a speck
    // engulfing a smaller speck qualifies.
    test: (b, i) => {
      const [b0, b1] = [b[i], b[i - 1]];
      const short0 = avg(CANDLE.bodyShort, b, i);
      const doji1 = avg(CANDLE.bodyDoji, b, i - 1);
      if ([short0, doji1].some((v) => v == null)) return false;
      return (
        isUp(b0) &&
        isDn(b1) &&
        ((b0.c >= b1.o && b0.o < b1.c) || (b0.c > b1.o && b0.o <= b1.c)) &&
        !(b0.o === b1.c && b0.c === b1.o) &&
        body(b0) > short0 &&
        body(b1) > doji1
      );
    },
  },
  {
    id: "bear-engulfing",
    label: "BEAR ENGULFING",
    bias: "bear",
    kind: "reversal",
    size: 2,
    test: (b, i) => {
      const [b0, b1] = [b[i], b[i - 1]];
      const short0 = avg(CANDLE.bodyShort, b, i);
      const doji1 = avg(CANDLE.bodyDoji, b, i - 1);
      if ([short0, doji1].some((v) => v == null)) return false;
      return (
        isDn(b0) &&
        isUp(b1) &&
        ((b0.c <= b1.o && b0.o > b1.c) || (b0.c < b1.o && b0.o >= b1.c)) &&
        !(b0.o === b1.c && b0.c === b1.o) &&
        body(b0) > short0 &&
        body(b1) > doji1
      );
    },
  },
  {
    id: "hammer",
    label: "HAMMER",
    bias: "bull",
    kind: "reversal",
    size: 1,
    hitRate: 0.88, // measured
    test: (b, i) => {
      const b0 = b[i];
      const short0 = avg(CANDLE.bodyShort, b, i);
      const doji0 = avg(CANDLE.bodyDoji, b, i);
      const sl0 = avg(CANDLE.shadowLong, b, i);
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      const near1 = avg(CANDLE.near, b, i - 1);
      if ([short0, doji0, sl0, svs0, near1].some((v) => v == null)) return false;
      return (
        body(b0) < short0 &&
        body(b0) > doji0 &&
        lower(b0) > sl0 &&
        upper(b0) < svs0 &&
        base(b0) <= b[i - 1].l + near1
      );
    },
  },
  {
    id: "shooting-star",
    label: "SHOOTING STAR",
    bias: "bear",
    kind: "reversal",
    size: 1,
    hitRate: 0.84, // measured
    test: (b, i) => {
      const b0 = b[i];
      const short0 = avg(CANDLE.bodyShort, b, i);
      const doji0 = avg(CANDLE.bodyDoji, b, i);
      const sl0 = avg(CANDLE.shadowLong, b, i);
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      const near1 = avg(CANDLE.near, b, i - 1);
      if ([short0, doji0, sl0, svs0, near1].some((v) => v == null)) return false;
      return (
        body(b0) < short0 &&
        body(b0) > doji0 &&
        upper(b0) > sl0 &&
        lower(b0) < svs0 &&
        base(b0) >= top(b[i - 1]) - near1
      );
    },
  },
  {
    id: "inverted-hammer",
    label: "INV HAMMER",
    bias: "bull",
    kind: "reversal",
    size: 1,
    // TA-Lib requires a hard gap down from the prior body, which on daily US
    // equities makes the pattern invisible. The `near` test mirrors the
    // hammer's own proximity test.
    test: (b, i) => {
      const b0 = b[i];
      const short0 = avg(CANDLE.bodyShort, b, i);
      const doji0 = avg(CANDLE.bodyDoji, b, i);
      const sl0 = avg(CANDLE.shadowLong, b, i);
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      const near1 = avg(CANDLE.near, b, i - 1);
      if ([short0, doji0, sl0, svs0, near1].some((v) => v == null)) return false;
      return (
        body(b0) < short0 &&
        body(b0) > doji0 &&
        upper(b0) > sl0 &&
        lower(b0) < svs0 &&
        top(b0) <= base(b[i - 1]) + near1
      );
    },
  },
  {
    id: "hanging-man",
    label: "HANGING MAN",
    bias: "bear",
    kind: "reversal",
    size: 1,
    // The hammer's shape exactly; only the trend gate separates them.
    test: (b, i) => {
      const b0 = b[i];
      const short0 = avg(CANDLE.bodyShort, b, i);
      const doji0 = avg(CANDLE.bodyDoji, b, i);
      const sl0 = avg(CANDLE.shadowLong, b, i);
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      const near1 = avg(CANDLE.near, b, i - 1);
      if ([short0, doji0, sl0, svs0, near1].some((v) => v == null)) return false;
      return (
        body(b0) < short0 &&
        body(b0) > doji0 &&
        lower(b0) > sl0 &&
        upper(b0) < svs0 &&
        base(b0) >= b[i - 1].h - near1
      );
    },
  },
  {
    id: "bull-harami",
    label: "BULL HARAMI",
    bias: "bull",
    kind: "reversal",
    size: 2,
    test: (b, i) => {
      const [b0, b1] = [b[i], b[i - 1]];
      const long1 = avg(CANDLE.bodyLong, b, i - 1);
      const short0 = avg(CANDLE.bodyShort, b, i);
      if ([long1, short0].some((v) => v == null)) return false;
      return (
        isDn(b1) &&
        body(b1) > long1 &&
        body(b0) <= short0 &&
        top(b0) < top(b1) &&
        base(b0) > base(b1)
      );
    },
    labelOf: (b, i) =>
      body(b[i]) <= (avg(CANDLE.bodyDoji, b, i) ?? 0) ? "BULL HARAMI CROSS" : "BULL HARAMI",
  },
  {
    id: "bear-harami",
    label: "BEAR HARAMI",
    bias: "bear",
    kind: "reversal",
    size: 2,
    test: (b, i) => {
      const [b0, b1] = [b[i], b[i - 1]];
      const long1 = avg(CANDLE.bodyLong, b, i - 1);
      const short0 = avg(CANDLE.bodyShort, b, i);
      if ([long1, short0].some((v) => v == null)) return false;
      return (
        isUp(b1) &&
        body(b1) > long1 &&
        body(b0) <= short0 &&
        top(b0) < top(b1) &&
        base(b0) > base(b1)
      );
    },
    labelOf: (b, i) =>
      body(b[i]) <= (avg(CANDLE.bodyDoji, b, i) ?? 0) ? "BEAR HARAMI CROSS" : "BEAR HARAMI",
  },
  {
    id: "marubozu-bull",
    label: "BULL MARUBOZU",
    bias: "bull",
    kind: "continuation",
    size: 1,
    test: (b, i) => {
      const b0 = b[i];
      const long0 = avg(CANDLE.bodyLong, b, i);
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      if ([long0, svs0].some((v) => v == null)) return false;
      return isUp(b0) && body(b0) > long0 && upper(b0) < svs0 && lower(b0) < svs0;
    },
  },
  {
    id: "marubozu-bear",
    label: "BEAR MARUBOZU",
    bias: "bear",
    kind: "continuation",
    size: 1,
    test: (b, i) => {
      const b0 = b[i];
      const long0 = avg(CANDLE.bodyLong, b, i);
      const svs0 = avg(CANDLE.shadowVeryShort, b, i);
      if ([long0, svs0].some((v) => v == null)) return false;
      return isDn(b0) && body(b0) > long0 && upper(b0) < svs0 && lower(b0) < svs0;
    },
  },
  {
    id: "doji",
    label: "DOJI",
    bias: "neutral",
    kind: "indecision",
    size: 1,
    test: (b, i) => {
      const doji0 = avg(CANDLE.bodyDoji, b, i);
      if (doji0 == null) return false;
      return body(b[i]) <= doji0;
    },
    labelOf: (b, i) => {
      const b0 = b[i];
      const svs0 = avg(CANDLE.shadowVeryShort, b, i) ?? 0;
      if (lower(b0) > 2 * upper(b0) && upper(b0) < svs0) return "DRAGONFLY DOJI";
      if (upper(b0) > 2 * lower(b0) && lower(b0) < svs0) return "GRAVESTONE DOJI";
      return "DOJI";
    },
  },
];

export const CANDLE_IDS = CANDLES.map((c) => c.id);

/**
 * Every catalogue entry that matches with its last bar exactly at `e`, in
 * catalogue order (so the caller's tie-break of last resort is free).
 *
 * Returns `[]` — never a throw — when `e` is too early for the averages or the
 * trend gate. `detectPattern` in sim-patterns.js turns these into Patterns;
 * this function deliberately knows nothing about states or drawing.
 */
export function candlesAt(bars, atrArr, e) {
  const out = [];
  if (!Array.isArray(bars) || e < 0 || e >= bars.length) return out;
  for (const entry of CANDLES) {
    const startIdx = e - entry.size + 1;
    if (startIdx < 0) continue;
    let ok = false;
    try {
      ok = entry.test(bars, e);
    } catch {
      ok = false; // a malformed bar fails closed, like a null average
    }
    if (!ok) continue;
    if (!trendOk(entry, trendBefore(bars, atrArr, startIdx))) continue;
    out.push({
      entry,
      startIdx,
      endIdx: e,
      label: entry.labelOf ? entry.labelOf(bars, e) : entry.label,
      hitRate: entry.hitRate ?? DEFAULT_HIT,
    });
  }
  return out;
}
