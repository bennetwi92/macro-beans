// Synthetic DAILY bars on a real weekday calendar, for the weekly strategy's
// tests (strategy.js, scorecard.js, construct.js). The weekly modules resample
// with sim-timeframe.js `toWeekly`, which buckets by ISO week from the dates,
// so the bars need genuine Monday–Friday dates, not an index.
//
// Not a test file: `npm test` globs `tests/web/*.test.js`.

/** Weekday ISO dates from `start` (a Monday), `n` of them. */
export function weekdays(n, start = "2015-01-05") {
  const out = [];
  const d = new Date(`${start}T00:00:00Z`);
  while (out.length < n) {
    const day = d.getUTCDay();
    if (day >= 1 && day <= 5) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

/**
 * Daily bars from a list of closes: each opens at the previous close, with a
 * high/low `range` fraction around the body.
 */
export function barsFromCloses(closes, { start = "2015-01-05", range = 0.01, v = 1_000_000 } = {}) {
  const dates = weekdays(closes.length, start);
  return closes.map((c, i) => {
    const o = i ? closes[i - 1] : c;
    return { d: dates[i], o, h: Math.max(o, c) * (1 + range), l: Math.min(o, c) * (1 - range), c, v };
  });
}

/** A deterministic random walk with drift — enough structure for setups to fire. */
export function walk(n, { start = 50, drift = 0.0004, vol = 0.015, seed = 11 } = {}) {
  let s = seed;
  const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const out = [];
  let p = start;
  for (let i = 0; i < n; i++) {
    // Slow regime cycle so the walk visits every stage.
    const cycle = Math.sin(i / 180) * 0.0012;
    p *= 1 + drift + cycle + (rnd() * 2 - 1) * vol;
    out.push(Math.max(1, p));
  }
  return out;
}

/** Closes that grow by `pct` per day. */
export const ramp = (n, start, pct) => Array.from({ length: n }, (_, i) => start * Math.pow(1 + pct, i));
