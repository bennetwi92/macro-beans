// Grade the weekly ledger: what happened to the cards the scorecard issued?
//
//   node scripts/scorecard/grade_ledger.mjs
//
// Reads every data/scorecard/ledger/<week>.csv (written each week by
// build_scorecards.mjs --ledger and committed by fundamentals.yml) and, for
// each card whose trade has had time to finish, replays the strategy's own
// trade from that week (strategy.js `runTrade`) on the current price history.
//
// This is the scorecard's forward test, and the first evidence about it that
// cannot flatter it: the backtest runs on today's S&P 500, so every name in it
// survived; the ledger recorded names BEFORE anyone knew which would. A name
// that has since left the universe has no price file here — it is REPORTED,
// never silently dropped, because dropping it would rebuild exactly the
// survivorship bias the ledger exists to escape. Fetch its history by hand
// (python -m src.data.refresh --tickers X) and re-run.

import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

import { parseCsv, ROOT, loadUniverse } from "../site/_scorecard_data.mjs";
import { prepareSeries, runTrade, weekAsOf } from "../../web/v2/js/strategy.js";

const DIR = join(ROOT, "data", "scorecard", "ledger");
if (!existsSync(DIR)) {
  console.log("No ledger yet — data/scorecard/ledger/ is written by the weekly workflow.");
  process.exit(0);
}
const weeks = readdirSync(DIR).filter((f) => f.endsWith(".csv")).sort();
const cards = weeks.flatMap((f) => parseCsv(readFileSync(join(DIR, f), "utf8")));
const { builtAt, names } = loadUniverse({ only: new Set(cards.map((c) => c.t)) });
const series = new Map(names.map((n) => [n.t, prepareSeries(n.daily, builtAt.slice(0, 10))]));

const graded = [];
const missing = new Set();
let pending = 0;
for (const c of cards) {
  const s = series.get(c.t);
  if (!s) {
    missing.add(c.t);
    continue;
  }
  const w = weekAsOf(s, c.week);
  if (w < 0 || s.bars[w].d !== c.week) {
    missing.add(c.t);
    continue;
  }
  const t = runTrade(s, w);
  if (!t || t.open) {
    pending++;
    continue;
  }
  graded.push({ ...c, total: Number(c.total), r: t.r });
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const fmt = (x) => (x == null ? "—" : `${x >= 0 ? "+" : ""}${x.toFixed(3)}R`);
console.log(`# Ledger grade — ${weeks.length} weeks (${weeks[0] ?? "—"} … ${weeks[weeks.length - 1] ?? "—"})\n`);
console.log(`${cards.length} cards · ${graded.length} graded · ${pending} still running · ${missing.size} names missing a price file\n`);
for (const status of ["BUY", "WATCH", "PASS"]) {
  const g = graded.filter((x) => x.status === status);
  console.log(`${status.padEnd(6)} n=${String(g.length).padStart(5)}  mean ${fmt(mean(g.map((x) => x.r)))}`);
}
const buys = graded.filter((x) => x.status === "BUY").sort((a, b) => a.total - b.total);
if (buys.length >= 20) {
  const half = Math.floor(buys.length / 2);
  console.log(`\nBUY, lower half of scores  ${fmt(mean(buys.slice(0, half).map((x) => x.r)))}`);
  console.log(`BUY, upper half of scores  ${fmt(mean(buys.slice(half).map((x) => x.r)))}`);
  console.log(`\nIf the upper half does not beat the lower, the headline does not rank — whatever the backtest said.`);
}
if (missing.size) {
  console.log(`\nMissing (left the universe, or no history): ${[...missing].sort().join(", ")}`);
  console.log(`These are exactly the names survivorship would hide. Fetch and re-run before reading the numbers.`);
}
