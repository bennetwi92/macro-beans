// The TAPE: what is the tide, and how much risk does it allow this week?
// Pure functions: no DOM, no fetch. Covered by tests/web/weekly-book.test.js.
//
// Spec: docs/web_v2/scorecard_strategy_spec.md §4.1 and §5. The first step of
// the weekly review, and the one input the portfolio construction takes from
// the market as a whole: a RISK BUDGET. A bad tape shrinks the book
// automatically — fewer new positions, less risk each, a lower cap on total
// open risk ("heat") — without anyone having to feel brave or scared.
//
// Three readings go in, all as of the decision week, all already published by
// the build:
//
//   regime   SPY's weekly trend (sim-market.js `trendAt`, "w"): bull / neutral / bear
//   breadth  the share of the universe in Weinstein Stage 2 — how many stocks
//            are actually advancing, which an index led by five names hides
//   vix      the volatility haircut, as in the market block
//
// Breadth is computed on TODAY's constituents, so historically it carries the
// same survivorship lean as everything else built on config/sp500.csv. It is
// read as a relative gauge (this week versus its own history), not a level.

import { weekKey } from "./sim-timeframe.js";
import { asOf, trendAt, rankSectors, VIX_SPIKE, BENCHMARK, INDICES } from "./sim-market.js";

/**
 * The three budgets. `riskPct` is the equity risked per NEW position (entry to
 * initial stop); `heatMax` caps the sum of open risk across the book;
 * `maxNew` caps new positions per week. The FULL budget's 1% per trade is the
 * classic small-account figure; eight concurrent 1% risks is a book that can
 * survive a correlated stop-out week.
 */
export const BUDGETS = Object.freeze({
  FULL: Object.freeze({ level: "FULL", riskPct: 1.0, heatMax: 8, maxNew: 4 }),
  HALF: Object.freeze({ level: "HALF", riskPct: 0.75, heatMax: 5, maxNew: 2 }),
  DEFENSIVE: Object.freeze({ level: "DEFENSIVE", riskPct: 0.5, heatMax: 2, maxNew: 1 }),
});

/**
 * Breadth thresholds, as a share of the universe in Stage 2. Set from the
 * breadth history 1995–2026 (docs/scorecard/weekly_strategy_backtest.md §5):
 * FULL needs breadth at or above its long-run median (44%), DEFENSIVE is its
 * bottom quintile (25%).
 */
export const BREADTH_FULL = 44;
export const BREADTH_DEFENSIVE = 25;

/**
 * Stage-2 and above-30-week shares per week across a set of prepared series
 * (strategy.js `prepareSeries`). Weeks are aligned by ISO week key, so a
 * holiday-shortened week still lines up across names.
 *
 * Returns `{dates, stage2, above30, n}` ascending — `dates` is each week's
 * last session date as the most names saw it.
 */
export function breadthSeries(seriesList, fromIso = null) {
  const acc = new Map(); // weekKey -> {d, n, st2, a30}
  for (const s of seriesList) {
    for (let w = 0; w < s.bars.length; w++) {
      const st = s.stage[w];
      if (st == null) continue;
      const d = s.bars[w].d;
      if (fromIso && d < fromIso) continue;
      const k = weekKey(d);
      let a = acc.get(k);
      if (!a) acc.set(k, (a = { d, n: 0, st2: 0, a30: 0 }));
      if (d > a.d) a.d = d;
      a.n++;
      if (st === 2) a.st2++;
      if (s.closes[w] > s.sma30[w]) a.a30++;
    }
  }
  const keys = [...acc.keys()].sort();
  const out = { dates: [], stage2: [], above30: [], n: [] };
  for (const k of keys) {
    const a = acc.get(k);
    // A week only a handful of names had reached is not a reading.
    if (a.n < 50) continue;
    out.dates.push(a.d);
    out.stage2.push(Math.round((a.st2 / a.n) * 1000) / 10);
    out.above30.push(Math.round((a.a30 / a.n) * 1000) / 10);
    out.n.push(a.n);
  }
  return out;
}

/** The breadth reading for the week containing `iso` (or the last before it). */
export function breadthAt(breadth, iso) {
  if (!breadth?.dates?.length) return null;
  const k = weekKey(iso);
  let i = -1;
  for (let j = breadth.dates.length - 1; j >= 0; j--) {
    if (weekKey(breadth.dates[j]) <= k) {
      i = j;
      break;
    }
  }
  if (i < 0) return null;
  return { date: breadth.dates[i], stage2: breadth.stage2[i], above30: breadth.above30[i], index: i };
}

/**
 * The budget a regime / breadth / VIX reading earns, with the reasons.
 *
 *   FULL       SPY weekly bull AND breadth ≥ BREADTH_FULL
 *   DEFENSIVE  SPY weekly bear OR breadth < BREADTH_DEFENSIVE
 *   HALF       anything else
 *   a VIX over VIX_SPIKE steps it down one level
 *
 * Fail open: with no regime AND no breadth there is nothing to be defensive
 * about, and the budget is HALF — the middle, not the maximum.
 */
export function budgetFor({ regime = null, stage2 = null, vix = null } = {}) {
  const why = [];
  let level;
  if (regime == null && stage2 == null) {
    level = "HALF";
    why.push("no market data this week, so we stay in the middle");
  } else if (regime === "bear" || (stage2 != null && stage2 < BREADTH_DEFENSIVE)) {
    level = "DEFENSIVE";
    if (regime === "bear") why.push("the S&P 500 is in a downtrend");
    if (stage2 != null && stage2 < BREADTH_DEFENSIVE) why.push(`only ${stage2.toFixed(0)}% of stocks are rising`);
  } else if (regime === "bull" && (stage2 == null || stage2 >= BREADTH_FULL)) {
    level = "FULL";
    why.push("the S&P 500 is in an uptrend");
    if (stage2 != null) why.push(`${stage2.toFixed(0)}% of stocks are rising`);
  } else {
    level = "HALF";
    if (regime) why.push(`the S&P 500 is ${regime === "bull" ? "in an uptrend" : regime === "bear" ? "in a downtrend" : "moving sideways"}`);
    if (stage2 != null) why.push(`${stage2.toFixed(0)}% of stocks are rising${regime === "bull" ? `, and a green light needs ${BREADTH_FULL}%` : ""}`);
  }
  if (vix != null && vix > VIX_SPIKE && level !== "DEFENSIVE") {
    level = level === "FULL" ? "HALF" : "DEFENSIVE";
    why.push(`the fear gauge (VIX) is high at ${vix.toFixed(0)}, so one step more careful`);
  }
  return { ...BUDGETS[level], why };
}

/**
 * The whole TAPE read for a decision date: index trends (daily and weekly),
 * all sectors ranked over 1 / 4 / 13 weeks, the VIX, breadth, and the budget.
 * `market` is sim-market.js `prepareMarket(...)`; `breadth` is
 * `breadthSeries(...)` as the build published it.
 */
export function tapeRead(market, breadth, iso) {
  if (!market) return { available: false, budget: budgetFor({}) };
  const i = asOf(market.dates, iso);
  if (i < 0) return { available: false, budget: budgetFor({}) };
  const indices = {};
  for (const sym of INDICES) {
    const t = market.trend[sym];
    indices[sym] = t ? { d: trendAt(t, market.close[sym], i, "d"), w: trendAt(t, market.close[sym], i, "w") } : { d: null, w: null };
  }
  const ranks = { 5: rankSectors(market, i, 5), 20: rankSectors(market, i, 20), 65: rankSectors(market, i, 65) };
  const sectors = ranks[65].map((r) => ({
    etf: r.etf,
    name: r.name,
    ret13: r.ret,
    rank13: r.rank,
    band: r.band,
    rank4: ranks[20].find((x) => x.etf === r.etf)?.rank ?? null,
    rank1: ranks[5].find((x) => x.etf === r.etf)?.rank ?? null,
  }));
  const vix = market.vix ? market.vix[i] ?? null : null;
  const b = breadthAt(breadth, iso);
  const regime = indices[BENCHMARK]?.w ?? null;
  return {
    available: true,
    date: market.dates[i],
    indices,
    sectors,
    vix,
    breadth: b,
    regime,
    budget: budgetFor({ regime, stage2: b?.stage2 ?? null, vix }),
  };
}
