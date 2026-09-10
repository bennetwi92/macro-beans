// Broad-market and sector context for the swing-trading simulator — pure
// functions, no DOM, no fetch, so every rule here is unit-tested under
// `node --test` (tests/web/sim-market.test.js).
//
// The question this module answers is the one a swing trader should ask before
// any other: is the tide going my way? A long taken into a market below its
// 50-day average is a different trade from the same chart in a bull tape, and
// the simulator was silent about it. This module supplies the missing half:
//
//   * the trend state of SPY / QQQ / IWM, daily AND weekly;
//   * where the stock's own sector ETF ranks against the other ten;
//   * the stock's 20-day relative strength against SPY;
//   * a MARKET TAILWINDS SCORE out of 35, side-aware, VIX-penalised.
//
// Two rules bind everything below:
//
// 1. **No look-ahead.** Every reading is taken as of a date, and a date only
//    ever resolves to the last market session ON OR BEFORE it (`asOf`). The
//    running week is closed with the day's own close rather than the week's
//    eventual one, which is what a live weekly chart shows and what a trader
//    could actually have seen. There is a mandatory test.
// 2. **Fail open.** Missing data is never a penalty. A gap in the feed, a
//    ticker with no sector, a date before the market history starts — each
//    marks its block `available:false`, and an unavailable block is EXCLUDED
//    from the composite rather than scored zero (see `compositePct`). A
//    simulator that punishes you for its own build failing teaches nothing.

import { ema, sma } from "./sim-indicators.js";

/* ---------- the scoring model ---------- */

// Market Tailwinds Score, out of 35: the trend of the broad market is worth
// more than the strength of the sector, and both are worth less than the chart
// itself — which is why the block is 35 and not 100.
export const TREND_PTS = { bull: 20, neutral: 10, bear: 0 };
export const SECTOR_PTS = { top: 15, mid: 8, bottom: 0 };
export const MARKET_MAX = TREND_PTS.bull + SECTOR_PTS.top; // 35

// Systemic risk is a haircut, not a factor: when the VIX is above this, every
// correlation goes to one and a clean sector read is worth less than it looks.
export const VIX_SPIKE = 30;
export const VIX_PENALTY = 5;

// Strict Mode refuses a trade below this share of the points on offer.
export const STRICT_MIN = 75;

// Ranks 1..3 of eleven sectors are the tailwind, 9..11 the headwind, and the
// middle five are neither. Held as a count, not a fraction, so a build that
// ships ten sector ETFs instead of eleven still bands them the same way.
export const TOP_N = 3;
export const BOTTOM_N = 3;

// The lookback the SCORE reads. Ranks over 1 and 5 days are published too —
// they are what tells you a leader is rolling over — but a swing trade holds
// for weeks, so the points ride on the 20-day rank.
export const SECTOR_LOOKBACKS = [1, 5, 20];
export const SCORE_LOOKBACK = 20;

// 20 sessions of relative strength: the same horizon as the scoring rank.
export const RS_LOOKBACK = 20;

// Weekly trend needs 50 completed weeks behind it; daily needs 50 sessions.
const EMA_P = 21;
const SMA_P = 50;

/** The three indices the environment strip reads, in display order. */
export const INDICES = ["SPY", "QQQ", "IWM"];
export const BENCHMARK = "SPY";

/* ---------- preparing the feed ---------- */

/**
 * Turn the raw `sim-market.json` into a lookup-ready market.
 *
 * The moving averages are computed ONCE here, not per render: the simulator
 * re-renders on every drag of the stop, and re-running a 1700-bar EMA three
 * times a frame is how a phone drops the gesture. After this, reading a trend
 * state at a date is a binary search plus an array index.
 *
 * Returns `null` for anything unusable, which the caller reads as "no market
 * context" and displays as such — see the fail-open rule at the top.
 */
export function prepareMarket(raw) {
  const dates = raw?.dates;
  const close = raw?.close;
  if (!Array.isArray(dates) || !dates.length || !close?.[BENCHMARK]) return null;
  const trend = {};
  for (const sym of INDICES) {
    if (Array.isArray(close[sym])) trend[sym] = trendSeries(dates, close[sym]);
  }
  return {
    dates,
    close,
    trend,
    // GICS sector name -> sector ETF, straight from the build. Sectors whose
    // ETF is missing from this build are dropped, so a ranking never contains
    // a hole.
    sectors: Object.fromEntries(
      Object.entries(raw.sectors || {}).filter(([, etf]) => Array.isArray(close[etf]))
    ),
    vix: Array.isArray(close.VIX) ? close.VIX : null,
    builtAt: raw.built_at || null,
  };
}

/**
 * Everything needed to state a trend at any bar, daily and weekly.
 *
 * Daily is the textbook pair. Weekly is the same pair on weekly closes, with
 * one wrinkle that matters: the CURRENT week has not closed. Its averages are
 * therefore built from the completed weeks plus today's close — a running
 * weekly bar, exactly what a broker platform draws — which is why the weekly
 * numbers are stored as the state at the end of the PREVIOUS week (`wEma`,
 * `wCum`) and finished off per bar in `trendAt`.
 */
function trendSeries(dates, closes) {
  const wIdx = new Array(closes.length).fill(0); // bar -> its week's ordinal
  const wClose = []; // last close of each week, in order
  let key = null;
  for (let i = 0; i < dates.length; i++) {
    const k = weekKey(dates[i]);
    if (k !== key) {
      key = k;
      wClose.push(closes[i]);
    } else {
      wClose[wClose.length - 1] = closes[i];
    }
    wIdx[i] = wClose.length - 1;
  }
  // Prefix sums of completed weekly closes: wCum[k] is the sum of weeks 0..k-1.
  const wCum = new Array(wClose.length + 1).fill(0);
  for (let k = 0; k < wClose.length; k++) wCum[k + 1] = wCum[k] + wClose[k];
  return {
    ema: ema(closes, EMA_P),
    sma: sma(closes, SMA_P),
    wIdx,
    wEma: ema(wClose, EMA_P),
    wCum,
  };
}

/** ISO-week bucket key. Thursday's week owns the year, per ISO 8601. */
function weekKey(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  const day = (d.getUTCDay() + 6) % 7; // Monday = 0
  d.setUTCDate(d.getUTCDate() - day + 3); // the week's Thursday
  return d.toISOString().slice(0, 10);
}

/* ---------- reading it, as of a date ---------- */

/**
 * The last market session on or before `iso`, or -1 if the history starts
 * after it. Binary search — this runs on every render.
 *
 * The `<=` is the whole no-look-ahead guarantee: a decision taken on a date
 * can only ever see sessions up to and including that date, and a market
 * holiday resolves BACKWARDS to the previous session, never forwards.
 */
export function asOf(dates, iso) {
  let lo = 0;
  let hi = dates.length - 1;
  let out = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] <= iso) {
      out = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return out;
}

/**
 * Trend state at bar `i`: `"bull"`, `"neutral"`, `"bear"` or `null`.
 *
 *   bull    price > 21EMA > 50SMA   — aligned, and in the right order
 *   bear    price < 50SMA           — below the line institutions defend
 *   neutral anything else           — including the ragged case where price is
 *                                     above both averages but they have crossed
 *
 * `tf` is `"d"` for daily or `"w"` for the running weekly bar.
 */
export function trendAt(t, closes, i, tf = "d") {
  if (!t || i < 0 || i >= closes.length) return null;
  const price = closes[i];
  // A `null` close is a leading gap in a series that listed after the window
  // started. It is NOT a reading, and must not fall through the comparisons
  // below as a quiet "neutral" — every comparison against null is false.
  if (price == null || !Number.isFinite(price)) return null;
  let e;
  let s;
  if (tf === "w") {
    const k = t.wIdx[i];
    const prevEma = k > 0 ? t.wEma[k - 1] : null;
    // The running week: last week's EMA advanced by one step onto today's
    // close, and the last 49 completed weeks plus today's close for the SMA.
    e = prevEma == null ? null : price * (2 / (EMA_P + 1)) + prevEma * (1 - 2 / (EMA_P + 1));
    s = k >= SMA_P - 1 ? (t.wCum[k] - t.wCum[k - (SMA_P - 1)] + price) / SMA_P : null;
  } else {
    e = t.ema[i];
    s = t.sma[i];
  }
  if (!Number.isFinite(e) || !Number.isFinite(s)) return null;
  if (price < s) return "bear";
  return price > e && e > s ? "bull" : "neutral";
}

/** Percent return of `closes` over `n` sessions ending at `i`, or null. */
export function pctOver(closes, i, n) {
  if (!closes || i < n || i >= closes.length) return null;
  const a = closes[i - n];
  const b = closes[i];
  if (!(a > 0) || !(b > 0)) return null;
  return (b / a - 1) * 100;
}

/**
 * The stock's relative strength against the benchmark over `n` sessions: how
 * much its RS line (stock ÷ benchmark) has risen, in percent.
 *
 *   RS = (stock_now / stock_then) / (bench_now / bench_then) - 1
 *
 * Positive means the stock outran the market over the window whatever the
 * market did — the number that separates "it went up" from "it led".
 */
export function relStrength(stockCloses, si, benchCloses, bi, n = RS_LOOKBACK) {
  const s = pctOver(stockCloses, si, n);
  const b = pctOver(benchCloses, bi, n);
  if (s == null || b == null) return null;
  return ((1 + s / 100) / (1 + b / 100) - 1) * 100;
}

/**
 * The sector ETFs ranked by return over `lookback`, best first:
 * `[{etf, name, ret, rank, band}]`, where `band` is top / mid / bottom.
 */
export function rankSectors(market, i, lookback = SCORE_LOOKBACK) {
  const rows = [];
  for (const [name, etf] of Object.entries(market.sectors)) {
    const ret = pctOver(market.close[etf], i, lookback);
    if (ret != null) rows.push({ etf, name, ret });
  }
  rows.sort((a, b) => b.ret - a.ret);
  return rows.map((r, k) => ({
    ...r,
    rank: k + 1,
    band: k < TOP_N ? "top" : k >= rows.length - BOTTOM_N ? "bottom" : "mid",
  }));
}

/* ---------- the score ---------- */

/**
 * Points for a `side`, out of `MARKET_MAX`.
 *
 * The score is the tailwind BEHIND THE TRADE, not a view on the market: a
 * bear tape is worth the full 20 to a short, and a bottom-ranked sector is
 * worth the full 15. Inverting it for the short side is the only way the gate
 * below can mean anything — a rule that only fires on longs is a rule you get
 * round by pressing the other button.
 *
 * The VIX haircut is NOT inverted. A volatility spike is a reason to size down
 * whichever way you are leaning, not a bonus for being short.
 */
export function scoreFor(status, side = "long") {
  if (!status?.available) {
    return { trend: 0, sector: 0, vix: 0, total: 0, max: MARKET_MAX, available: false };
  }
  const short = side === "short";
  const regime = status.indices[BENCHMARK]?.d ?? null;
  const trendKey = short ? flip(regime) : regime;
  const band = status.sector.band;
  const bandKey = short ? flipBand(band) : band;
  const trend = trendKey == null ? null : TREND_PTS[trendKey];
  const sector = bandKey == null ? null : SECTOR_PTS[bandKey];
  const vix = status.vix != null && status.vix > VIX_SPIKE ? -VIX_PENALTY : 0;
  // A block with no reading is dropped from BOTH sides of the fraction, so an
  // unranked sector costs the trade nothing and the percentage still means
  // "share of the points that were on offer".
  const max = (trend == null ? 0 : TREND_PTS.bull) + (sector == null ? 0 : SECTOR_PTS.top);
  const total = Math.max(0, (trend ?? 0) + (sector ?? 0) + vix);
  return { trend, sector, vix, total, max, available: max > 0 };
}

const flip = (t) => (t === "bull" ? "bear" : t === "bear" ? "bull" : t);
const flipBand = (b) => (b === "top" ? "bottom" : b === "bottom" ? "top" : b);

/**
 * The composite, as a percentage of the points that were actually on offer.
 *
 * SIM-104 ships one block — the market's 35 points. The signature takes a LIST
 * of blocks because the epic's other blocks (the setup itself, risk) land in
 * the same composite later, and because the rescale is the whole trick: an
 * unavailable block drops out of the numerator AND the denominator, so a
 * missing feed can never quietly become a failing grade.
 *
 * Returns `null` when nothing at all was scoreable — the caller must then let
 * the trade through (fail open), not block it.
 */
export function compositePct(blocks) {
  let got = 0;
  let max = 0;
  for (const b of blocks) {
    if (!b?.available || !(b.max > 0)) continue;
    got += b.total;
    max += b.max;
  }
  return max > 0 ? (got / max) * 100 : null;
}

/* ---------- the one call the page makes ---------- */

/**
 * Market status for one stock on one date — the whole feature in one object.
 *
 * This is the client-side twin of the story's
 * `GET /api/v1/simulator/market-status?ticker={symbol}`. The cockpit has no
 * app server of its own (pre-built JSON is the backend), so the "endpoint" is
 * a pure function over a file the nightly build already wrote; the response
 * shape is the endpoint's, and a real HTTP route could serve it unchanged.
 *
 * `stock` is `{closes, index}` — the stock's own closes and the bar being
 * decided on — and is optional: without it everything but relative strength
 * still reads.
 */
export function marketStatus(market, { sector, date, stock = null } = {}) {
  if (!market) return { available: false, reason: "no-data" };
  const i = asOf(market.dates, date);
  if (i < 0) return { available: false, reason: "before-history" };

  const indices = {};
  for (const sym of INDICES) {
    const t = market.trend[sym];
    const c = market.close[sym];
    indices[sym] = t
      ? { d: trendAt(t, c, i, "d"), w: trendAt(t, c, i, "w") }
      : { d: null, w: null };
  }

  // An unmapped ticker (a sector we do not carry an ETF for, or none at all)
  // falls back to SPY as its benchmark and says so with a marker. It scores no
  // sector points and, crucially, is not scored ZERO for them either.
  const etf = market.sectors[sector] || null;
  const ranks = {};
  for (const lb of SECTOR_LOOKBACKS) ranks[lb] = rankSectors(market, i, lb);
  const scored = ranks[SCORE_LOOKBACK] || [];
  const row = etf ? scored.find((r) => r.etf === etf) : null;

  const status = {
    available: true,
    date: market.dates[i],
    index: i,
    indices,
    regime: indices[BENCHMARK]?.d ?? null,
    sector: {
      name: sector || null,
      etf: etf || BENCHMARK,
      unmapped: !etf,
      rank: row?.rank ?? null,
      of: scored.length,
      band: row?.band ?? null,
      ret: row?.ret ?? null,
      // The short lookbacks are published for the reader, not the score: a
      // sector that is top-3 over 20 days and bottom-3 over 1 is rolling over.
      rank1: rankIn(ranks[1], etf),
      rank5: rankIn(ranks[5], etf),
    },
    rs:
      stock && market.close[BENCHMARK]
        ? relStrength(stock.closes, stock.index, market.close[BENCHMARK], i)
        : null,
    vix: market.vix ? market.vix[i] ?? null : null,
  };
  status.score = scoreFor(status, "long");
  status.shortScore = scoreFor(status, "short");
  return status;
}

const rankIn = (rows, etf) => (etf ? rows?.find((r) => r.etf === etf)?.rank ?? null : null);
