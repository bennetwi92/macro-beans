// The scorecard: one card per stock per week, a graded block per style of
// analysis, a weighted headline, and the vetoes. Pure functions: no DOM, no
// fetch. Covered by tests/web/scorecard.test.js.
//
// Spec: docs/web_v2/scorecard_strategy_spec.md §3. strategy.js decides WHAT the
// strategy would do this week (which setup, BUY or WATCH, where the stop is);
// this module decides how GOOD that candidate is, and whether anything rules
// it out. The ranking is the scorecard's only job — it never invents a trade
// the rules did not produce.
//
// Four rules bind everything below:
//
// 1. **A score is for a SETUP.** A card grades a stock as a PULLBACK, a
//    BREAKOUT or a REVERSAL, never in the abstract: the same RSI is a virtue in
//    one and a warning in another, and each setup weights the blocks
//    differently (PROFILES).
// 2. **Fail open.** A block with no data — no fundamentals snapshot for a
//    historical week, no earnings report in the last quarter, no chart pattern
//    — is EXCLUDED from the headline, which rescales over what remains
//    (`compositePct` from sim-market.js). A missing feed must never read as a
//    bearish signal.
// 3. **No look-ahead.** Every block reads the week being decided and earlier.
//    Fundamentals are the sharp edge: a snapshot is only valid on or after the
//    day it was taken, so a historical card simply has no fundamental block.
// 4. **Weights are evidence, not taste.** PROFILES record where each weight
//    came from; the in-sample calibration (scripts/scorecard/backtest.mjs)
//    decides them and the out-of-sample half judges them. A block that did not
//    rank outcomes in-sample carries no weight, however good it sounds.

import { marketStatus, scoreFor, compositePct, relStrength, asOf as marketAsOf, BENCHMARK, STRICT_MIN } from "./sim-market.js";
import { detectPattern, resolvePattern } from "./sim-patterns.js";
import { setupsAt, planAt, analogueStats, slope30, RULES } from "./strategy.js";

export const BLOCKS = Object.freeze([
  "market",
  "stage",
  "rs",
  "structure",
  "pattern",
  "momentum",
  "analogue",
  "earnings",
  "fundamental",
]);

export const BLOCK_LABELS = Object.freeze({
  market: "MARKET & SECTOR",
  stage: "TREND / STAGE",
  rs: "REL. STRENGTH",
  structure: "STRUCTURE",
  pattern: "PATTERN",
  momentum: "MOMENTUM",
  analogue: "LIKE-WEEK",
  earnings: "EARNINGS",
  fundamental: "FUNDAMENTAL",
});

/**
 * Per-setup weights (they sum to 100 per setup) and gates.
 *
 * PROVENANCE — read this before changing a number. These are PRIORS, from
 * the spec's hypothesis table (§2.2) and the literature, and they are
 * deliberately NOT fitted. The backtest (docs/scorecard/weekly_strategy_backtest.md)
 * measured every block's within-week rank information: none is reliable
 * (|IC| < 0.05, and the sign flips between in- and out-of-sample years), and
 * weights fitted to the in-sample ICs turn negative out of sample. Fitting
 * them would be fitting noise. The universe cannot settle it either way: it is
 * today's constituents, and a survivor-only universe biases every
 * cross-sectional test against momentum and quality (the losers in it are, by
 * construction, the ones that recovered). The only clean evidence is forward
 * — the weekly ledger (data/scorecard/ledger/) records each week's cards as
 * they stood, and is what should move these numbers.
 *
 * Two changes ARE evidence-led: the chart-pattern block carries no weight
 * (weekly patterns are uncalibrated — the census puts tier 1 under its band —
 * and their IC was negative in both halves), and the fundamental block keeps a
 * fixed weight because it has no history at all.
 *
 * `minScore` is the headline a BUY must reach to be ranked as one.
 */
export const PROFILES = Object.freeze({
  PULLBACK: Object.freeze({
    weights: Object.freeze({ market: 20, stage: 15, rs: 15, structure: 15, pattern: 0, momentum: 10, analogue: 5, earnings: 15, fundamental: 5 }),
    minScore: 55,
    marketGate: false,
  }),
  BREAKOUT: Object.freeze({
    weights: Object.freeze({ market: 20, stage: 10, rs: 20, structure: 10, pattern: 0, momentum: 10, analogue: 5, earnings: 20, fundamental: 5 }),
    minScore: 55,
    marketGate: false,
  }),
  REVERSAL: Object.freeze({
    weights: Object.freeze({ market: 15, stage: 10, rs: 10, structure: 15, pattern: 0, momentum: 10, analogue: 5, earnings: 15, fundamental: 20 }),
    minScore: 55,
    marketGate: false,
  }),
});

/** Reward:risk below this is no trade at any score (spec §2.3). */
export const MIN_RR = 1.5;
/** No new entry with a report due within this many calendar days of the decision. */
export const EARNINGS_WINDOW_DAYS = 14;
/** A report older than this (calendar days) has drifted out: no earnings block. */
export const EARNINGS_DRIFT_DAYS = 91;
/** REVERSAL needs a business that survives: sector quality percentile floor. */
export const REVERSAL_QUALITY_MIN = 40;

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const round = (x, dp = 2) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10 ** dp) / 10 ** dp);

/** A–F from a 0..1 score. */
export function grade(score) {
  if (score == null) return "—";
  if (score >= 0.8) return "A";
  if (score >= 0.65) return "B";
  if (score >= 0.5) return "C";
  if (score >= 0.35) return "D";
  return "F";
}

const block = (key, available, score, text, raw = {}) => ({
  key,
  available: !!available && score != null && Number.isFinite(score),
  score: available && score != null && Number.isFinite(score) ? round(clamp01(score), 3) : null,
  grade: available ? grade(score) : "—",
  text,
  raw,
});

/* ---------- the blocks ---------- */

/**
 * Market & sector — sim-market.js's Market Tailwinds Score, unchanged, on the
 * weekly read: SPY's weekly trend (20), the stock's sector ETF rank over 13
 * weeks (15), VIX haircut. Long side: the book is long-only.
 */
export function marketBlock(ms) {
  if (!ms?.available) return block("market", false, null, "no market feed for this week");
  const sc = scoreFor(ms, "long");
  if (!sc.available) return block("market", false, null, "market feed incomplete");
  const reg = ms.regime ? ms.regime.toUpperCase() : "—";
  const sec = ms.sector.rank ? `${ms.sector.etf} ${ms.sector.rank}/${ms.sector.of}` : `${ms.sector.etf} unranked`;
  const vix = ms.vix != null ? ` · VIX ${ms.vix.toFixed(0)}` : "";
  return block("market", true, sc.total / sc.max, `${sc.total}/${sc.max} · SPY ${reg}(w) · ${sec}${vix}`, {
    total: sc.total,
    max: sc.max,
    regime: ms.regime,
    sectorRank: ms.sector.rank,
    sectorOf: ms.sector.of,
    etf: ms.sector.etf,
    vix: ms.vix,
  });
}

/**
 * Trend / stage — Weinstein. What each setup wants from the trend:
 *   PULLBACK  an established Stage 2 (not newborn, not ancient) with a rising
 *             30-week and the 10-week above it
 *   BREAKOUT  the earlier the better: a base (Stage 1, or a flat-line
 *             continuation base read as 3), or a young Stage 2
 *   REVERSAL  Stage 1 out of a real decline, the 30-week flattening
 */
export function stageBlock(s, w, setup) {
  const st = s.stage[w];
  if (st == null) return block("stage", false, null, "not enough history");
  const age = s.age[w];
  const sl = slope30(s, w) ?? 0;
  const aligned = s.sma10[w] != null && s.sma30[w] != null && s.sma10[w] > s.sma30[w];
  let score;
  if (setup === "PULLBACK") {
    const ageS = age < 6 ? 0.3 : age <= 52 ? 1 : Math.max(0.4, 1 - (age - 52) / 104);
    score = st === 2 ? 0.4 * ageS + 0.35 * clamp01(sl / 1.0) + 0.25 * (aligned ? 1 : 0.3) : 0;
  } else if (setup === "BREAKOUT") {
    // Stage 3 here is a flat-line continuation base breaking out (strategy.js
    // setupsAt): a base, like Stage 1, and scored like one.
    const base = st === 1 || st === 3 ? 0.85 : st === 2 ? (age < 13 ? 1 : age <= 52 ? 0.75 : 0.5) : 0;
    score = base * (0.7 + 0.3 * clamp01((sl + RULES.flatAtr) / 1.0));
  } else {
    score = st === 1 ? 0.6 + 0.4 * clamp01((sl + 1) / 1) : 0;
  }
  const dir = sl > RULES.flatAtr ? "rising" : sl < -RULES.flatAtr ? "falling" : "flat";
  const pos = s.sma30[w] != null ? ((s.closes[w] / s.sma30[w] - 1) * 100).toFixed(1) : "—";
  return block("stage", true, score, `STAGE ${st} · ${age} wk · 30wk ${dir} · ${pos}% vs 30wk`, {
    stage: st,
    age,
    slopeAtr: round(sl),
    aligned,
  });
}

/**
 * Relative strength — the "buy strong trends" pillar, and the best-documented
 * effect in this whole card (Jegadeesh & Titman; George & Hwang's 52-week-high
 * effect): the stock's 26-week return relative to SPY, plus how close it sits
 * to its own 52-week high. Read off DAILY closes as of the decision session,
 * so it agrees with the market strip to the day.
 */
export function rsBlock(s, w, market) {
  const di = s.bars[w].di;
  const bi = market ? marketAsOf(market.dates, s.bars[w].d) : -1;
  const rs26 = market && bi >= 0 ? relStrength(s.dailyCloses, di, market.close[BENCHMARK], bi, 130) : null;
  let hi52 = -Infinity;
  for (let k = Math.max(0, w - 51); k <= w; k++) hi52 = Math.max(hi52, s.bars[k].h);
  const offHigh = hi52 > 0 ? (s.closes[w] / hi52 - 1) * 100 : null;
  if (rs26 == null && offHigh == null) return block("rs", false, null, "no benchmark");
  // RS: −20% → 0, +20% → 1. Off-high: −30% → 0, at the high → 1.
  const a = rs26 == null ? null : clamp01((rs26 + 20) / 40);
  const b = offHigh == null ? null : clamp01((offHigh + 30) / 30);
  const score = a == null ? b : b == null ? a : 0.6 * a + 0.4 * b;
  const txt = `${rs26 == null ? "RS —" : `RS26w ${rs26 >= 0 ? "+" : ""}${rs26.toFixed(1)}%`} · ${offHigh == null ? "" : `${offHigh.toFixed(1)}% off 52wk high`}`;
  return block("rs", true, score, txt, { rs26: round(rs26), offHigh: round(offHigh) });
}

/**
 * Structure — the geometry of the trade: room to the nearest resistance per
 * unit of risk to the stop, and (for a PULLBACK) whether it is resting on a
 * tested level. "Buy low" made measurable.
 */
export function structureBlock(plan, setup) {
  if (!plan || plan.rr == null) return block("structure", false, null, "no stop distance");
  const rrS = clamp01((plan.rr - 1) / 2.5);
  let supS = 0;
  if (plan.support && plan.atr > 0) {
    const gap = (plan.entry - plan.support.price) / plan.atr;
    supS = gap <= 1.5 ? Math.min(1, plan.support.touches / 4) : 0;
  }
  const score = setup === "PULLBACK" ? 0.75 * rrS + 0.25 * supS : rrS;
  const res = plan.blueSky ? "no resistance in 2y" : `res ${((plan.target / plan.entry - 1) * 100).toFixed(1)}% above`;
  const sup = plan.support ? ` · supp ${((1 - plan.support.price / plan.entry) * 100).toFixed(1)}% below ×${plan.support.touches}` : "";
  return block("structure", true, score, `R:R ${plan.rr.toFixed(1)} · ${res}${sup}`, {
    rr: round(plan.rr),
    blueSky: plan.blueSky,
  });
}

/**
 * Chart pattern — tier 1 of the simulator's ladder only, on weekly bars. The
 * candlestick tier is left out: its trend gate counts bars and was calibrated
 * on daily ones (the weekly census fires it on 31% of weeks). No pattern is
 * the common case and is NOT a penalty — the block is simply absent.
 */
export function patternBlock(s, w) {
  const p0 = detectPattern(s.bars, s.atr, w, { tiers: [1], detectBars: 60, visibleFrom: Math.max(0, w - 34) });
  if (!p0) return block("pattern", false, null, "no chart pattern");
  const p = resolvePattern(p0, s.bars, w);
  const live = ["forming", "broken-out", "throwback"].includes(p.state);
  if (!live) return block("pattern", false, null, `${p.label} (${p.state})`);
  let score = 0.5;
  if (p.bias === "bull") score = 0.6 + 0.4 * (p.hitRate ?? 0.5);
  else if (p.bias === "bear") score = 0.1;
  return block("pattern", true, score, `${p.label} · ${p.state}`, { id: p.id, bias: p.bias, state: p.state });
}

/**
 * Momentum — the oscillators, read for the setup: a PULLBACK wants a weekly
 * RSI that has cooled into the 40s with the MACD histogram turning up; a
 * BREAKOUT wants RSI strength and a volume surge on the break; a REVERSAL
 * wants RSI back over 50 and a positive histogram.
 */
export function momentumBlock(s, w, setup) {
  const r = s.rsi[w];
  const h = s.macd.hist[w];
  const hp = s.macd.hist[w - 1];
  if (r == null || h == null) return block("momentum", false, null, "not enough history");
  const vx = s.vma10[w - 1] > 0 ? s.bars[w].v / s.vma10[w - 1] : null;
  const turning = hp != null && h > hp;
  let score;
  if (setup === "PULLBACK") {
    score = (clamp01(1 - Math.abs(r - 47) / 15) + (turning ? 1 : 0.3)) / 2;
  } else if (setup === "BREAKOUT") {
    const rS = r >= 55 && r <= 75 ? 1 : r >= 50 && r <= 80 ? 0.6 : 0.2;
    const vS = vx == null ? 0.5 : vx >= 1.5 ? 1 : vx >= 1.2 ? 0.6 : 0.3;
    score = (rS + vS + (s.macd.line[w] > 0 ? 1 : 0.3)) / 3;
  } else {
    score = ((r >= 50 && r <= 65 ? 1 : r > 65 ? 0.6 : 0.2) + (h > 0 ? 1 : 0.3)) / 2;
  }
  const txt = `RSI ${r.toFixed(0)} · MACD hist ${turning ? "rising" : "falling"}${vx != null ? ` · vol ×${vx.toFixed(1)}` : ""}`;
  return block("momentum", true, score, txt, { rsi: round(r, 1), turning, volX: round(vx) });
}

/**
 * Like-week analogues — this strategy's own completed trades on this name in
 * the same setup (strategy.js `analogueStats`). Scored RELATIVE to the
 * universe's expectancy for the setup: the question is whether this name
 * does this trade better than names in general, not whether the trade works
 * at all — that is what the backtest is for. Needs three trades to speak.
 */
export function analogueBlock(stats) {
  if (!stats || stats.n < 3) {
    const n = stats?.n ?? 0;
    return block("analogue", false, null, `${n} past ${n === 1 ? "trade" : "trades"} on this name — too few`, { n });
  }
  const prior = stats.prior ?? 0;
  const score = 0.5 + (stats.shrunkR - prior) / 0.8;
  const txt = `${stats.meanR >= 0 ? "+" : ""}${stats.meanR.toFixed(2)}R avg · ${(stats.win * 100).toFixed(0)}% win · n=${stats.n}` +
    (stats.edge != null ? ` · edge ${stats.edge >= 0 ? "+" : ""}${(stats.edge * 100).toFixed(1)}% vs drift` : "");
  return block("analogue", true, score, txt, {
    n: stats.n,
    meanR: round(stats.meanR),
    shrunkR: round(stats.shrunkR),
    win: round(stats.win),
    edge: round(stats.edge, 4),
  });
}

/**
 * Earnings — the news block. The one piece of news that is dated,
 * machine-readable and testable: the most recent EPS surprise, while its
 * drift lasts (post-earnings-announcement drift, ~a quarter). A report is
 * known only on a date STRICTLY after it (most land after the close).
 *
 * `reports` is `[{d, surprise}]` ascending (surprise in percent; may be null).
 */
export function earningsBlock(reports, decisionIso) {
  if (!Array.isArray(reports) || !reports.length) return block("earnings", false, null, "no earnings history");
  let last = null;
  for (const r of reports) {
    if (r.d < decisionIso && r.surprise != null && Number.isFinite(r.surprise)) last = r;
  }
  if (!last) return block("earnings", false, null, "no reported surprise yet");
  const age = daysBetween(last.d, decisionIso);
  if (age > EARNINGS_DRIFT_DAYS) return block("earnings", false, null, `last report ${last.d} — drift spent`);
  // −10% surprise → 0, 0 → 0.5, +10% → 1; tapering as the drift ages.
  const raw = clamp01(0.5 + last.surprise / 20);
  const score = 0.5 + (raw - 0.5) * (1 - age / (2 * EARNINGS_DRIFT_DAYS));
  return block("earnings", true, score, `surprise ${last.surprise >= 0 ? "+" : ""}${last.surprise.toFixed(1)}% · ${last.d} (${age}d ago)`, {
    surprise: round(last.surprise, 1),
    reported: last.d,
    ageDays: age,
  });
}

/** The next scheduled report STRICTLY after the decision, or null. */
export function nextEarnings(reports, decisionIso) {
  if (!Array.isArray(reports)) return null;
  for (const r of reports) if (r.d > decisionIso) return r.d;
  return null;
}

/**
 * Fundamental — quality and value, as percentiles within the stock's GICS
 * sector from the latest snapshot (fundamental-score.js grades them). Present
 * only on the live week, by construction: there is no history to read.
 * `fund` is `{quality, value, asOf, detail}` with percentiles 0..100.
 */
export function fundamentalBlock(fund, setup, decisionIso) {
  if (!fund || fund.quality == null) return block("fundamental", false, null, "no fundamentals snapshot for this week");
  if (fund.asOf && fund.asOf < decisionIso && daysBetween(fund.asOf, decisionIso) > 14) {
    return block("fundamental", false, null, `snapshot ${fund.asOf} is stale`);
  }
  if (fund.asOf && fund.asOf > addDays(decisionIso, 14)) {
    // A snapshot taken after the week being decided would be look-ahead.
    return block("fundamental", false, null, "no snapshot this early");
  }
  const q = fund.quality / 100;
  const v = fund.value == null ? null : fund.value / 100;
  const wq = setup === "REVERSAL" ? 0.8 : 0.7;
  const score = v == null ? q : wq * q + (1 - wq) * v;
  return block("fundamental", true, score, `quality ${ordinal(fund.quality)} · value ${fund.value == null ? "—" : ordinal(fund.value)} pct in sector`, {
    quality: round(fund.quality, 0),
    value: round(fund.value, 0),
  });
}

/** 1st, 2nd, 3rd, 4th … 11th, 12th, 13th … 21st. */
export function ordinal(x) {
  const n = Math.round(x);
  const t = n % 100;
  const suf = t >= 11 && t <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th";
  return `${n}${suf}`;
}

/* ---------- dates ---------- */

export function daysBetween(a, b) {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86400000);
}

export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/* ---------- the card ---------- */

/**
 * Score every setup week `w` presents and return the card for the best one:
 *
 *   {t, date, setup, status, why, total, blocks, vetoes, flags, plan,
 *    analogue, stage, alternatives}
 *
 * status: "BUY" (a ranked candidate), "WATCH" (forming, or held back — by an
 * earnings date, or a headline under the profile's minScore), "PASS" (a
 * setup the vetoes rule out), or null (no setup this week). A card with no
 * setup still carries the stage and the market read, because the BOOK needs
 * them for names it already holds.
 *
 * ctx: {t, s, w, market, events, priors, earnings, fundamentals}
 *   events       strategy.eventTable(s) — for the like-week block
 *   priors       strategy.universePriors(...) as of this week
 *   earnings     [{d, surprise}] ascending, or null
 *   fundamentals {quality, value, asOf} for this name, or null
 */
export function scoreCard(ctx) {
  const { s, w } = ctx;
  const date = s.bars[w].d;
  const ms = ctx.market
    ? marketStatus(ctx.market, {
        sector: ctx.sector,
        date,
        stock: { closes: s.dailyCloses, index: s.bars[w].di },
        tf: "w",
      })
    : null;
  const shared = {
    market: marketBlock(ms),
    rs: rsBlock(s, w, ctx.market),
    pattern: patternBlock(s, w),
    earnings: earningsBlock(ctx.earnings, date),
  };
  const next = nextEarnings(ctx.earnings, date);
  const base = {
    t: ctx.t,
    date,
    close: s.closes[w],
    stage: s.stage[w],
    stageAge: s.age[w],
    nextEarnings: next,
  };

  const found = setupsAt(s, w);
  if (!found.length) {
    return { ...base, setup: null, status: null, why: "no setup this week", total: null, blocks: shared, vetoes: [], flags: [], plan: null, alternatives: [] };
  }

  const plan = planAt(s, w);
  const cards = found.map((f) => cardFor(ctx, f, plan, shared, ms, date, next));
  const rank = { BUY: 3, WATCH: 2, PASS: 1 };
  cards.sort((a, b) => rank[b.status] - rank[a.status] || (b.total ?? -1) - (a.total ?? -1));
  const best = cards[0];
  return {
    ...base,
    ...best,
    plan,
    alternatives: cards.slice(1).map((c) => ({ setup: c.setup, status: c.status, total: c.total })),
  };
}

function cardFor(ctx, found, plan, shared, ms, date, next) {
  const { s, w } = ctx;
  const setup = found.setup;
  const prof = PROFILES[setup];
  const stats = ctx.events ? analogueStats(s, ctx.events, w, setup, ctx.priors?.[setup]) : null;
  const blocks = {
    market: shared.market,
    stage: stageBlock(s, w, setup),
    rs: shared.rs,
    structure: structureBlock(plan, setup),
    pattern: shared.pattern,
    momentum: momentumBlock(s, w, setup),
    analogue: analogueBlock(stats),
    earnings: shared.earnings,
    fundamental: fundamentalBlock(ctx.fundamentals, setup, date),
  };
  const total = headline(blocks, prof.weights);

  const vetoes = [];
  const flags = [];
  let status = found.status;
  let why = found.why;
  if (plan.rr != null && plan.rr < MIN_RR) vetoes.push(`R:R ${plan.rr.toFixed(1)} < ${MIN_RR} — resistance too close`);
  if (prof.marketGate && blocks.market.available && blocks.market.score * 100 < STRICT_MIN) {
    vetoes.push(`market tailwinds under ${STRICT_MIN}%`);
  }
  if (setup === "REVERSAL" && ctx.fundamentals?.quality != null && ctx.fundamentals.quality < REVERSAL_QUALITY_MIN) {
    vetoes.push(`quality ${ordinal(ctx.fundamentals.quality)} pct — a reversal needs a business that survives`);
  }
  if (setup === "REVERSAL" && ctx.fundamentals?.quality == null) flags.push("quality unverified");
  if (next && daysBetween(date, next) <= EARNINGS_WINDOW_DAYS) {
    flags.push(`earnings ${next}`);
    if (status === "BUY") {
      status = "WATCH";
      why = `earnings ${next} — enter after the report`;
    }
  }
  if (vetoes.length) status = "PASS";
  else if (status === "BUY" && total != null && total < prof.minScore) {
    status = "WATCH";
    why = `score ${total.toFixed(0)} under ${prof.minScore}`;
  }
  return { setup, status, why, total, blocks, vetoes, flags, analogue: stats, facts: found.facts };
}

/** The weighted headline over available blocks, 0..100 (null if none). */
export function headline(blocks, weights) {
  const parts = [];
  for (const k of BLOCKS) {
    const wt = weights[k] ?? 0;
    const b = blocks[k];
    if (!(wt > 0) || !b) continue;
    parts.push({ available: b.available, total: b.available ? wt * b.score : 0, max: wt });
  }
  const pct = compositePct(parts);
  return pct == null ? null : round(pct, 1);
}
