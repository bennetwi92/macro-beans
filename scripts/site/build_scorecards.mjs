// Build the weekly review's data: every S&P 500 name scored as of the last
// completed week, the TAPE read, breadth history, and the inputs the CARD page
// needs to recompute any one name in the browser.
//
//   node scripts/site/build_scorecards.mjs            # the site's JSON
//   node scripts/site/build_scorecards.mjs --ledger   # + this week's ledger CSV
//
// Runs AFTER build_sim.py and build_sim_market.py (it reads their output) and
// reads the committed fundamentals snapshots + earnings calendar. It imports
// the browser's own modules, as scripts/tools/pattern_census.mjs does: the
// card computed here and the card the CARD page recomputes are the same
// function over the same inputs, so they cannot disagree.
//
// Outputs (web/v2/data/, gitignored):
//   scorecards.json    {built_at, week, tape, breadth, priors, fundamentals_as_of, rows:[…]}
//   fundamentals.json  {as_of, grades:{T:{quality,value,detail}}, raw:{T:{…}}}
//   earnings.json      {T: [[iso, surprise|null], …]}
//
// With --ledger it also writes data/scorecard/ledger/<week>.csv: every card
// with a setup, as it stood this week. That file is COMMITTED (by the weekly
// fundamentals.yml workflow) and is the strategy's forward evidence: the only
// test of the scorecard free of survivorship, because a name recorded this
// week stays recorded if it later leaves the index. Grade it with
// scripts/scorecard/grade_ledger.mjs.
//
// Coverage gate: fails (exit 1) if fewer than MIN_COVERAGE of the universe
// could be scored — a half-built shortlist ranks over a fragment and would be
// worse than yesterday's.

import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

import { loadUniverse, loadMarket, loadEarnings, loadFundamentals, V2_DATA, ROOT } from "./_scorecard_data.mjs";
import { prepareSeries, eventTable, universePriors } from "../../web/v2/js/strategy.js";
import { scoreCard, BLOCKS } from "../../web/v2/js/scorecard.js";
import { gradeFundamentals } from "../../web/v2/js/fundamental-score.js";
import { breadthSeries, tapeRead } from "../../web/v2/js/tape.js";
import { weeklyReturns } from "../../web/v2/js/construct.js";

const MIN_COVERAGE = 0.6;
const BREADTH_FROM = "2006-01-01"; // twenty years of breadth for the TAPE chart

const t0 = Date.now();
const log = (...a) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s]`, ...a);

const { builtAt, names } = loadUniverse();
const asOf = builtAt.slice(0, 10);
const market = loadMarket();
const earnings = loadEarnings();
const fund = loadFundamentals(asOf);
log(`${names.length} names · market ${market ? "ok" : "MISSING"} · earnings ${earnings.size} · fundamentals ${fund ? fund.asOf : "none"}`);

const sectorOf = new Map(names.map((n) => [n.t, n.sector]));
const grades = fund ? gradeFundamentals(fund.rows, (t) => sectorOf.get(t)) : {};

const U = names.map((n) => {
  const s = prepareSeries(n.daily, asOf);
  return { ...n, s, events: eventTable(s) };
});
log("series + event tables");

// The decision week is the latest completed week any name reached.
let week = null;
for (const u of U) {
  const b = u.s.bars[u.s.bars.length - 1];
  if (b && (!week || b.d > week)) week = b.d;
}
const priors = universePriors(U, week);
const breadth = breadthSeries(U.map((u) => u.s), BREADTH_FROM);
const tape = tapeRead(market, breadth, week);

const r1 = (x) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10) / 10);
const r2 = (x) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 100) / 100);
const px = (x) => (x == null || !Number.isFinite(x) ? null : x >= 1 ? Math.round(x * 100) / 100 : Number(x.toPrecision(4)));

const fundFor = (t) => {
  const g = grades[t];
  return g && g.quality != null ? { quality: g.quality, value: g.value, asOf: fund.asOf } : null;
};

const rows = [];
let stale = 0;
for (const u of U) {
  const w = u.s.bars.length - 1;
  if (w < 60) continue;
  const earn = earnings.get(u.t) || null;
  const ctx = { t: u.t, s: u.s, sector: u.sector, market, events: u.events, priors, earnings: earn, fundamentals: fundFor(u.t) };
  const card = scoreCard({ ...ctx, w });
  // Last week's verdict, so the routine can say what CHANGED. Fundamentals are
  // left out of it — the snapshot is this week's.
  const prev = scoreCard({ ...ctx, w: w - 1, fundamentals: null });
  const isStale = u.s.bars[w].d < week;
  if (isStale) stale++;
  const blocks = {};
  for (const k of BLOCKS) {
    const b = card.blocks?.[k];
    if (b) blocks[k] = { a: b.available ? 1 : 0, s: b.score, g: b.grade, x: b.text };
  }
  const info = fund?.rows[u.t] || {};
  rows.push({
    t: u.t,
    n: u.name,
    s: u.sector,
    ind: info.industry || null,
    d: card.date,
    stale: isStale || undefined,
    c: px(card.close),
    st: card.stage,
    age: card.stageAge,
    setup: card.setup,
    status: card.status,
    why: card.why,
    total: r1(card.total),
    blocks,
    plan: card.plan
      ? {
          entry: px(card.plan.entry),
          stop: px(card.plan.stop),
          riskPct: r2(card.plan.riskPct),
          rr: r2(card.plan.rr),
          target: px(card.plan.target),
          blueSky: card.plan.blueSky,
          support: card.plan.support ? px(card.plan.support.price) : null,
        }
      : null,
    vetoes: card.vetoes?.length ? card.vetoes : undefined,
    flags: card.flags?.length ? card.flags : undefined,
    next: card.nextEarnings,
    alt: card.alternatives?.length ? card.alternatives : undefined,
    prev: prev.setup ? { setup: prev.setup, status: prev.status, total: r1(prev.total) } : null,
    // 52 weekly log returns for the ORDERS page's correlation cap — only where
    // a buy is conceivable, to keep the file small.
    ret: card.status === "BUY" || card.status === "WATCH" ? weeklyReturns(u.s, w).map((x) => Math.round(x * 1e4) / 1e4) : undefined,
  });
}

const coverage = rows.length / names.length;
const counts = rows.reduce((a, r) => ((a[r.status || "none"] = (a[r.status || "none"] || 0) + 1), a), {});
log(`scored ${rows.length}/${names.length} (${(coverage * 100).toFixed(0)}%) · week ${week} · ${JSON.stringify(counts)} · stale ${stale}`);

const write = (f, obj) => {
  const s = JSON.stringify(obj);
  writeFileSync(join(V2_DATA, f), s);
  log(`wrote ${f} (${(s.length / 1024).toFixed(0)} KB)`);
};

write("scorecards.json", {
  built_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  data_as_of: asOf,
  week,
  tape,
  breadth,
  priors,
  fundamentals_as_of: fund?.asOf ?? null,
  rows,
});

if (fund) {
  const raw = {};
  for (const [t, r] of Object.entries(fund.rows)) {
    const o = {};
    for (const [k, v] of Object.entries(r)) {
      if (v === "" || v == null) continue;
      const x = Number(v);
      o[k] = Number.isFinite(x) ? Number(x.toPrecision(4)) : v;
    }
    raw[t] = o;
  }
  const g = {};
  for (const [t, x] of Object.entries(grades)) {
    g[t] = { quality: x.quality == null ? null : Math.round(x.quality), value: x.value == null ? null : Math.round(x.value), detail: x.detail };
  }
  write("fundamentals.json", { as_of: fund.asOf, grades: g, raw });
}

const earn = {};
for (const [t, list] of earnings) earn[t] = list.map((e) => [e.d, e.surprise]);
write("earnings.json", earn);

if (process.argv.includes("--ledger")) {
  const dir = join(ROOT, "data", "scorecard", "ledger");
  mkdirSync(dir, { recursive: true });
  const cols = ["week", "t", "sector", "setup", "status", "total", ...BLOCKS, "close", "stop", "rr", "next_earnings", "budget", "why"];
  const q = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  const lines = [cols.join(",")];
  for (const r of rows.filter((x) => x.setup && !x.stale)) {
    lines.push(
      [
        week,
        r.t,
        r.s,
        r.setup,
        r.status,
        r.total,
        ...BLOCKS.map((k) => (r.blocks[k]?.a ? r.blocks[k].s : "")),
        r.c,
        r.plan?.stop,
        r.plan?.rr,
        r.next,
        tape?.budget?.level,
        [r.why, ...(r.vetoes || [])].join("; "),
      ]
        .map(q)
        .join(",")
    );
  }
  writeFileSync(join(dir, `${week}.csv`), lines.join("\n") + "\n");
  log(`wrote data/scorecard/ledger/${week}.csv (${lines.length - 1} cards)`);
}

if (coverage < MIN_COVERAGE) {
  console.error(`Coverage ${(coverage * 100).toFixed(0)}% < ${MIN_COVERAGE * 100}% — failing the build.`);
  process.exit(1);
}
