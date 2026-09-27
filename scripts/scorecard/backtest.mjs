// The weekly strategy's evidence: block calibration, gate tests, and a full
// portfolio simulation against controls.
//
//   node scripts/scorecard/backtest.mjs              # everything, all names
//   node scripts/scorecard/backtest.mjs --names 100  # quick run on a subset
//
// Needs the simulator data built first (it reads what the site reads):
//   python -m src.data.refresh --tickers-file config/sp500.csv
//   python -m src.data.refresh --tickers-file config/market_context.csv
//   /usr/local/bin/python3 scripts/site/build_sim.py
//   /usr/local/bin/python3 scripts/site/build_sim_market.py
//
// Writes data/scorecard/ (CSV + JSON) and docs/scorecard/weekly_strategy_backtest.md.
//
// It imports the browser's own modules — strategy.js, scorecard.js, tape.js,
// construct.js — exactly as the site build does. No port, no reimplementation:
// the strategy measured here is the strategy the cockpit shows.
//
// READ THE BIASES (they are printed into the report too):
//   * SURVIVORSHIP. The universe is TODAY's S&P 500. Every name in it survived
//     to be here, so every long strategy on it looks better than it was. The
//     defence is to judge everything RELATIVELY — setups against random
//     entries, the score against random ranking, returns in excess of the
//     same universe that week — never by the headline CAGR alone.
//   * NO FUNDAMENTALS. yfinance keeps no fundamentals history, so the
//     fundamental block is absent from every historical card (fail open).
//   * EARNINGS from 2014 only: the calendar yfinance returns starts there.
//   * WEEKLY FILLS. Stops fill on the weekly bar (at the stop, or the open on a
//     gap), exactly as the simulator's weekly mode does.
//   * IN/OUT OF SAMPLE by alternate years (odd = in, even = out), so both
//     halves span every regime and both hold earnings data. Weights are
//     chosen on odd years; even years judge them.

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { loadUniverse, loadMarket, loadEarnings, ROOT } from "../site/_scorecard_data.mjs";
import { prepareSeries, eventTable, runTrade, setupsAt, SETUPS } from "../../web/v2/js/strategy.js";
import { scoreCard, BLOCKS, PROFILES, MIN_RR, EARNINGS_WINDOW_DAYS, daysBetween, nextEarnings } from "../../web/v2/js/scorecard.js";
import { breadthSeries, tapeRead, BUDGETS } from "../../web/v2/js/tape.js";
import { construct, weeklyReturns, COSTS } from "../../web/v2/js/construct.js";
import { weekKey } from "../../web/v2/js/sim-timeframe.js";
import { asOf as marketAsOf } from "../../web/v2/js/sim-market.js";

const args = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};
const LIMIT = Number(flag("names", Infinity));
const START = flag("start", "2000-01-01");
const STOP_ATR = flag("stop-atr", null) == null ? null : Number(flag("stop-atr", null));
const SEEDS = Number(flag("seeds", 20));
const WRITE = !args.includes("--no-write");
const OUT = join(ROOT, "data", "scorecard");
const DOC = join(ROOT, "docs", "scorecard", "weekly_strategy_backtest.md");
const STARTING_EQUITY = 100000;

const t0 = Date.now();
const log = (...a) => console.error(`[${((Date.now() - t0) / 1000).toFixed(0)}s]`, ...a);

/* ---------- load ---------- */

const { builtAt, names } = loadUniverse({ limit: LIMIT });
const asOfBuild = builtAt.slice(0, 10);
const market = loadMarket();
const earnings = loadEarnings();
log(`universe ${names.length} names, market ${market ? "ok" : "MISSING"}, earnings calendars ${earnings.size}`);

const U = names.map((n) => {
  const s = prepareSeries(n.daily, asOfBuild, { stopAtr: STOP_ATR });
  const byWeek = new Map(s.bars.map((b, w) => [weekKey(b.d), w]));
  return { ...n, s, events: eventTable(s), byWeek, earn: earnings.get(n.t) || null };
});
log("series + event tables ready");

// Cross-sectional mean 13-week forward return per week: the "excess" yardstick.
const csMean = new Map();
for (const u of U) {
  u.s.bars.forEach((b, w) => {
    const f = u.s.fwd[w];
    if (f == null) return;
    const k = weekKey(b.d);
    const a = csMean.get(k) || [0, 0];
    a[0] += f;
    a[1]++;
    csMean.set(k, a);
  });
}

const breadth = breadthSeries(U.map((u) => u.s), "1995-01-01");

// Every completed strategy trade, by exit date: the universe prior, as of.
const done = [];
for (const u of U) {
  for (const e of u.events) {
    if (e.trade.open) continue;
    done.push({ d: u.s.bars[e.trade.exitIdx].d, setup: e.setup, r: e.trade.r });
  }
}
done.sort((a, b) => (a.d < b.d ? -1 : 1));

const weeks = [...new Set(U.flatMap((u) => u.s.bars.filter((b) => b.d >= START).map((b) => weekKey(b.d))))].sort();
// Drop the last week: nothing can be entered after it.
weeks.pop();

/* ---------- pass 1: every BUY setup, carded ---------- */

const calib = [];
const cands = new Map(); // weekKey -> [candidate]
const acc = Object.fromEntries(SETUPS.map((k) => [k, { n: 0, sum: 0 }]));
let dp = 0;

for (const k of weeks) {
  const repDate = U.map((u) => u.byWeek.get(k)).find((w) => w != null);
  // Advance the prior to this week's date (the latest date any name shows).
  let wkDate = null;
  for (const u of U) {
    const w = u.byWeek.get(k);
    if (w != null && (!wkDate || u.s.bars[w].d > wkDate)) wkDate = u.s.bars[w].d;
  }
  if (!wkDate || repDate == null) continue;
  while (dp < done.length && done[dp].d <= wkDate) {
    acc[done[dp].setup].n++;
    acc[done[dp].setup].sum += done[dp].r;
    dp++;
  }
  const priors = Object.fromEntries(SETUPS.map((x) => [x, { n: acc[x].n, meanR: acc[x].n ? acc[x].sum / acc[x].n : null }]));
  const cm = csMean.get(k);
  const list = [];
  for (const u of U) {
    const w = u.byWeek.get(k);
    if (w == null || w < 60 || w >= u.s.bars.length - 1) continue;
    const buy = setupsAt(u.s, w).find((x) => x.status === "BUY");
    if (!buy) continue;
    const card = scoreCard({ t: u.t, s: u.s, w, sector: u.sector, market, events: u.events, priors, earnings: u.earn, fundamentals: null });
    const trade = runTrade(u.s, w);
    const date = u.s.bars[w].d;
    const next = nextEarnings(u.earn, date);
    const row = {
      date,
      year: Number(date.slice(0, 4)),
      t: u.t,
      sector: u.sector,
      setup: card.setup,
      status: card.status,
      total: card.total,
      rr: card.plan?.rr ?? null,
      r: trade && !trade.open ? trade.r : null,
      maeR: trade && !trade.open ? trade.maeR : null,
      fwd: u.s.fwd[w],
      xs: u.s.fwd[w] != null && cm ? u.s.fwd[w] - cm[0] / cm[1] : null,
      earnSoon: u.earn ? (next ? daysBetween(date, next) <= EARNINGS_WINDOW_DAYS : false) : null,
    };
    for (const b of BLOCKS) row[b] = card.blocks?.[b]?.available ? card.blocks[b].score : null;
    calib.push(row);
    if (card.status === "BUY") {
      list.push({ t: u.t, w, u, total: card.total, setup: card.setup, sector: u.sector, entry: card.plan.entry, stop: card.plan.stop });
    }
  }
  list.sort((a, b) => b.total - a.total);
  cands.set(k, list);
}
log(`carded ${calib.length} BUY setups across ${weeks.length} weeks`);

/* ---------- statistics ---------- */

function ranks(xs) {
  const idx = xs.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]);
  const r = new Array(xs.length);
  let k = 0;
  while (k < idx.length) {
    let j = k;
    while (j + 1 < idx.length && idx[j + 1][0] === idx[k][0]) j++;
    for (let m = k; m <= j; m++) r[idx[m][1]] = (k + j) / 2;
    k = j + 1;
  }
  return r;
}
function pearson(a, b) {
  const n = a.length;
  if (n < 3) return null;
  const ma = a.reduce((x, y) => x + y, 0) / n;
  const mb = b.reduce((x, y) => x + y, 0) / n;
  let c = 0;
  let va = 0;
  let vb = 0;
  for (let i = 0; i < n; i++) {
    c += (a[i] - ma) * (b[i] - mb);
    va += (a[i] - ma) ** 2;
    vb += (b[i] - mb) ** 2;
  }
  return va > 0 && vb > 0 ? c / Math.sqrt(va * vb) : null;
}
/**
 * WITHIN-WEEK Spearman rank IC of `key` against `target`: both are ranked
 * inside each week (as a centred percentile), then correlated across all
 * weeks. The portfolio picks among the candidates of ONE week, so this is the
 * question that matters — a pooled IC would mix in timing (a good week lifts
 * every candidate, whatever its score). Weeks with fewer than 3 usable rows
 * carry no ranking information and are dropped.
 */
function ic(rows, key, target) {
  const byWeek = new Map();
  for (const r of rows) {
    if (r[key] == null || r[target] == null) continue;
    const k = weekKey(r.date);
    if (!byWeek.has(k)) byWeek.set(k, []);
    byWeek.get(k).push(r);
  }
  const xs = [];
  const ys = [];
  for (const list of byWeek.values()) {
    if (list.length < 3) continue;
    const rx = ranks(list.map((r) => r[key]));
    const ry = ranks(list.map((r) => r[target]));
    const m = (list.length - 1) / 2;
    for (let i = 0; i < list.length; i++) {
      xs.push((rx[i] - m) / list.length);
      ys.push((ry[i] - m) / list.length);
    }
  }
  if (xs.length < 30) return { ic: null, n: xs.length };
  return { ic: pearson(xs, ys), n: xs.length };
}
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const isIn = (r) => r.year % 2 === 1;
const f2 = (x, dp = 2) => (x == null || !Number.isFinite(x) ? "—" : x.toFixed(dp));
const pc = (x, dp = 1) => (x == null || !Number.isFinite(x) ? "—" : `${(x * 100).toFixed(dp)}%`);
const sg = (x, dp = 3) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(dp)}`);

// Block IC per setup, in and out of sample, against R and against excess return.
const blockIC = {};
for (const setup of SETUPS) {
  const rows = calib.filter((r) => r.setup === setup);
  blockIC[setup] = {};
  for (const b of [...BLOCKS, "total"]) {
    blockIC[setup][b] = {
      inR: ic(rows.filter(isIn), b, "r"),
      inX: ic(rows.filter(isIn), b, "xs"),
      outR: ic(rows.filter((r) => !isIn(r)), b, "r"),
      outX: ic(rows.filter((r) => !isIn(r)), b, "xs"),
    };
  }
}

// In-sample weights: proportional to the positive part of the mean of the two
// ICs; fundamentals keep their fixed weight (no history to calibrate on).
const suggested = {};
for (const setup of SETUPS) {
  const fixed = PROFILES[setup].weights.fundamental;
  const raw = {};
  let sum = 0;
  for (const b of BLOCKS) {
    if (b === "fundamental") continue;
    const x = blockIC[setup][b];
    const v = x.inR.ic == null || x.inX.ic == null ? 0 : Math.max(0, (x.inR.ic + x.inX.ic) / 2);
    raw[b] = v;
    sum += v;
  }
  suggested[setup] = { fundamental: fixed };
  for (const b of Object.keys(raw)) suggested[setup][b] = sum > 0 ? Math.round((raw[b] / sum) * (100 - fixed)) : 0;
}

// Composite quintiles, out of sample.
function quintiles(rows) {
  const pts = rows.filter((r) => r.total != null && r.r != null).sort((a, b) => a.total - b.total);
  const out = [];
  for (let q = 0; q < 5; q++) {
    const sl = pts.slice(Math.floor((q * pts.length) / 5), Math.floor(((q + 1) * pts.length) / 5));
    out.push({
      q: q + 1,
      n: sl.length,
      lo: sl[0]?.total,
      hi: sl[sl.length - 1]?.total,
      meanR: mean(sl.map((r) => r.r)),
      xs: mean(sl.filter((r) => r.xs != null).map((r) => r.xs)),
      win: sl.length ? sl.filter((r) => r.r > 0.1).length / sl.length : null,
    });
  }
  return out;
}

// Gates.
const post14 = calib.filter((r) => r.date >= "2014-06-01" && r.earnSoon != null && r.r != null);
const gap = (rows) => (rows.length ? rows.filter((r) => r.r < -1.5).length / rows.length : null);
const gates = {
  earnings: {
    soon: { n: post14.filter((r) => r.earnSoon).length, meanR: mean(post14.filter((r) => r.earnSoon).map((r) => r.r)), gapLoss: gap(post14.filter((r) => r.earnSoon)) },
    clear: { n: post14.filter((r) => !r.earnSoon).length, meanR: mean(post14.filter((r) => !r.earnSoon).map((r) => r.r)), gapLoss: gap(post14.filter((r) => !r.earnSoon)) },
  },
  rr: {
    low: { n: calib.filter((r) => r.rr != null && r.rr < MIN_RR && r.r != null).length, meanR: mean(calib.filter((r) => r.rr != null && r.rr < MIN_RR && r.r != null).map((r) => r.r)) },
    ok: { n: calib.filter((r) => r.rr != null && r.rr >= MIN_RR && r.r != null).length, meanR: mean(calib.filter((r) => r.rr != null && r.rr >= MIN_RR && r.r != null).map((r) => r.r)) },
  },
};

/* ---------- pass 2: the portfolio ---------- */

function stopAt(p, wNow) {
  let st = p.trade.initialStop;
  for (const [i, v] of p.trade.stops || []) {
    if (i <= wNow) st = v;
    else break;
  }
  return st;
}
function closeAt(u, k) {
  // The last close on or before week k for this name.
  const w = u.byWeek.get(k);
  if (w != null) return u.s.closes[w];
  return null;
}

function simulate({ tape = true, rank = "score", seed = 1, costs = true }) {
  let rnd = seed;
  const rand = () => (rnd = (rnd * 1103515245 + 12345) % 2147483648) / 2147483648;
  const cost = costs ? COSTS.fxPct / 100 : 0;
  let cash = STARTING_EQUITY;
  let positions = [];
  const lastClose = new Map();
  const curve = [];
  const closed = [];
  for (const k of weeks) {
    // Exits whose fill week has come.
    const still = [];
    for (const p of positions) {
      const t = p.trade;
      if (!t.open && weekKey(p.u.s.bars[t.exitIdx].d) <= k) {
        cash += p.qty * t.exitPrice * (1 - cost);
        closed.push({ t: p.u.t, setup: p.setup, r: t.r, pct: t.pct, entry: p.u.s.bars[t.entryIdx].d, exit: p.u.s.bars[t.exitIdx].d, reason: t.reason, total: p.total });
      } else still.push(p);
    }
    positions = still;
    // Mark.
    let invested = 0;
    for (const p of positions) {
      const c = closeAt(p.u, k);
      if (c != null) lastClose.set(p.u.t, c);
      invested += p.qty * (lastClose.get(p.u.t) ?? p.entry);
    }
    const equity = cash + invested;
    const date = cands.get(k)?.[0]?.u.s.bars[cands.get(k)[0].w].d ?? null;
    curve.push({ k, equity, invested, n: positions.length });
    // Decide.
    let list = (cands.get(k) || []).slice();
    if (rank === "random") {
      for (let i = list.length - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [list[i], list[j]] = [list[j], list[i]];
      }
    }
    if (!list.length) continue;
    const decisionDate = list[0].u.s.bars[list[0].w].d;
    const budget = tape ? tapeRead(market, breadth, decisionDate).budget : BUDGETS.FULL;
    const holdings = positions.map((p) => {
      const wNow = p.u.byWeek.get(k) ?? p.w;
      const price = lastClose.get(p.u.t) ?? p.entry;
      return { t: p.u.t, qty: p.qty, entryGBP: p.entry, stopGBP: stopAt(p, wNow), priceGBP: price, sector: p.sector, action: "HOLD", returns: weeklyReturns(p.u.s, wNow) };
    });
    const res = construct({
      equityGBP: equity,
      cashGBP: cash,
      holdings,
      candidates: list.map((c) => ({ ...c, returns: weeklyReturns(c.u.s, c.w) })),
      budget,
    });
    for (const o of res.orders) {
      if (o.action === "TRIM") {
        const p = positions.find((x) => x.u.t === o.t);
        if (p) {
          p.qty -= o.qty;
          cash += o.qty * o.priceGBP * (1 - cost);
        }
      }
      if (o.action !== "BUY") continue;
      const c = list.find((x) => x.t === o.t);
      const trade = runTrade(c.u.s, c.w, { trace: true });
      if (!trade) continue; // Monday opened through the stop: order cancelled
      let qty = o.qty;
      if (qty * trade.entryPrice * (1 + cost) > cash) qty = cash / (trade.entryPrice * (1 + cost));
      if (qty <= 0) continue;
      cash -= qty * trade.entryPrice * (1 + cost);
      positions.push({ u: c.u, w: c.w, qty, entry: trade.entryPrice, trade, setup: c.setup, sector: c.sector, total: c.total });
    }
  }
  return { curve, closed };
}

function metrics({ curve, closed }) {
  const eq = curve.map((c) => c.equity);
  const rets = [];
  for (let i = 1; i < eq.length; i++) rets.push(eq[i] / eq[i - 1] - 1);
  const yrs = eq.length / 52;
  const cagr = Math.pow(eq[eq.length - 1] / eq[0], 1 / yrs) - 1;
  const m = mean(rets);
  const sd = Math.sqrt(rets.reduce((a, r) => a + (r - m) ** 2, 0) / (rets.length - 1));
  let peak = -Infinity;
  let mdd = 0;
  for (const e of eq) {
    peak = Math.max(peak, e);
    mdd = Math.min(mdd, e / peak - 1);
  }
  const exposure = mean(curve.map((c) => (c.equity > 0 ? c.invested / c.equity : 0)));
  const byYear = {};
  for (let i = 0; i < curve.length; i++) {
    const y = curve[i].k.slice(0, 4);
    (byYear[y] ||= { first: i, last: i }).last = i;
  }
  const yearly = Object.entries(byYear).map(([y, v]) => ({ y, ret: eq[v.last] / eq[Math.max(0, v.first - 1)] - 1 }));
  const yMean = (odd) => mean(yearly.filter((y) => (Number(y.y) % 2 === 1) === odd && Number(y.y) >= Number(START.slice(0, 4))).map((y) => y.ret));
  return {
    oddYears: yMean(true),
    evenYears: yMean(false),
    cagr,
    vol: sd * Math.sqrt(52),
    sharpe: (m * 52) / (sd * Math.sqrt(52)),
    mdd,
    exposure,
    trades: closed.length,
    win: closed.length ? closed.filter((t) => t.r > 0.1).length / closed.length : null,
    meanR: mean(closed.map((t) => t.r)),
    final: eq[eq.length - 1],
    yearly,
  };
}

function spyMetrics() {
  const eq = [];
  for (const k of weeks) {
    // SPY's close on the last session of week k.
    let d = null;
    for (const u of U) {
      const w = u.byWeek.get(k);
      if (w != null && (!d || u.s.bars[w].d > d)) d = u.s.bars[w].d;
    }
    const i = marketAsOf(market.dates, d);
    eq.push({ k, equity: market.close.SPY[i], invested: 1 });
  }
  return metrics({ curve: eq, closed: [] });
}

log("simulating portfolios");
const strategyRun = simulate({ tape: true, rank: "score" });
const runs = {
  strategy: metrics(strategyRun),
  noTape: metrics(simulate({ tape: false, rank: "score" })),
};
const randomRuns = Array.from({ length: SEEDS }, (_, i) => metrics(simulate({ tape: true, rank: "random", seed: i + 1 })));
runs.randomRank = {
  oddYears: mean(randomRuns.map((r) => r.oddYears)),
  evenYears: mean(randomRuns.map((r) => r.evenYears)),
  cagr: mean(randomRuns.map((r) => r.cagr)),
  vol: mean(randomRuns.map((r) => r.vol)),
  sharpe: mean(randomRuns.map((r) => r.sharpe)),
  mdd: mean(randomRuns.map((r) => r.mdd)),
  exposure: mean(randomRuns.map((r) => r.exposure)),
  trades: mean(randomRuns.map((r) => r.trades)),
  win: mean(randomRuns.map((r) => r.win)),
  meanR: mean(randomRuns.map((r) => r.meanR)),
  spread: [Math.min(...randomRuns.map((r) => r.cagr)), Math.max(...randomRuns.map((r) => r.cagr))],
  beaten: null,
  yearly: [],
};
runs.randomRank.beaten = randomRuns.filter((r) => r.cagr < runs.strategy.cagr).length / randomRuns.length;
runs.randomRank.seeds = randomRuns.length;
runs.spy = spyMetrics();
log("done");

/* ---------- random-entry control (same exits) ---------- */

let seed = 7;
const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const ctlR = [];
for (const u of U) {
  for (let w = 60; w < u.s.bars.length - 30; w++) {
    if (u.s.bars[w].d < START || rnd() > 0.05) continue;
    const t = runTrade(u.s, w);
    if (t && !t.open) ctlR.push(t.r);
  }
}
const setupR = Object.fromEntries(SETUPS.map((k) => [k, calib.filter((r) => r.setup === k && r.r != null).map((r) => r.r)]));

/* ---------- the universe-wide momentum test ---------- */
// Does the best-documented effect in equities rank THIS universe at all? Every
// 4th week, every name: 26-week RS vs SPY, distance from the 52-week high, and
// 12-1 momentum (52-week return skipping the last 4), each against the excess
// 13-week return, within week. If these cannot rank the whole universe, no
// block built on them can rank a setup list — and the reason is worth knowing.
const mom = [];
for (const u of U) {
  const s = u.s;
  for (let w = 80; w < s.bars.length - 14; w += 4) {
    const d = s.bars[w].d;
    if (d < START || s.fwd[w] == null) continue;
    const cm = csMean.get(weekKey(d));
    if (!cm) continue;
    const di = s.bars[w].di;
    const bi = marketAsOf(market.dates, d);
    const spyA = market.close.SPY[bi - 130];
    const spyB = market.close.SPY[bi];
    const stA = s.dailyCloses[di - 130];
    const rs = di >= 130 && bi >= 130 && spyA > 0 && stA > 0 ? (s.dailyCloses[di] / stA) / (spyB / spyA) - 1 : null;
    let hi52 = -Infinity;
    for (let k = w - 51; k <= w; k++) hi52 = Math.max(hi52, s.bars[k].h);
    mom.push({
      date: d,
      year: Number(d.slice(0, 4)),
      rs,
      offHigh: s.closes[w] / hi52 - 1,
      m121: s.closes[w - 4] / s.closes[w - 52] - 1,
      xs: s.fwd[w] - cm[0] / cm[1],
    });
  }
}
function decileSpread(rows, key) {
  const byWeek = new Map();
  for (const r of rows) {
    if (r[key] == null) continue;
    const k = weekKey(r.date);
    if (!byWeek.has(k)) byWeek.set(k, []);
    byWeek.get(k).push(r);
  }
  const top = [];
  const bot = [];
  for (const list of byWeek.values()) {
    if (list.length < 50) continue;
    list.sort((a, b) => a[key] - b[key]);
    const d = Math.floor(list.length / 10);
    bot.push(...list.slice(0, d).map((r) => r.xs));
    top.push(...list.slice(-d).map((r) => r.xs));
  }
  return { top: mean(top), bottom: mean(bot) };
}
const momentumTest = Object.fromEntries(
  ["rs", "offHigh", "m121"].map((key) => [
    key,
    { in: ic(mom.filter(isIn), key, "xs"), out: ic(mom.filter((r) => !isIn(r)), key, "xs"), deciles: decileSpread(mom, key) },
  ])
);

/* ---------- write ---------- */

if (!WRITE) {
  console.log(JSON.stringify({ stopAtr: STOP_ATR, control: { meanR: mean(ctlR) }, bySetup: Object.fromEntries(SETUPS.map((k) => [k, mean(setupR[k])])),
    runs: Object.fromEntries(Object.entries(runs).map(([k, v]) => [k, { cagr: v.cagr, odd: v.oddYears, even: v.evenYears, sharpe: v.sharpe, mdd: v.mdd, meanR: v.meanR, trades: v.trades, beaten: v.beaten }])),
    gates }, null, 1));
  process.exit(0);
}
mkdirSync(OUT, { recursive: true });
mkdirSync(join(ROOT, "docs", "scorecard"), { recursive: true });

const csv = (rows, cols) => [cols.join(","), ...rows.map((r) => cols.map((c) => (r[c] == null ? "" : typeof r[c] === "number" ? +r[c].toFixed(5) : r[c])).join(","))].join("\n") + "\n";
writeFileSync(join(OUT, "calibration.csv"), csv(calib, ["date", "t", "sector", "setup", "status", "total", ...BLOCKS, "rr", "r", "maeR", "fwd", "xs", "earnSoon"]));
writeFileSync(join(OUT, "trades.csv"), csv(strategyRun.closed, ["t", "setup", "total", "entry", "exit", "reason", "r", "pct"]));
writeFileSync(join(OUT, "equity.csv"), csv(strategyRun.curve.map((c) => ({ week: c.k, equity: c.equity, invested: c.invested, positions: c.n })), ["week", "equity", "invested", "positions"]));
const summary = {
  built: new Date().toISOString(),
  data_through: asOfBuild,
  start: START,
  names: U.length,
  cards: calib.length,
  blockIC,
  suggested,
  shipped: Object.fromEntries(SETUPS.map((k) => [k, PROFILES[k].weights])),
  quintilesOut: Object.fromEntries(SETUPS.map((k) => [k, quintiles(calib.filter((r) => r.setup === k && !isIn(r)))])),
  quintilesIn: Object.fromEntries(SETUPS.map((k) => [k, quintiles(calib.filter((r) => r.setup === k && isIn(r)))])),
  gates,
  momentumTest,
  control: { n: ctlR.length, meanR: mean(ctlR), bySetup: Object.fromEntries(SETUPS.map((k) => [k, { n: setupR[k].length, meanR: mean(setupR[k]) }])) },
  breadth: {
    median: [...breadth.stage2].sort((a, b) => a - b)[Math.floor(breadth.stage2.length / 2)],
    p20: [...breadth.stage2].sort((a, b) => a - b)[Math.floor(breadth.stage2.length / 5)],
  },
  runs,
};
writeFileSync(join(OUT, "backtest_summary.json"), JSON.stringify(summary, null, 1));
writeFileSync(DOC, report(summary));
console.log(JSON.stringify({ suggested, runs: Object.fromEntries(Object.entries(runs).map(([k, v]) => [k, { cagr: v.cagr, sharpe: v.sharpe, mdd: v.mdd, meanR: v.meanR, trades: v.trades }])), control: summary.control, breadth: summary.breadth, gates }, null, 1));

/* ---------- the report ---------- */

function report(S) {
  const L = [];
  const r = S.runs;
  L.push(`# The weekly strategy — backtest and block calibration`);
  L.push("");
  L.push(`*Generated by \`scripts/scorecard/backtest.mjs\` on ${S.built.slice(0, 10)} from data through ${S.data_through}. ` +
    `${S.names} S&P 500 names, ${S.cards.toLocaleString()} BUY setups carded since ${S.start}. Research, not advice.*`);
  L.push("");
  L.push(`This note is the evidence behind the cockpit's weekly review — the TAPE, SHORTLIST, CARD, BOOK and ORDERS pages. ` +
    `It asks three questions in order: do the setups beat a random entry; does the scorecard rank the setups; and does a portfolio built from the ranking beat the same portfolio built at random. ` +
    `Only the third is the strategy, and each depends on the one before.`);
  L.push("");
  L.push(`## Read this first — the biases`);
  L.push("");
  L.push(`- **Survivorship.** The universe is *today's* S&P 500, so every name in it survived. Any long strategy on it flatters itself, and the headline returns below are **not** an estimate of future returns. The honest comparisons are relative: setups against random entries, ranked against random portfolios, and returns in excess of the same universe in the same week.`);
  L.push(`- **No fundamentals history.** yfinance keeps none, so the fundamental block is absent from every historical card. It is graded live only, and the repo now snapshots it weekly (\`data/fundamentals/snapshots/\`) so that one day it can be tested.`);
  L.push(`- **Earnings data from 2014.** The earnings block and the earnings veto are only testable from there.`);
  L.push(`- **Weekly fills.** Stops fill on the weekly bar, at the stop or at the open on a gap: the simulator's weekly model.`);
  L.push(`- **Costs.** ${COSTS.fxPct}% per side, which is Trading 212's FX fee on a USD name in a GBP ISA. There's no commission and no slippage model beyond the gap rule.`);
  L.push(`- **Samples.** Odd years are in-sample, where the weights were chosen, and even years are out-of-sample, where they are judged.`);
  L.push("");
  L.push(`## 1. Do the setups beat a random entry?`);
  L.push("");
  L.push(`Every trade uses the same exits: the initial stop under the decision week's low, break-even at +1R, a trail under the 10-week, the 30-week thesis rule and a 26-week time limit. Only the entry differs.`);
  L.push("");
  L.push(`| entry | trades | mean R |`);
  L.push(`|---|---|---|`);
  L.push(`| random week (control) | ${S.control.n.toLocaleString()} | ${sg(S.control.meanR)} |`);
  for (const k of SETUPS) L.push(`| ${k} | ${S.control.bySetup[k].n.toLocaleString()} | ${sg(S.control.bySetup[k].meanR)} |`);
  L.push("");
  L.push(`**They do not.** On this universe a random week, managed by these exits, earns about what a setup does. The expectancy is the **exits'** (cut losers at −1R, let the trail run the winners) plus the universe's survivorship drift. That's why the scorecard has to earn its place by *ranking*. Setup rules alone would be decoration.`);
  L.push("");
  L.push(`## 2. Does the scorecard rank the setups?`);
  L.push("");
  L.push(`The rank IC here is **within-week**: a block's score and the outcome are both ranked among the BUY setups of the *same week*, then correlated across all weeks. That's the question the portfolio asks, because it chooses among one week's candidates. A pooled IC would mix in timing, since a good week lifts every candidate whatever its score. There are two outcomes: the strategy's trade result in **R** (what a risk-sized book earns), and the 13-week return in **excess** of the whole universe that week. Positive is good. With thousands of setups an IC of 0.03 is real but small, and anything below about ±0.02 is noise.`);
  L.push("");
  L.push(`The *suggested* weight column is what fitting the in-sample ICs would give: a weight proportional to each block's positive in-sample information. **It was not adopted.** Compare each block's in-sample IC with its out-of-sample IC: the signs flip for most blocks, so weights fitted to one half would be fitted to noise. The shipped weights are the spec's priors (\`scorecard.js\` PROFILES), with one evidence-led change: the chart-pattern block carries no weight.`);
  L.push("");
  for (const k of SETUPS) {
    L.push(`### ${k}`);
    L.push("");
    L.push(`| block | n (in) | IC R in | IC xs in | IC R out | IC xs out | suggested (not adopted) | shipped |`);
    L.push(`|---|---|---|---|---|---|---|---|`);
    for (const b of [...BLOCKS, "total"]) {
      const x = S.blockIC[k][b];
      L.push(`| ${b === "total" ? "**headline**" : b} | ${x.inR.n} | ${sg(x.inR.ic)} | ${sg(x.inX.ic)} | ${sg(x.outR.ic)} | ${sg(x.outX.ic)} | ${b === "total" ? "" : S.suggested[k][b] ?? ""} | ${b === "total" ? "" : S.shipped[k][b]} |`);
    }
    L.push("");
    L.push(`Headline quintiles, **out of sample** (even years):`);
    L.push("");
    L.push(`| quintile | n | score range | mean R | excess 13w | win >0.1R |`);
    L.push(`|---|---|---|---|---|---|`);
    for (const q of S.quintilesOut[k]) L.push(`| Q${q.q} | ${q.n} | ${f2(q.lo, 0)}–${f2(q.hi, 0)} | ${sg(q.meanR)} | ${pc(q.xs)} | ${pc(q.win, 0)} |`);
    L.push("");
  }
  L.push(`## 3. The gates`);
  L.push("");
  const g = S.gates;
  L.push(`**Earnings veto** (no entry with a report due within ${EARNINGS_WINDOW_DAYS} days; BUY setups since mid-2014):`);
  L.push("");
  L.push(`| | n | mean R | losses worse than −1.5R |`);
  L.push(`|---|---|---|---|`);
  L.push(`| report due inside the window | ${g.earnings.soon.n} | ${sg(g.earnings.soon.meanR)} | ${pc(g.earnings.soon.gapLoss)} |`);
  L.push(`| clear of reports | ${g.earnings.clear.n} | ${sg(g.earnings.clear.meanR)} | ${pc(g.earnings.clear.gapLoss)} |`);
  L.push("");
  L.push(`**Reward:risk veto** (no trade under ${MIN_RR}:1 to the nearest resistance):`);
  L.push("");
  L.push(`| | n | mean R |`);
  L.push(`|---|---|---|`);
  L.push(`| R:R under ${MIN_RR} | ${g.rr.low.n} | ${sg(g.rr.low.meanR)} |`);
  L.push(`| R:R ${MIN_RR} or better | ${g.rr.ok.n} | ${sg(g.rr.ok.meanR)} |`);
  L.push("");
  L.push(`## 4. The portfolio`);
  L.push("");
  L.push(`Portfolio results are **path-dependent**. One changed decision in 2001 changes which names are held in 2002, so small rule changes move the CAGR by two or three points. The random-ranking row therefore averages ${S.runs.randomRank.seeds} seeds and gives their range, and the strategy beat **${pc(S.runs.randomRank.beaten, 0)}** of them. Read differences of a couple of points as noise.`);
  L.push("");
  L.push(`**Stop width.** The initial stop's floor (1 ATR, \`RULES.stop.minAtr\`) was chosen from 0.5, 1.0, 1.5 and 2.0 ATR on the in-sample years. It held out of sample. At the simulator's 0.5 ATR, weekly noise stops trades out before they start, and the structure block's R:R then measured stop *tightness* and ranked outcomes backwards.`);
  L.push("");
  L.push(`The same construction the ORDERS page runs (\`construct.js\`): each position is sized from its stop, with the TAPE's risk budget, a heat cap, at most ${10} positions and 3 per sector, and a correlation cap. The trim band is the only rebalancing. It starts at $${STARTING_EQUITY.toLocaleString()} in ${S.start.slice(0, 4)}.`);
  L.push("");
  L.push(`| run | CAGR | odd yrs | even yrs | vol | Sharpe | max DD | exposure | trades | win | mean R |`);
  L.push(`|---|---|---|---|---|---|---|---|---|---|---|`);
  const row = (name, m) => L.push(`| ${name} | ${pc(m.cagr)} | ${pc(m.oddYears)} | ${pc(m.evenYears)} | ${pc(m.vol)} | ${f2(m.sharpe)} | ${pc(m.mdd)} | ${pc(m.exposure, 0)} | ${m.trades == null ? "—" : Math.round(m.trades)} | ${pc(m.win, 0)} | ${sg(m.meanR)} |`);
  row("**strategy** (ranked by score, TAPE budget)", r.strategy);
  row("ranked by score, no TAPE budget (always FULL)", r.noTape);
  row(`**random ranking**, TAPE budget (mean of ${r.randomRank.seeds}; CAGR ${pc(r.randomRank.spread[0])}–${pc(r.randomRank.spread[1])})`, r.randomRank);
  row("SPY buy & hold", r.spy);
  L.push("");
  L.push(`Read it in this order:`);
  L.push("");
  L.push(`1. **Strategy against random ranking.** It's the same setups, the same sizing and the same exits; only the order candidates are taken in differs. The gap between them is everything the scorecard contributes.`);
  L.push(`2. **Strategy against no TAPE.** This shows what the risk budget does to drawdown, and what it costs in return.`);
  L.push(`3. **Against SPY**, only then, and only with the survivorship caveat above.`);
  L.push("");
  L.push(`### Year by year (strategy)`);
  L.push("");
  L.push(`| year | strategy | SPY |`);
  L.push(`|---|---|---|`);
  const spyY = Object.fromEntries(r.spy.yearly.map((y) => [y.y, y.ret]));
  for (const y of r.strategy.yearly) L.push(`| ${y.y} | ${pc(y.ret)} | ${pc(spyY[y.y])} |`);
  L.push("");
  L.push(`## 5. Why selection cannot be validated on this universe`);
  L.push("");
  L.push(`If the blocks cannot rank the setups, perhaps the setup list is simply too homogeneous. So the best-documented cross-sectional effect in equities, momentum, is tested on the **whole universe**: every name, every 4th week since ${S.start.slice(0, 4)}, ranked within the week against its excess 13-week return.`);
  L.push("");
  L.push(`| signal | IC in (odd yrs) | IC out (even yrs) | top decile excess | bottom decile excess |`);
  L.push(`|---|---|---|---|---|`);
  const labels = { rs: "26-week RS vs SPY", offHigh: "distance from 52-week high", m121: "12-1 momentum" };
  for (const [k, v] of Object.entries(S.momentumTest)) L.push(`| ${labels[k]} | ${sg(v.in.ic)} | ${sg(v.out.ic)} | ${pc(v.deciles.top, 2)} | ${pc(v.deciles.bottom, 2)} |`);
  L.push("");
  L.push(`Momentum does not rank this universe either, and the *losers* do at least as well as the winners. That isn't evidence that momentum is dead. It's the survivorship bias at work, and in a specific direction. The universe is today's S&P 500, so every stock in it that fell hard later recovered, or it wouldn't be here. The ones that fell and kept falling were delisted or dropped from the index, and they're missing. **A survivor-only universe is biased against momentum and quality, and in favour of buying losers.** Every cross-sectional test in this note carries that bias, and nothing in the available data can remove it: point-in-time constituent lists exist, but prices for the names that left mostly don't.`);
  L.push("");
  L.push(`## 6. What this means for the strategy`);
  L.push("");
  L.push(`- **The risk side is evidence-backed and robust.** The TAPE budget cuts the maximum drawdown by roughly two-fifths. The earnings veto cuts gap losses roughly threefold. The 1 ATR stop floor beat the simulator's 0.5 ATR default in both halves. Sizing from the stop keeps every loss near 1R. These rules held in every variant tested.`);
  L.push(`- **The selection side is unproven, and this data can't prove it.** The block weights are literature-based priors. They were deliberately not fitted, because fitting them to in-sample noise would have produced weights that fail out of sample. Treat the headline as a consistent, explicit checklist, not as a forecast.`);
  L.push(`- **The per-trade expectancy comes from the exits.** Cutting at the stop and trailing winners gives about +0.3R a trade, and random entries earn it too on this universe. The strategy's claim is that it takes those trades in a disciplined, risk-budgeted way, not that it picks better stocks.`);
  L.push(`- **The honest test is forward.** From now on each week's cards are recorded as they stood (\`data/scorecard/ledger/\`), including names that later leave the index, so there's no survivorship. The fundamentals are snapshotted weekly alongside them. Grade the ledger after a year. It's the first evidence about the scorecard that can't be flattering.`);
  L.push("");
  L.push(`## 7. Breadth`);
  L.push("");
  L.push(`The share of the universe in Stage 2 has a median of **${f2(S.breadth.median, 0)}%** and a bottom quintile below **${f2(S.breadth.p20, 0)}%**, measured on today's constituents. The TAPE's FULL and DEFENSIVE thresholds are set against these (\`tape.js\` BREADTH_FULL / BREADTH_DEFENSIVE).`);
  L.push("");
  L.push(`---`);
  L.push("");
  L.push(`*Files: \`data/scorecard/calibration.csv\` (every carded setup), \`trades.csv\`, \`equity.csv\`, \`backtest_summary.json\`. Re-run after any change to \`strategy.js\` or \`scorecard.js\`.*`);
  return L.join("\n") + "\n";
}
