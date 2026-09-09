// Price structure for the swing-trading simulator: pivots, a ZigZag
// reduction, straight-line fits and clustered support/resistance levels.
//
// This is stage 1 of the chart-pattern pipeline (see
// docs/web_v2/chart_pattern_spec.md §4 and §6). Everything downstream — every
// triangle, wedge, flag, double bottom and head-and-shoulders — is built from
// the pivots this module finds, so its two constants (PIVOT_K, MIN_SWING_ATR)
// decide whether the feature finds three patterns or three hundred.
//
// Pure: no DOM, no fetch, no imports. Covered by tests/web/sim-structure.test.js.
//
// Two conventions carry through the whole pipeline:
//
//   * Every threshold that compares two PRICES is a multiple of ATR(14) at the
//     bar in question. One number then works on a $9 stock and a $900 one,
//     which is what lets a single set of constants serve a 500-name universe.
//   * A pivot needs `k` bars to its right before it can be confirmed, so the
//     last `k` bars can never hold one. That is not an edge case to engineer
//     around — it is the structural reason a pattern touching the right edge
//     is "forming" rather than finished.

/** Bars either side of a bar that make it a confirmed pivot. */
export const PIVOT_K = 2;

/** ZigZag noise filter: the smallest swing worth keeping, in ATR(14). */
export const MIN_SWING_ATR = 0.75;

/**
 * A pivot this close to a fitted line counts as touching it, in ATR(14).
 *
 * Calibrated down from 0.35. A trendline is fitted THROUGH the pivots and then
 * checked against those same pivots, which is close to circular, and the
 * detector tries ~80 candidate spans per deal — so a per-candidate test that is
 * merely plausible fires somewhere almost every time. 0.20 is what makes three
 * pivots landing on one line evidence rather than arithmetic.
 */
export const TOUCH_ATR = 0.2;

/** Float slack on every "within tolerance" comparison in this module. */
const EPS = 1e-9;

/* ---------- pivots ---------- */

/**
 * @typedef {Object} Pivot
 * @property {number} i             bar index
 * @property {"high"|"low"} type
 * @property {number} price         the high (or low) of that bar
 * @property {boolean} provisional  true when the bar is too close to `to` to
 *                                  have `k` bars on its right
 */

/**
 * Confirmed pivots in `[from, to]`, plus the two provisional ones at the right
 * edge, in index order.
 *
 * A confirmed pivot is a strict local extreme over `[i-k, i+k]` — strict on
 * both sides, so a tie makes neither bar a pivot. Only `i` in
 * `[from + k, to - k]` can be confirmed.
 *
 * The final `k` bars cannot be confirmed either way, so the extreme high and
 * the extreme low within `(to - k, to]` are emitted flagged `provisional`.
 * Callers may use those to shape a pattern that is still forming, but must
 * never count one as a touch — nothing has confirmed that it is a turn.
 */
export function pivotsOf(bars, from, to, k = PIVOT_K) {
  const out = [];
  if (!Array.isArray(bars) || k < 1) return out;
  const lo = Math.max(0, from);
  const hi = Math.min(bars.length - 1, to);

  for (let i = lo + k; i <= hi - k; i++) {
    let isHigh = true;
    let isLow = true;
    for (let j = i - k; j <= i + k && (isHigh || isLow); j++) {
      if (j === i) continue;
      if (bars[j].h >= bars[i].h) isHigh = false;
      if (bars[j].l <= bars[i].l) isLow = false;
    }
    if (isHigh) out.push({ i, type: "high", price: bars[i].h, provisional: false });
    if (isLow) out.push({ i, type: "low", price: bars[i].l, provisional: false });
  }

  // The right edge: one provisional high and one provisional low drawn from
  // the bars that cannot yet be confirmed.
  const edge = [];
  const tailFrom = Math.max(lo, hi - k + 1);
  if (tailFrom <= hi) {
    let hIdx = tailFrom;
    let lIdx = tailFrom;
    for (let i = tailFrom + 1; i <= hi; i++) {
      if (bars[i].h > bars[hIdx].h) hIdx = i;
      if (bars[i].l < bars[lIdx].l) lIdx = i;
    }
    edge.push({ i: hIdx, type: "high", price: bars[hIdx].h, provisional: true });
    edge.push({ i: lIdx, type: "low", price: bars[lIdx].l, provisional: true });
    edge.sort((a, b) => a.i - b.i || (a.type === "high" ? -1 : 1));
  }

  return out.concat(edge);
}

/**
 * Reduce pivots to a strictly alternating high/low/high/low sequence.
 *
 * Two rules, applied in index order: a pivot of the same type as the last one
 * kept replaces it when it is the more extreme of the two, and a pivot of the
 * opposite type is kept only if the swing to it clears `minSwing` ATRs. The
 * result is the skeleton every pattern in sim-patterns.js is fitted to.
 */
export function zigzag(pivots, bars, atrArr, minSwing = MIN_SWING_ATR) {
  const out = [];
  for (const p of pivots) {
    const last = out[out.length - 1];
    if (!last) {
      out.push(p);
      continue;
    }
    if (p.type === last.type) {
      const better = p.type === "high" ? p.price > last.price : p.price < last.price;
      if (better) out[out.length - 1] = p;
      continue;
    }
    const a = atrArr[p.i];
    if (a == null || !(a > 0)) continue;
    if (Math.abs(p.price - last.price) < minSwing * a) continue;
    out.push(p);
  }
  return out;
}

/* ---------- straight lines through pivots ---------- */

/** @typedef {{m:number, b:number}} Line  price = m * barIndex + b */

/**
 * Least-squares line through `{i, price}` points, in index space. Two points
 * give the exact line through them; one gives a horizontal line at its price;
 * none gives `null`.
 */
export function fitLine(points) {
  const n = points.length;
  if (!n) return null;
  if (n === 1) return { m: 0, b: points[0].price };
  let si = 0;
  let sp = 0;
  for (const p of points) {
    si += p.i;
    sp += p.price;
  }
  const mi = si / n;
  const mp = sp / n;
  let num = 0;
  let den = 0;
  for (const p of points) {
    const d = p.i - mi;
    num += d * (p.price - mp);
    den += d * d;
  }
  const m = den === 0 ? 0 : num / den;
  return { m, b: mp - m * mi };
}

/** The line's price at bar `i`. */
export function lineAt(line, i) {
  return line.m * i + line.b;
}

/**
 * How many of `pivots` sit within `tol` ATRs of the line. Provisional pivots
 * never count: an unconfirmed extreme is not evidence that a line was
 * respected, and letting it count would inflate every touch test at the right
 * edge — exactly where patterns are most tempting and least certain.
 */
export function countTouches(line, pivots, atrArr, tol = TOUCH_ATR) {
  let n = 0;
  for (const p of pivots) {
    if (p.provisional) continue;
    const a = atrArr[p.i];
    if (a == null || !(a > 0)) continue;
    // EPS keeps the boundary inclusive as specified: `tol * a` is computed
    // from floating-point prices, so an exactly-on-tolerance pivot would
    // otherwise fall on the wrong side of the comparison about half the time.
    if (Math.abs(p.price - lineAt(line, p.i)) <= tol * a + EPS) n++;
  }
  return n;
}

/* ---------- support and resistance ---------- */

/** Pivots within this many ATRs of each other collapse into one level. */
export const SR_TOL_ATR = 0.35;
/**
 * Three touches is where the spec starts, and on a wide detection window three
 * is still a coincidence: there are enough pivots in ninety sessions that some
 * three of them cluster near almost any price. Four is a level.
 */
export const SR_MIN_TOUCHES = 4;
/** The level has to be near enough to the current price to matter, in ATRs. */
export const SR_NEAR_ATR = 1.0;
/** A touch inside this many bars of the anchor counts one and a half. */
export const SR_RECENT_BARS = 10;

/**
 * @typedef {Object} Level
 * @property {number} price     touch-weighted mean of the cluster
 * @property {number} touches
 * @property {number} recent    touches inside SR_RECENT_BARS of the anchor
 * @property {number} score     touches + 0.5 * recent
 * @property {number} band      half-width of the level's zone, in price
 * @property {number} firstIdx
 * @property {number} lastIdx
 */
/**
 * Cluster pivots into horizontal support/resistance levels near the anchor's
 * close, best first.
 *
 * Unlike the geometric patterns, a level may be built from pivots that are off
 * the left of the visible chart. That is the one deliberate exception to the
 * "draw only what you can see" rule, and it is sound because a horizontal
 * level is fully specified by its price: the line is drawn edge to edge either
 * way, and a level that has been tested four times over six months is a better
 * level than one tested three times in the last fortnight, whether or not the
 * older touches fit on a phone screen.
 *
 * Returns `[]` when nothing clusters — which is what keeps "no pattern at all"
 * a real, common outcome rather than a bug.
 */
export function levels(pivots, bars, atrArr, opts = {}) {
  const anchor = opts.anchor ?? bars.length - 1;
  const a = atrArr[anchor];
  if (a == null || !(a > 0)) return [];

  const tolAtr = opts.tolAtr ?? SR_TOL_ATR;
  const minTouches = opts.minTouches ?? SR_MIN_TOUCHES;
  const nearAtr = opts.nearAtr ?? SR_NEAR_ATR;
  const recentBars = opts.recentBars ?? SR_RECENT_BARS;
  const tol = tolAtr * a;
  const close = bars[anchor].c;

  const pts = pivots.filter((p) => !p.provisional).sort((x, y) => x.price - y.price);

  // Greedy single pass over the price-sorted pivots: a pivot joins the open
  // cluster while it stays within `tol` of that cluster's running mean, and
  // starts a new one otherwise. This is the standard S/R clustering algorithm
  // and it is stable — the same pivots always give the same levels.
  const clusters = [];
  let cur = null;
  for (const p of pts) {
    if (cur && p.price - cur.sum / cur.n <= tol) {
      cur.sum += p.price;
      cur.n += 1;
      cur.items.push(p);
    } else {
      cur = { sum: p.price, n: 1, items: [p] };
      clusters.push(cur);
    }
  }

  const out = [];
  for (const c of clusters) {
    if (c.n < minTouches) continue;
    const price = c.sum / c.n;
    if (Math.abs(price - close) > nearAtr * a) continue;
    const recent = c.items.filter((p) => anchor - p.i <= recentBars).length;
    const idx = c.items.map((p) => p.i);
    out.push({
      price,
      touches: c.n,
      recent,
      score: c.n + 0.5 * recent,
      band: tol,
      firstIdx: Math.min(...idx),
      lastIdx: Math.max(...idx),
    });
  }

  // Deterministic: score, then more touches, then nearer the close.
  out.sort(
    (x, y) =>
      y.score - x.score ||
      y.touches - x.touches ||
      Math.abs(x.price - close) - Math.abs(y.price - close)
  );
  return out;
}
