// Shared input loading for the scorecard's Node scripts — the site build
// (build_scorecards.mjs) and the research backtest (scripts/scorecard/
// backtest.mjs) read the SAME files through the SAME code, so the evidence
// and the live card can never be built from different data.
//
// Inputs:
//   web/v2/data/sim-universe.json, sim/<T>.json   daily OHLCV (build_sim.py)
//   web/v2/data/sim-market.json                   indices, sectors, VIX (build_sim_market.py)
//   data/fundamentals/snapshots/<date>.csv        weekly .info snapshots (committed)
//   data/fundamentals/earnings.csv                earnings calendar + surprises (committed)

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { prepareMarket } from "../../web/v2/js/sim-market.js";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const V2_DATA = join(ROOT, "web", "v2", "data");
export const FUND_DIR = join(ROOT, "data", "fundamentals");

/** RFC-4180-enough CSV: quoted fields, doubled quotes, commas inside quotes. */
export function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else q = false;
      } else field += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      field = "";
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
    } else field += ch;
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  const [head, ...body] = rows;
  return body.map((r) => Object.fromEntries(head.map((h, k) => [h, r[k] ?? ""])));
}

const bar = (r) => ({ d: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5] });

/** The simulator universe: [{t, name, sector, daily}] and the build date. */
export function loadUniverse({ limit = Infinity, only = null } = {}) {
  const idx = JSON.parse(readFileSync(join(V2_DATA, "sim-universe.json"), "utf8"));
  const out = [];
  for (const row of idx.tickers) {
    if (out.length >= limit) break;
    if (only && !only.has(row.t)) continue;
    const f = join(V2_DATA, "sim", `${row.t}.json`);
    if (!existsSync(f)) continue;
    const d = JSON.parse(readFileSync(f, "utf8"));
    out.push({ t: row.t, name: row.n, sector: row.s, daily: d.bars.map(bar) });
  }
  return { builtAt: idx.built_at, names: out };
}

/** The prepared market feed (sim-market.js), or null if it was not built. */
export function loadMarket() {
  const f = join(V2_DATA, "sim-market.json");
  if (!existsSync(f)) return null;
  return prepareMarket(JSON.parse(readFileSync(f, "utf8")));
}

/** `Map(ticker -> [{d, surprise}])`, ascending, surprise in percent or null. */
export function loadEarnings() {
  const f = join(FUND_DIR, "earnings.csv");
  const out = new Map();
  if (!existsSync(f)) return out;
  for (const r of parseCsv(readFileSync(f, "utf8"))) {
    const s = r.surprise_pct === "" || r.surprise_pct == null ? null : Number(r.surprise_pct);
    if (!out.has(r.ticker)) out.set(r.ticker, []);
    out.get(r.ticker).push({ d: r.date, surprise: Number.isFinite(s) ? s : null });
  }
  for (const list of out.values()) list.sort((a, b) => (a.d < b.d ? -1 : a.d > b.d ? 1 : 0));
  return out;
}

/**
 * The newest fundamentals snapshot dated on or before `asOf` (default: the
 * newest). `{asOf, rows: {TICKER: {...}}}` or null. The `<=` is the
 * no-look-ahead rule — a snapshot says nothing about any earlier week.
 */
export function loadFundamentals(asOf = null) {
  const dir = join(FUND_DIR, "snapshots");
  if (!existsSync(dir)) return null;
  const days = readdirSync(dir)
    .filter((f) => f.endsWith(".csv"))
    .map((f) => f.slice(0, -4))
    .filter((d) => asOf == null || d <= asOf)
    .sort();
  if (!days.length) return null;
  const day = days[days.length - 1];
  const rows = {};
  for (const r of parseCsv(readFileSync(join(dir, `${day}.csv`), "utf8"))) {
    const { ticker, ...rest } = r;
    rows[ticker] = rest;
  }
  return { asOf: day, rows };
}
