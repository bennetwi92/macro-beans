// Shared plumbing for the weekly review — the five steps of the Sunday
// routine: TAPE → SHORTLIST → CARD → BOOK → ORDERS. Loaders (fetched once,
// cached in memory), the step strip that makes the five pages read as one
// flow, and the small formatters every step uses.
//
// Spec: docs/web_v2/scorecard_strategy_spec.md §4. The analytics are NOT here:
// they live in the pure, tested modules (strategy.js, scorecard.js, tape.js,
// construct.js). This file only fetches and draws.

import { prepareMarket } from "./sim-market.js";
import { prepareSeries } from "./strategy.js";

export const STEPS = [
  { n: 1, key: "tape", label: "MARKET", file: "tape.html", q: "is this a good week to buy?" },
  { n: 2, key: "shortlist", label: "IDEAS", file: "shortlist.html", q: "which stocks look worth buying?" },
  { n: 3, key: "card", label: "CHECK", file: "card.html", q: "should I buy this one?" },
  { n: 4, key: "book", label: "MY STOCKS", file: "book.html", q: "should I keep what I own?" },
  { n: 5, key: "orders", label: "TO DO", file: "orders.html", q: "what exactly do I do on Monday?" },
];

/* ---------- plain-English vocabulary ----------
 *
 * The rules modules speak in keys (BUY / WATCH / PASS, FULL / HALF /
 * DEFENSIVE, PULLBACK / BREAKOUT / REVERSAL, Weinstein stages 1-4). The
 * pages are for someone new to trading, so every key is SHOWN through these
 * maps and never printed raw. Keys stay as they are: CSS classes, the build
 * and the ledger use them.
 */
export const SAY = {
  status: { BUY: "BUY", WATCH: "NOT YET", PASS: "SKIP" },
  statusLong: {
    BUY: "Worth buying this week",
    WATCH: "Close, but not yet. Check again next week",
    PASS: "Skip it. Something important is wrong",
  },
  setup: { PULLBACK: "DIP", BREAKOUT: "NEW HIGH", REVERSAL: "TURNAROUND" },
  setupLong: {
    PULLBACK: "a rising stock that has dipped and is bouncing back",
    BREAKOUT: "a stock breaking above its highest price of the last six months",
    REVERSAL: "a fallen stock that has stopped falling and is turning up",
  },
  level: { FULL: "GREEN LIGHT", HALF: "AMBER", DEFENSIVE: "RED LIGHT" },
  levelLong: {
    FULL: "Good conditions for buying",
    HALF: "Mixed conditions, so buy less than usual",
    DEFENSIVE: "Poor conditions, so buy very little",
  },
  trend: { bull: "UP", bear: "DOWN", neutral: "SIDEWAYS" },
  stage: { 1: "flat", 2: "rising", 3: "stalling", 4: "falling" },
  index: { SPY: "S&P 500", QQQ: "Nasdaq 100 (tech)", IWM: "Small companies" },
  // runTrade's exit reasons
  action: { BUY: "BUY", EXIT: "SELL ALL", TRIM: "SELL SOME", TRAIL: "RAISE STOP", RESET: "KEEP", HOLD: "KEEP" },
  exit: { stop: "hit its stop-loss", trail: "hit its raised stop-loss", thesis: "uptrend ended", time: "time limit reached", open: "still held" },
};

/** "+1.4× risk": a result as a multiple of the money that was at risk (R). */
export const xRisk = (r, dp = 1) =>
  r == null || !Number.isFinite(r) ? "—" : Math.abs(r) < 0.5 * 10 ** -dp ? "0×" : `${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(dp)}×`;

/* ---------- loaders ---------- */

const cache = new Map();
function once(key, fn) {
  if (!cache.has(key)) cache.set(key, fn().catch((e) => { cache.delete(key); throw e; }));
  return cache.get(key);
}
const getJSON = (url) => fetch(url, { cache: "no-cache" }).then((r) => {
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
});

export const loadScorecards = () => once("sc", () => getJSON("data/scorecards.json"));
export const loadMarketFeed = () => once("mk", () => getJSON("data/sim-market.json").then(prepareMarket));
export const loadFundamentals = () => once("fd", () => getJSON("data/fundamentals.json").catch(() => null));
export const loadEarnings = () => once("er", () => getJSON("data/earnings.json").catch(() => ({})));
export const loadUniverse = () => once("un", () => getJSON("data/sim-universe.json"));

/** One name's weekly series, prepared exactly as the build prepared it. */
export function loadSeries(t, asOf) {
  return once(`s:${t}:${asOf}`, () =>
    getJSON(`data/sim/${encodeURIComponent(t)}.json`).then((d) => ({
      name: d.name,
      sector: d.sector,
      s: prepareSeries(d.bars.map((r) => ({ d: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5] })), asOf),
    }))
  );
}

/** `[{d, surprise}]` for a ticker from the compact earnings file. */
export const earningsFor = (all, t) => (all?.[t] || []).map(([d, s]) => ({ d, surprise: s }));

/* ---------- the step strip ---------- */

/**
 * The routine's progress strip: five numbered steps, the current one lit, and
 * a "next" link. Rendered at the top of each step's content so the pages read
 * as one sitting rather than five tools.
 */
export function stepStrip(current, { week = null, next = true } = {}) {
  const i = STEPS.findIndex((s) => s.key === current);
  const links = STEPS.map((s, k) => {
    const cls = k === i ? "rv-step on" : k < i ? "rv-step done" : "rv-step";
    return `<a class="${cls}" href="${s.file}"><b>${s.n}</b>${s.label}</a>`;
  }).join(`<span class="rv-step-sep">›</span>`);
  const nx = next && i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null;
  return (
    `<nav class="rv-steps">${links}` +
    `<span class="rv-step-q">${STEPS[i]?.q ?? ""}${week ? ` · prices to Fri ${week}` : ""}</span>` +
    (nx ? `<a class="rv-step-next" href="${nx.file}">NEXT: ${nx.label} →</a>` : "") +
    `</nav>`
  );
}

/** A read-only options bar: one row of label + text, for pages with no controls. */
export function infoBar(label, html, mountId = "optbar") {
  const el = document.getElementById(mountId);
  if (!el) return;
  el.className = "optbar";
  el.innerHTML = `<div class="optbar-row"><span class="opt-field"><span class="opt-label">${label}</span><span class="dim-note">${html}</span></span></div>`;
}

/* ---------- formatters ---------- */

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const pct = (x, dp = 1, signed = true) =>
  x == null || !Number.isFinite(x) ? "—" : `${signed && x > 0 ? "+" : ""}${x.toFixed(dp)}%`;

export const num = (x, dp = 2) => (x == null || !Number.isFinite(x) ? "—" : x.toFixed(dp));

/** Price at the precision the simulator quotes (cents; four sig figs under $1). */
export const px = (x) => (x == null || !Number.isFinite(x) ? "—" : x >= 1 ? x.toFixed(2) : x.toPrecision(4));

export const updown = (x) => (x == null ? "" : x > 0 ? "up" : x < 0 ? "down" : "");

export function statusChip(status) {
  if (!status) return `<span class="rv-chip rv-none">—</span>`;
  return `<span class="rv-chip rv-${status.toLowerCase()}">${SAY.status[status] ?? status}</span>`;
}

export function gradeChip(b, title = "") {
  if (!b || !b.a) return `<span class="rv-grade rv-g-na" title="${esc(b?.x || title)}">·</span>`;
  return `<span class="rv-grade rv-g-${b.g}" title="${esc(b.x)}">${b.g}</span>`;
}

/** A setup key → its short plain name. */
export const setupName = (k) => (k ? SAY.setup[k] ?? k : "");

/** A budget level → its colour class. */
export const levelClass = (lv) => (lv === "FULL" ? "rv-full" : lv === "DEFENSIVE" ? "rv-def" : "rv-half");

export function trendChip(t) {
  if (!t) return `<span class="rv-tr rv-tr-na">—</span>`;
  return `<span class="rv-tr rv-tr-${t}">${SAY.trend[t] ?? t.toUpperCase()}</span>`;
}

/** "What changed since last week" for a scorecard row. */
export function changeNote(row) {
  const p = row.prev;
  if (!row.status) return p?.status === "BUY" ? "was BUY" : "";
  if (!p || !p.status) return "NEW";
  if (p.status !== row.status) return `was ${SAY.status[p.status] ?? p.status}`;
  return "";
}

/** Render a friendly failure into a mount. */
export function failInto(el, what, err) {
  el.innerHTML = `<div class="rv-empty">Couldn't load ${esc(what)}. This week's numbers may not have been built yet. Try again later.<br><span class="dim-note">${esc(err?.message || err)}</span></div>`;
}
