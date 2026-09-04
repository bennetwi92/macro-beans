// Technical indicators for the swing-trading simulator — pure functions, no
// DOM, no fetch, so they can be unit-tested under `node --test`.
//
// Every function takes a plain array and returns an array of the SAME length,
// with `null` in the leading positions where the indicator is not yet defined.
// That keeps indicator[i] aligned with bars[i] at the call site — the chart and
// the trade engine both index by bar, and an off-by-one there is invisible but
// wrong.
//
// Conventions are the textbook ones (what a broker platform draws by default):
// EMAs are seeded with the SMA of the first `period` values, RSI and ATR use
// Wilder smoothing, MACD is 12/26/9.

/** Simple moving average. */
export function sma(values, period) {
  const out = new Array(values.length).fill(null);
  if (period <= 0) return out;
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

/**
 * Exponential moving average, seeded with the SMA of the first `period`
 * defined values. Leading `null`s in the input (e.g. the MACD line before the
 * slow EMA exists) are skipped, so `ema(macdLine, 9)` gives the signal line.
 */
export function ema(values, period) {
  const out = new Array(values.length).fill(null);
  if (period <= 0) return out;
  const k = 2 / (period + 1);
  let seedSum = 0;
  let seen = 0;
  let prev = null;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null || !Number.isFinite(v)) continue;
    if (prev === null) {
      seedSum += v;
      seen += 1;
      if (seen === period) {
        prev = seedSum / period;
        out[i] = prev;
      }
      continue;
    }
    prev = v * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

/** MACD with the standard 12/26/9 parameters. */
export function macd(values, fast = 12, slow = 26, signal = 9) {
  const fastEma = ema(values, fast);
  const slowEma = ema(values, slow);
  const line = values.map((_, i) =>
    fastEma[i] == null || slowEma[i] == null ? null : fastEma[i] - slowEma[i]
  );
  const signalLine = ema(line, signal);
  const hist = line.map((v, i) =>
    v == null || signalLine[i] == null ? null : v - signalLine[i]
  );
  return { line, signal: signalLine, hist };
}

/**
 * Wilder's RSI (default 14). The first value is a simple average of the first
 * `period` changes; from there gains and losses are Wilder-smoothed.
 */
export function rsi(values, period = 14) {
  const out = new Array(values.length).fill(null);
  if (values.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = values[i] - values[i - 1];
    if (d >= 0) gain += d;
    else loss -= d;
  }
  gain /= period;
  loss /= period;
  out[period] = rsiFrom(gain, loss);
  for (let i = period + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    gain = (gain * (period - 1) + (d > 0 ? d : 0)) / period;
    loss = (loss * (period - 1) + (d < 0 ? -d : 0)) / period;
    out[i] = rsiFrom(gain, loss);
  }
  return out;
}

function rsiFrom(gain, loss) {
  if (loss === 0) return gain === 0 ? 50 : 100;
  return 100 - 100 / (1 + gain / loss);
}

/**
 * Wilder's ATR (default 14) over `bars` — objects with {h, l, c}. Used only to
 * size the simulator's default stop, so it never needs to be drawn.
 */
export function atr(bars, period = 14) {
  const out = new Array(bars.length).fill(null);
  if (bars.length <= period) return out;
  const tr = bars.map((b, i) => {
    if (i === 0) return b.h - b.l;
    const pc = bars[i - 1].c;
    return Math.max(b.h - b.l, Math.abs(b.h - pc), Math.abs(b.l - pc));
  });
  let acc = 0;
  for (let i = 1; i <= period; i++) acc += tr[i];
  let prev = acc / period;
  out[period] = prev;
  for (let i = period + 1; i < bars.length; i++) {
    prev = (prev * (period - 1) + tr[i]) / period;
    out[i] = prev;
  }
  return out;
}
