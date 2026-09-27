// Fundamental grades for the scorecard: QUALITY and VALUE, each a percentile
// within the stock's GICS sector. Pure functions: no DOM, no fetch. Covered by
// tests/web/weekly-book.test.js.
//
// Spec: docs/web_v2/scorecard_strategy_spec.md §3.7. Three decisions shape it:
//
//   * **Within sector, cross-sectionally.** An absolute P/E screen just sorts
//     by sector — banks are always "cheap", software always "dear". Ranking a
//     bank against banks needs only today's snapshot, no history, which is
//     the only kind of fundamentals data there is (yfinance `.info` has none).
//   * **Yields, not multiples.** Value ranks E/P, EBITDA/EV and B/P, higher
//     better. A loss-maker's negative P/E is then naturally the WORST value
//     rather than a nonsense "cheapest", with no special case.
//   * **Fail open, per metric.** A missing field drops out of that name's
//     average; a name with fewer than MIN_METRICS readings gets no grade at
//     all rather than a grade built from one number. Banks carry no
//     debt-to-equity or EV/EBITDA in yfinance and are graded on the rest.

/** A grade needs at least this many metrics behind it. */
export const MIN_METRICS = 3;
/** A sector with fewer names than this is ranked against the whole universe. */
export const MIN_SECTOR = 5;

const num = (v) => {
  if (v == null || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
};
const cap = (x, lo, hi) => (x == null ? null : Math.max(lo, Math.min(hi, x)));
const inv = (x) => (x == null || x === 0 ? null : 1 / x);

/**
 * The metrics graded, each HIGHER = BETTER after its transform. Growth rates
 * are capped so one post-pandemic base effect cannot outrank everything; ROE
 * is capped because negative-equity balance sheets (buyback-funded) turn it
 * into a number with no meaning.
 */
export const QUALITY = Object.freeze([
  { key: "revenueGrowth", label: "revenue growth", get: (r) => cap(num(r.revenueGrowth), -1, 2) },
  { key: "earningsGrowth", label: "earnings growth", get: (r) => cap(num(r.earningsGrowth), -2, 3) },
  { key: "operatingMargins", label: "operating margin", get: (r) => num(r.operatingMargins) },
  { key: "returnOnAssets", label: "return on assets", get: (r) => num(r.returnOnAssets) },
  { key: "returnOnEquity", label: "return on equity", get: (r) => cap(num(r.returnOnEquity), -1, 1) },
  {
    key: "fcfMargin",
    label: "FCF margin",
    get: (r) => {
      const f = num(r.freeCashflow);
      const rev = num(r.totalRevenue);
      return f != null && rev > 0 ? f / rev : null;
    },
  },
  { key: "lowLeverage", label: "low debt/equity", get: (r) => (num(r.debtToEquity) == null ? null : -num(r.debtToEquity)) },
]);

export const VALUE = Object.freeze([
  { key: "earningsYield", label: "forward E/P", get: (r) => inv(num(r.forwardPE) ?? num(r.trailingPE)) },
  { key: "ebitdaYield", label: "EBITDA/EV", get: (r) => inv(num(r.enterpriseToEbitda)) },
  { key: "bookYield", label: "B/P", get: (r) => inv(num(r.priceToBook)) },
]);

/**
 * Percentile ranks (0..100, ties averaged) of `values` — `null`s are skipped
 * and come back null. The lowest reading is 0, the highest 100.
 */
export function percentiles(values) {
  const idx = values.map((v, i) => [v, i]).filter(([v]) => v != null && Number.isFinite(v));
  idx.sort((a, b) => a[0] - b[0]);
  const out = new Array(values.length).fill(null);
  const n = idx.length;
  if (n === 0) return out;
  if (n === 1) {
    out[idx[0][1]] = 50;
    return out;
  }
  let k = 0;
  while (k < n) {
    let j = k;
    while (j + 1 < n && idx[j + 1][0] === idx[k][0]) j++;
    const pct = (((k + j) / 2) / (n - 1)) * 100;
    for (let m = k; m <= j; m++) out[idx[m][1]] = pct;
    k = j + 1;
  }
  return out;
}

/**
 * Grade every name. `rows` is `{TICKER: {…raw .info fields}}`; `sectorOf` maps
 * a ticker to its GICS sector (the simulator universe's `s`, so the grouping
 * matches the sector ETFs the market block ranks).
 *
 * Returns `{TICKER: {quality, value, nQuality, nValue, detail}}` where
 * `detail` is `{metricKey: percentile}` for the card's evidence line.
 */
export function gradeFundamentals(rows, sectorOf) {
  const tickers = Object.keys(rows || {});
  const groups = new Map();
  for (const t of tickers) {
    const sec = sectorOf(t) || "—";
    if (!groups.has(sec)) groups.set(sec, []);
    groups.get(sec).push(t);
  }
  // Each name is ranked within its sector; a name whose sector is too small
  // to be a real field is ranked against the whole universe instead.
  const pctFor = new Map(); // metricKey -> Map(ticker -> pct)
  for (const m of [...QUALITY, ...VALUE]) {
    const map = new Map();
    const rankIn = (field, keep) => {
      const ps = percentiles(field.map((x) => m.get(rows[x])));
      field.forEach((x, i) => {
        if (ps[i] != null && keep(x)) map.set(x, ps[i]);
      });
    };
    const small = new Set();
    for (const g of groups.values()) {
      if (g.length >= MIN_SECTOR) rankIn(g, () => true);
      else g.forEach((x) => small.add(x));
    }
    if (small.size) rankIn(tickers, (x) => small.has(x));
    pctFor.set(m.key, map);
  }

  const out = {};
  for (const t of tickers) {
    const detail = {};
    const avg = (metrics) => {
      const got = [];
      for (const m of metrics) {
        const p = pctFor.get(m.key).get(t);
        if (p != null) {
          got.push(p);
          detail[m.key] = Math.round(p);
        }
      }
      return got;
    };
    const q = avg(QUALITY);
    const v = avg(VALUE);
    out[t] = {
      quality: q.length >= MIN_METRICS ? q.reduce((a, b) => a + b, 0) / q.length : null,
      value: v.length >= 2 ? v.reduce((a, b) => a + b, 0) / v.length : null,
      nQuality: q.length,
      nValue: v.length,
      detail,
    };
  }
  return out;
}
