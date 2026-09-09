// Synthetic OHLC series for the simulator's structure and pattern tests.
//
// A triangle you built has known pivots, so when a detector fails the failure
// localises to one clause instead of to "somewhere in AAPL". The builder is a
// small DSL — `.up(8, 3.2).down(5, 1.1).flat(4)` — because pasting real OHLC
// arrays into a test makes it impossible to see what the case is testing.
//
// Not a test file: `npm test` globs `tests/web/*.test.js`, so this is only ever
// imported.

const DEFAULT_WICK = 0.25; // wick length as a fraction of the bar's body move
const DEFAULT_VOL = 1_000_000;

/**
 * A price series under construction. Every segment method appends bars that
 * open at the previous close, so the series is continuous and gap-free unless
 * a test asks for a gap with `.bar()`.
 */
class Series {
  constructor(start, opts = {}) {
    this.price = start;
    this.wick = opts.wick ?? DEFAULT_WICK;
    this.noise = opts.noise ?? 0; // deterministic wobble, so pivots are findable
    this.seed = opts.seed ?? 1;
    this.rows = [];
  }

  /** Deterministic pseudo-random in [-1, 1] — no Math.random in a test. */
  _wobble() {
    this.seed = (this.seed * 1103515245 + 12345) % 2147483648;
    return (this.seed / 2147483648) * 2 - 1;
  }

  /** One bar, given explicitly. Prices are absolute, not deltas. */
  bar({ o, h, l, c, v = DEFAULT_VOL }) {
    this.rows.push({ o, h, l, c, v });
    this.price = c;
    return this;
  }

  /** `n` bars each closing `step` higher than they opened. */
  up(n, step, opts = {}) {
    return this._run(n, Math.abs(step), opts);
  }

  /** `n` bars each closing `step` lower. */
  down(n, step, opts = {}) {
    return this._run(n, -Math.abs(step), opts);
  }

  /** `n` bars that go nowhere but still have a range. */
  flat(n, range = 1, opts = {}) {
    for (let i = 0; i < n; i++) {
      const o = this.price;
      const c = o + (i % 2 ? -1 : 1) * range * 0.15;
      this.bar({ o, h: Math.max(o, c) + range * 0.5, l: Math.min(o, c) - range * 0.5, c, ...opts });
    }
    return this;
  }

  _run(n, step, opts = {}) {
    const wick = opts.wick ?? this.wick;
    for (let i = 0; i < n; i++) {
      const o = this.price;
      const c = o + step + (this.noise ? this._wobble() * this.noise : 0);
      // Asymmetric wicks: a rising bar reaches further up than a falling one
      // and vice versa. Without that the last bar of a rally and the first bar
      // of the pullback share a high exactly, and a tie is not a strict local
      // extreme — the turn would have no pivot at all.
      const w = Math.abs(step) * wick + 1e-6;
      const up = c >= o;
      this.bar({
        o,
        h: Math.max(o, c) + (up ? w : w * 0.5),
        l: Math.min(o, c) - (up ? w * 0.5 : w),
        c,
        ...opts,
      });
    }
    return this;
  }

  /**
   * A single swing high `step` above the current price and back — the smallest
   * unit a pivot test needs.
   */
  peak(up, down, step) {
    return this.up(up, step).down(down, step);
  }

  /** A single swing low. */
  trough(down, up, step) {
    return this.down(down, step).up(up, step);
  }

  /**
   * Walk the series through a list of turning points, so a test can state the
   * shape it wants rather than the bars that produce it:
   *
   *     .turns([{ gap: 6, price: 110, type: "high" }, { gap: 5, price: 102, type: "low" }])
   *
   * Each turn takes `gap` bars to reach `price`, and the turn bar's own high
   * (or low) lands EXACTLY on it, so a fitted trendline through the pivots is
   * the line the test asked for. Bodies stop `inset` short of the extreme and
   * every other bar wicks out only `eps`, which is what makes the turn a
   * strict local extreme and therefore a confirmed pivot.
   */
  turns(list, { inset = 0.35, eps = 0.06 } = {}) {
    for (const t of list) {
      const high = t.type === "high";
      const bodyTarget = high ? t.price - inset : t.price + inset;
      const from = this.price;
      const step = (bodyTarget - from) / t.gap;
      for (let k = 1; k <= t.gap; k++) {
        const o = this.price;
        const c = from + step * k;
        const last = k === t.gap;
        this.bar({
          o,
          h: last && high ? t.price : Math.max(o, c) + eps,
          l: last && !high ? t.price : Math.min(o, c) - eps,
          c,
        });
      }
    }
    return this;
  }

  /** Bars with ISO dates attached, in the shape the simulator uses. */
  build() {
    const start = Date.UTC(2020, 0, 6); // a Monday
    return this.rows.map((r, i) => ({
      d: new Date(start + i * 86400000).toISOString().slice(0, 10),
      o: round(r.o),
      h: round(r.h),
      l: round(r.l),
      c: round(r.c),
      v: r.v,
    }));
  }
}

const round = (v) => Math.round(v * 10000) / 10000;

/** Start a series at `start`. */
export function series(start = 100, opts = {}) {
  return new Series(start, opts);
}

/**
 * `n` bars of quiet chop before the interesting part, so ATR(14) and the
 * candle averages are warm and the trend gate sees "flat" rather than `null`.
 */
export function warmup(s, n = 40, range = 1) {
  return s.flat(n, range);
}

/** A flat ATR array of `bars.length`, for tests that want one number. */
export function flatAtr(bars, value) {
  return bars.map(() => value);
}
