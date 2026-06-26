// Pure price-sheet metrics — compute one instrument's row AS OF a chosen date
// from its daily bars. No DOM, no fetch; mirrors the definitions that used to
// live in scripts/site/build_price_sheet.py so the date picker can recompute
// everything client-side.
//
// bars: [[isoDate, close], ...] ascending by date.

const TRADING_DAYS = 252;

function stdPop(arr) {
  // population standard deviation (ddof = 0), matching numpy default.
  const n = arr.length;
  if (!n) return null;
  let mean = 0;
  for (const x of arr) mean += x;
  mean /= n;
  let s = 0;
  for (const x of arr) {
    const d = x - mean;
    s += d * d;
  }
  return Math.sqrt(s / n);
}

function rsiWilder(closes, period = 14) {
  // Wilder RSI via the same recurrence as pandas ewm(alpha=1/period,
  // adjust=False): seed the average with the first delta, then smooth.
  if (closes.length < period + 1) return null;
  const alpha = 1 / period;
  let avgGain = null;
  let avgLoss = null;
  for (let k = 1; k < closes.length; k++) {
    const d = closes[k] - closes[k - 1];
    const g = d > 0 ? d : 0;
    const l = d < 0 ? -d : 0;
    if (avgGain === null) {
      avgGain = g;
      avgLoss = l;
    } else {
      avgGain = (1 - alpha) * avgGain + alpha * g;
      avgLoss = (1 - alpha) * avgLoss + alpha * l;
    }
  }
  if (avgGain === null) return null;
  if (avgLoss === 0) return 100;
  return 100 - 100 / (1 + avgGain / avgLoss);
}

const EMPTY = {
  last: null, prev: null,
  d1: null, w1: null, m1: null, y1: null,
  rsi: null, px200: null, vol45: null, volr: null,
};

// Index of the last bar dated on/before `asOfMs` (ms epoch). -1 if none.
function indexAsOf(bars, asOfMs) {
  let i = -1;
  for (let k = 0; k < bars.length; k++) {
    if (Date.parse(bars[k][0]) <= asOfMs) i = k;
    else break;
  }
  return i;
}

export function rowAsOf(bars, asOfMs) {
  const i = indexAsOf(bars, asOfMs);
  if (i < 1) return { ...EMPTY }; // need at least a previous close

  const closes = new Array(i + 1);
  for (let k = 0; k <= i; k++) closes[k] = bars[k][1];
  const n = i + 1;

  const last = closes[i];
  const prev = closes[i - 1];

  const pctLag = (lag) => (n > lag ? (last / closes[i - lag] - 1) * 100 : null);

  let px200 = null;
  if (n >= 200) {
    let s = 0;
    for (let k = i - 199; k <= i; k++) s += closes[k];
    const sma = s / 200;
    px200 = sma ? last / sma : null;
  }

  const rets = new Array(i);
  for (let k = 1; k <= i; k++) rets[k - 1] = Math.log(closes[k] / closes[k - 1]);
  const volOf = (m) => {
    if (rets.length < m) return null;
    const s = stdPop(rets.slice(rets.length - m));
    return s == null ? null : s * Math.sqrt(TRADING_DAYS) * 100;
  };
  const vol45 = volOf(45);
  // vol1y: needs >=200 returns; uses up to the last 252 (matches the Python).
  const vol1y = rets.length >= 200 ? volOf(Math.min(TRADING_DAYS, rets.length)) : null;

  return {
    last,
    prev,
    d1: prev ? (last / prev - 1) * 100 : null,
    w1: pctLag(5),
    m1: pctLag(21),
    y1: pctLag(TRADING_DAYS),
    rsi: rsiWilder(closes),
    px200,
    vol45,
    volr: vol45 && vol1y ? vol45 / vol1y : null,
  };
}
