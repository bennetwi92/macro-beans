// Calibration for the simulator's chart-pattern engine.
//
// Runs `detectPattern` at every eligible decision index across the simulator's
// universe, then runs `resolvePattern` forward to the end of the runway, and
// reports what the feature would actually show a player. It imports the three
// browser modules directly — no port, no reimplementation, no drift.
//
// A one-off tool. Deliberately NOT wired into CI or deploy.yml: it needs the
// built simulator JSON, which is gitignored, and its output is a judgement
// call rather than a pass/fail gate.
//
//   python -m src.data.refresh --tickers-file config/sp500.csv --start 2018-01-01
//   /usr/local/bin/python3 scripts/site/build_sim.py
//   node scripts/tools/pattern_census.mjs
//
// With no built data it falls back to generated random-walk series
// (`--synthetic`). That is a weaker test and the report says so — a random
// walk has no real market structure, so a LOW hit rate on it proves little.
// What it does prove is the direction that matters most: a detector that finds
// ascending triangles in 60% of random walks is too loose, and nothing about
// real data would fix that.
//
// Options:
//   --synthetic       force the generated series even if real data exists
//   --names <n>       how many tickers / synthetic names to sample (default 120)
//   --stride <n>      sample every nth eligible decision day (default 5)

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { atr } from "../../web/v2/js/sim-indicators.js";
import { detectPattern, resolvePattern } from "../../web/v2/js/sim-patterns.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SIM_DIR = join(ROOT, "web", "v2", "data", "sim");

// Mirrors simulator.js. A census run against different numbers would be
// measuring a different feature.
const LOOKBACK = 35;
const WARMUP = 200 + LOOKBACK;
const MAX_HOLD = 60;
const RUNWAY = MAX_HOLD + 2;

const args = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? Number(args[i + 1]) : dflt;
};
const NAMES = flag("names", 120);
const STRIDE = flag("stride", 5);
const FORCE_SYNTH = args.includes("--synthetic");

/* ---------- input ---------- */

function realSeries() {
  let files;
  try {
    files = readdirSync(SIM_DIR).filter((f) => f.endsWith(".json"));
  } catch {
    return null;
  }
  if (!files.length) return null;
  const out = [];
  for (const f of files.slice(0, NAMES)) {
    const d = JSON.parse(readFileSync(join(SIM_DIR, f), "utf8"));
    const bars = (d.bars || []).map((r) => ({ d: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5] }));
    if (bars.length >= WARMUP + RUNWAY) out.push({ ticker: d.ticker, bars });
  }
  return out.length ? out : null;
}

/** A deterministic geometric random walk with fat tails and volatility clustering. */
function syntheticSeries(n, len = 1500) {
  let seed = 20260909;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  const gauss = () => {
    const u = Math.max(1e-9, rnd());
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd());
  };
  const out = [];
  for (let k = 0; k < n; k++) {
    let px = 20 + rnd() * 380;
    let vol = 0.012 + rnd() * 0.02;
    const bars = [];
    for (let i = 0; i < len; i++) {
      vol = 0.9 * vol + 0.1 * (0.012 + rnd() * 0.02); // clustering
      const ret = gauss() * vol;
      const o = px;
      const c = Math.max(1, o * (1 + ret));
      const wick = Math.abs(gauss()) * vol * o * 0.6;
      bars.push({
        d: `2020-01-${String((i % 28) + 1).padStart(2, "0")}`,
        o,
        h: Math.max(o, c) + wick,
        l: Math.max(0.5, Math.min(o, c) - wick),
        c,
        v: 1e6,
      });
      px = c;
    }
    out.push({ ticker: `SYN${k}`, bars });
  }
  return out;
}

/* ---------- the run ---------- */

const real = FORCE_SYNTH ? null : realSeries();
const universe = real ?? syntheticSeries(NAMES);
const source = real ? `built simulator JSON (${universe.length} names)` : `SYNTHETIC random walks (${universe.length} names)`;

const tierCount = { 1: 0, 2: 0, 3: 0, none: 0 };
const byId = new Map();
const stateAtDecision = new Map();
const terminalById = new Map();
let points = 0;
const started = Date.now();

const bump = (m, k) => m.set(k, (m.get(k) || 0) + 1);

for (const { bars } of universe) {
  const atrArr = atr(bars, 14);
  const lo = WARMUP;
  const hi = bars.length - 1 - RUNWAY;
  for (let A = lo; A <= hi; A += STRIDE) {
    points++;
    const p = detectPattern(bars, atrArr, A, { visibleFrom: Math.max(0, A - (LOOKBACK - 1)) });
    if (!p) {
      tierCount.none++;
      continue;
    }
    tierCount[p.tier]++;
    if (p.tier === 1) {
      bump(byId, p.id);
      // The state the PLAYER sees. A pattern's shape can end a few bars before
      // the decision bar, so it may already have broken out by the time the
      // hand is dealt — which is exactly what simulator.js resolves on its
      // first render, and what this band is measuring.
      bump(stateAtDecision, resolvePattern(p, bars, A).state);
      // Run it out to the end of the hand's runway and record where it landed.
      const end = Math.min(bars.length - 1, A + MAX_HOLD);
      const done = resolvePattern(p, bars, end);
      if (!terminalById.has(p.id)) terminalById.set(p.id, new Map());
      bump(terminalById.get(p.id), done.state);
    }
  }
}

/* ---------- the report ---------- */

const pct = (n, d = points) => (d ? ((n / d) * 100).toFixed(1) + "%" : "—");
const band = (ok) => (ok ? "PASS" : "**FAIL**");

const tier1 = tierCount[1] / points;
const anyTier = (tierCount[1] + tierCount[2] + tierCount[3]) / points;
const idRows = [...byId.entries()].sort((a, b) => b[1] - a[1]);
const largest = idRows.length ? idRows[0][1] / tierCount[1] : 0;
const forming = (stateAtDecision.get("forming") || 0) / (tierCount[1] || 1);

console.log(`# Pattern census`);
console.log(`\nSource: ${source}`);
console.log(`Decision points: ${points.toLocaleString()} (stride ${STRIDE}) in ${((Date.now() - started) / 1000).toFixed(1)}s\n`);

console.log(`## Tier reach\n`);
console.log(`| tier | share | band | verdict |`);
console.log(`|---|---|---|---|`);
console.log(`| 1 — chart pattern | ${pct(tierCount[1])} | 20–45% | ${band(tier1 >= 0.2 && tier1 <= 0.45)} |`);
console.log(`| 2 — candlestick | ${pct(tierCount[2])} | — | — |`);
console.log(`| 3 — S/R level | ${pct(tierCount[3])} | — | — |`);
console.log(`| any pattern | ${pct(tierCount[1] + tierCount[2] + tierCount[3])} | ≤ 75% | ${band(anyTier <= 0.75)} |`);
console.log(`| no pattern | ${pct(tierCount.none)} | — | — |`);

console.log(`\n## Tier 1 by id\n`);
console.log(`| id | count | share of tier 1 | ≥ 0.3% |`);
console.log(`|---|---|---|---|`);
for (const [id, n] of idRows) {
  const share = n / tierCount[1];
  console.log(`| ${id} | ${n} | ${(share * 100).toFixed(1)}% | ${band(share >= 0.003)} |`);
}
console.log(`\nLargest single id: ${(largest * 100).toFixed(1)}% (band ≤ 30%) — ${band(largest <= 0.3)}`);

console.log(`\n## State at the decision bar (tier 1)\n`);
console.log(`| state | share |`);
console.log(`|---|---|`);
for (const [st, n] of [...stateAtDecision.entries()].sort((a, b) => b[1] - a[1])) {
  console.log(`| ${st} | ${pct(n, tierCount[1])} |`);
}
console.log(`\n\`forming\` at the decision bar: ${(forming * 100).toFixed(1)}% (band 50–85%) — ${band(forming >= 0.5 && forming <= 0.85)}`);

console.log(`\n## Terminal state after the 60-session runway\n`);
console.log(`| id | confirmed | failed | expired | abandoned | still open |`);
console.log(`|---|---|---|---|---|---|`);
for (const [id] of idRows) {
  const m = terminalById.get(id) || new Map();
  const tot = [...m.values()].reduce((a, b) => a + b, 0) || 1;
  const g = (k) => ((((m.get(k) || 0) / tot) * 100).toFixed(0) + "%").padStart(4);
  const open = tot - ["confirmed", "failed", "expired", "abandoned"].reduce((a, k) => a + (m.get(k) || 0), 0);
  console.log(
    `| ${id} | ${g("confirmed")} | ${g("failed")} | ${g("expired")} | ${g("abandoned")} | ${(((open / tot) * 100).toFixed(0) + "%").padStart(4)} |`
  );
}

if (!real) {
  console.log(
    `\n> Read against a random walk. Structure-free series under-produce every` +
      `\n> pattern that needs repeated respect for a line, so treat a LOW tier-1` +
      `\n> share here as uninformative and a HIGH one as a real failure.`
  );
}
