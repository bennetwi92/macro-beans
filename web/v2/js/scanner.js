// Scanner — daily long-only BUY shortlist.
//
// Runs each strategy's live detector against the latest (or rewound) bar and
// lists the setups that are buyable now, each with its historical track record
// AND its EDGE over the instrument's own drift baseline — so an apparent 60%
// win rate that's really just market drift doesn't masquerade as skill.
//
// Long-only framing: every row is a BUY. Mean-reversion strategies buy
// weakness (a dip), momentum strategies buy strength (a breakout); there is no
// "sell" — bearish views are Phase 2 (buy an inverse ETF).
//
// Strategy MATH is imported from v1's strategy-engine.js (tested). v1 bars are
// [iso, open, close]; our chart bars are [iso, close], so we adapt to
// [iso, close, close] — the scanner only uses entry:"close".

import "./nav.js";
import { createOptionsBar } from "./options-bar.js";
import {
  findEvents, findStreakEvents, findMultiDayEvents, findBreakoutEvents, findRangeEvents, findCrossEvents,
  liveBounce, liveStreak, liveMultiDay, liveBreakout, liveRange, liveCross,
  computeStats, indexAsOf, forwardReturn,
  HORIZONS, STREAK_HORIZONS, MULTIDAY_HORIZONS, BREAKOUT_HORIZONS, RANGE_HORIZONS, CROSS_HORIZONS,
  fmt,
} from "../../js/strategy-engine.js";
import { TabulatorFull as Tabulator } from "https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.2/dist/js/tabulator_esm.min.js";

// Fixed params (mirrors v1's scanner so numbers agree).
const MD_MOVE = { threshold: 8, window: 5 };
const BREAK_LOOK = 20;
const RANGE_SET = { band: 3, window: 10 };
const CROSS_PER = 200;
const SHRINK_K = 20; // small-sample shrinkage for the ranking score

const state = {
  style: "all",   // all | dip | breakout
  fresh: true,    // only setups that became true on the as-of bar
  trend: "all",   // all | up (above 200-day)
  range: "5y",    // track-record window
  asOf: null,     // rewind date; null = live
  threshold: 2.0,
  streak: 3,
};

// Each strategy carries its natural BUY direction and style. A long buyer buys
// dips (mean-reversion, "down") and breakouts (momentum, "up").
const STRATEGIES = [
  { key: "bounce", label: "Buy the Bounce", style: "dip", dir: "down", hold: HORIZONS.at(-1), horizons: HORIZONS,
    detect: (b) => liveBounce(b, { direction: "down", threshold: state.threshold }),
    signal: (s) => `${fmt(s.move)} day`, sigVal: (s) => s.move,
    stats: (b) => computeStats(findEvents(b, { direction: "down", threshold: state.threshold, entry: "close", range: state.range }))[2] },
  { key: "streak", label: "Red Streak", style: "dip", dir: "down", hold: STREAK_HORIZONS.at(-1), horizons: STREAK_HORIZONS,
    detect: (b) => liveStreak(b, { direction: "down", streak: state.streak }),
    signal: (s) => `${s.run} red closes`, sigVal: () => null,
    stats: (b) => computeStats(findStreakEvents(b, { direction: "down", streak: state.streak, entry: "close", range: state.range }))[2] },
  { key: "multiday", label: "Multi-Day Drop", style: "dip", dir: "down", hold: MULTIDAY_HORIZONS.at(-1), horizons: MULTIDAY_HORIZONS,
    detect: (b) => liveMultiDay(b, { direction: "down", ...MD_MOVE }),
    signal: (s) => `${fmt(s.move)} / ${MD_MOVE.window}d`, sigVal: (s) => s.move,
    stats: (b) => computeStats(findMultiDayEvents(b, { direction: "down", threshold: MD_MOVE.threshold, window: MD_MOVE.window, entry: "close", range: state.range }))[2] },
  { key: "breakout", label: "Breakout High", style: "breakout", dir: "up", hold: BREAKOUT_HORIZONS.at(-1), horizons: BREAKOUT_HORIZONS,
    detect: (b) => liveBreakout(b, { direction: "up", lookback: BREAK_LOOK }),
    signal: () => `${BREAK_LOOK}-day high`, sigVal: () => null,
    stats: (b) => computeStats(findBreakoutEvents(b, { direction: "up", lookback: BREAK_LOOK, entry: "close", range: state.range }))[2] },
  { key: "cross", label: "MA Cross Up", style: "breakout", dir: "up", hold: CROSS_HORIZONS.at(-1), horizons: CROSS_HORIZONS,
    detect: (b) => liveCross(b, { direction: "up", period: CROSS_PER }),
    signal: () => `above ${CROSS_PER}-day`, sigVal: () => null,
    stats: (b) => computeStats(findCrossEvents(b, { direction: "up", period: CROSS_PER, entry: "close", range: state.range }))[2] },
  { key: "range", label: "Tight Range", style: "range", dir: null, hold: RANGE_HORIZONS.at(-1), horizons: RANGE_HORIZONS,
    detect: (b) => liveRange(b, RANGE_SET),
    signal: (s) => `${s.spread.toFixed(1)}% range`, sigVal: () => null,
    stats: (b) => computeStats(findRangeEvents(b, { band: RANGE_SET.band, window: RANGE_SET.window, entry: "close", range: state.range }))[2] },
];

const INSTR = []; // [{ticker, name, theme, bars:[[iso,c,c]]}]

/* ---------- scan helpers ---------- */

const globalLatest = () => INSTR.reduce((m, i) => (i.bars.length && i.bars.at(-1)[0] > m ? i.bars.at(-1)[0] : m), "");
const globalEarliest = () => INSTR.reduce((m, i) => (i.bars.length && (!m || i.bars[0][0] < m) ? i.bars[0][0] : m), "");
const effectiveDate = () => state.asOf || globalLatest();
const isHistory = () => Boolean(state.asOf) && state.asOf < globalLatest();

function yearsAgoISO(view, n) {
  const [Y, M, D] = view.at(-1)[0].split("-").map(Number);
  return `${Y - n}-${String(M).padStart(2, "0")}-${String(D).padStart(2, "0")}`;
}

// Unconditional forward-return baseline over the same window/horizon — the
// "always invested" drift the signal must beat to be a real edge.
function baselineStats(view, H) {
  const minDate = state.range === "5y" ? yearsAgoISO(view, 5) : null;
  let n = 0, wins = 0, sum = 0;
  for (let i = 0; i < view.length - H; i++) {
    if (minDate && view[i][0] < minDate) continue;
    const r = view[i + H][2] / view[i][2] - 1;
    sum += r; if (r > 0) wins += 1; n += 1;
  }
  return n ? { n, rate: (wins / n) * 100, avg: (sum / n) * 100 } : { n: 0, rate: NaN, avg: NaN };
}

// Above the 200-day average on the as-of bar? null if too little history.
function trendUp(view) {
  if (view.length < 200) return null;
  let s = 0;
  for (let k = view.length - 200; k < view.length; k++) s += view[k][2];
  return view.at(-1)[2] >= s / 200;
}

function passesStyle(strat) {
  return state.style === "all" || strat.style === state.style;
}

function scanRows() {
  const asOf = effectiveDate();
  const history = isHistory();
  const rows = [];
  for (const inst of INSTR) {
    const bars = inst.bars;
    const idx = indexAsOf(bars, asOf);
    if (idx < 2) continue;
    const view = idx === bars.length - 1 ? bars : bars.slice(0, idx + 1);
    const up = trendUp(view);
    if (state.trend === "up" && up === false) continue;

    for (const strat of STRATEGIES) {
      if (!passesStyle(strat)) continue;
      const sig = strat.detect(view);
      if (!sig.triggered) continue;
      // "New today": true on the as-of bar but not the one before it.
      if (state.fresh && view.length > 3 && strat.detect(view.slice(0, -1)).triggered) continue;

      const st = strat.stats(view);
      const base = baselineStats(view, strat.hold);
      const edge = Number.isFinite(st.avg) && Number.isFinite(base.avg) ? st.avg - base.avg : NaN;
      const edgeWin = Number.isFinite(st.rate) && Number.isFinite(base.rate) ? st.rate - base.rate : NaN;
      // Rank by per-day edge, shrunk toward zero by sample size.
      const score = Number.isFinite(edge) ? (edge / strat.hold) * (st.n / (st.n + SHRINK_K)) : -Infinity;
      const outcome = history ? forwardReturn(bars, idx, strat.hold) : NaN;

      rows.push({
        ticker: inst.ticker, name: inst.name, theme: inst.theme,
        strategy: strat.label, signal: strat.signal(sig), sigVal: strat.sigVal(sig),
        trendUp: up, hold: `${strat.hold}d`,
        edge, edgeWin, avg: st.avg, rate: st.rate, med: st.med, worst: st.worst, n: st.n,
        score, outcome: Number.isFinite(outcome) ? outcome : null,
        pending: history && !Number.isFinite(outcome),
      });
    }
  }
  return rows;
}

/* ---------- formatters ---------- */

const paint = (cell, up, down) => {
  const el = cell.getElement();
  el.classList.toggle("up", up);
  el.classList.toggle("down", down);
};
const nameFmt = (cell) => {
  const d = cell.getRow().getData();
  return `<span class="ps-name">${d.name}</span> <span class="ps-tkr">${d.ticker}</span>`;
};
const signalFmt = (cell) => {
  const d = cell.getRow().getData();
  if (typeof d.sigVal === "number") paint(cell, d.sigVal > 0, d.sigVal < 0);
  return cell.getValue() ?? "";
};
const pct1 = (cell) => {
  const v = cell.getValue();
  if (v == null || Number.isNaN(v)) return "";
  paint(cell, v > 0, v < 0);
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
};
const edgeFmt = (cell) => {
  const v = cell.getValue();
  if (v == null || Number.isNaN(v)) return "—";
  paint(cell, v > 0, v < 0);
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
};
const rateFmt = (cell) => {
  const d = cell.getRow().getData();
  const v = cell.getValue();
  if (d.n === 0 || v == null || Number.isNaN(v)) return "—";
  paint(cell, d.edgeWin > 0, d.edgeWin < 0); // colour vs the instrument's OWN base rate
  return `${Math.round(v)}%`;
};
const nFmt = (cell) => {
  const v = cell.getValue();
  if (v == null) return "";
  if (v < 10) { cell.getElement().classList.add("ps-dim"); return `${v} ⚠`; }
  return String(v);
};
const trendFmt = (cell) => {
  const up = cell.getRow().getData().trendUp;
  const el = cell.getElement();
  el.classList.remove("up", "down", "ps-dim");
  if (up === true) { el.classList.add("up"); return "▲"; }
  if (up === false) { el.classList.add("down"); return "▼"; }
  el.classList.add("ps-dim"); return "·";
};
const outcomeFmt = (cell) => {
  const d = cell.getRow().getData();
  if (d.pending) { cell.getElement().classList.add("ps-dim"); return "pending"; }
  return pct1(cell);
};
const chartFmt = (cell) => {
  const t = cell.getRow().getData().ticker;
  return (
    `<a class="ps-chart" href="chart.html?i=${t}" title="Open chart" onclick="event.stopPropagation()">` +
    `<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">` +
    `<polyline points="1,11 5,7 8,9 14,3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></a>`
  );
};

// Tabulator 6.5 has no setPlaceholder(); update the empty-state text in the DOM.
function setEmptyMsg(msg) {
  const el = document.querySelector("#scan-grid .tabulator-placeholder-contents");
  if (el) el.textContent = msg;
}

/* ---------- grid ---------- */

const R = "right";
const grid = new Tabulator("#scan-grid", {
  data: [],
  layout: "fitData",
  height: "100%",
  placeholder: "No buy setups for these filters — widen the setup/trend filters or the date.",
  initialSort: [{ column: "score", dir: "desc" }],
  columns: [
    { title: "INSTRUMENT", field: "name", frozen: true, width: 168, formatter: nameFmt },
    { title: "THEME", field: "theme", width: 116, cssClass: "ps-theme" },
    { title: "SETUP", field: "strategy", width: 130 },
    { title: "SIGNAL", field: "signal", width: 104, formatter: signalFmt },
    { title: "TREND", field: "trendUp", width: 56, hozAlign: "center", headerSort: false, formatter: trendFmt, headerTooltip: "Above (▲) or below (▼) the 200-day average" },
    { title: "EDGE", field: "edge", width: 66, hozAlign: R, formatter: edgeFmt, headerTooltip: "Avg forward return minus the instrument's own baseline (drift removed). This is the real edge." },
    { title: "AVG", field: "avg", width: 60, hozAlign: R, formatter: pct1, headerTooltip: "Average forward return over the hold (gross — includes market drift)" },
    { title: "WIN%", field: "rate", width: 60, hozAlign: R, formatter: rateFmt, headerTooltip: "Win rate; coloured vs the instrument's baseline win rate" },
    { title: "MED", field: "med", width: 58, hozAlign: R, formatter: pct1, headerTooltip: "Median forward return" },
    { title: "WORST", field: "worst", width: 64, hozAlign: R, formatter: pct1, headerTooltip: "Worst single outcome in the track record" },
    { title: "N", field: "n", width: 50, hozAlign: R, formatter: nFmt, headerTooltip: "Sample size (⚠ under 10 — treat as noise)" },
    { title: "HOLD", field: "hold", width: 48, hozAlign: R, cssClass: "ps-theme" },
    { title: "OUTCOME", field: "outcome", width: 74, hozAlign: R, visible: false, formatter: outcomeFmt },
    { title: "score", field: "score", visible: false },
    { title: "", field: "chart", width: 34, hozAlign: "center", headerSort: false, formatter: chartFmt },
  ],
});

function refresh() {
  try {
    if (isHistory()) grid.showColumn("outcome");
    else grid.hideColumn("outcome");
  } catch (_) { /* ignore */ }
  grid.setData(scanRows());
}

/* ---------- options bar ---------- */

createOptionsBar("optbar", {
  primary: [
    { type: "seg", id: "scan-style", label: "SETUP", value: state.style,
      options: [{ value: "all", label: "All" }, { value: "dip", label: "Dips" }, { value: "breakout", label: "Breakouts" }] },
    { type: "seg", id: "scan-fresh", label: "WHEN", value: "new",
      options: [{ value: "new", label: "New today" }, { value: "active", label: "All active" }] },
    { type: "seg", id: "scan-trend", label: "TREND", value: state.trend,
      options: [{ value: "all", label: "All" }, { value: "up", label: "Uptrend" }] },
    { type: "seg", id: "scan-range", label: "TRACK", value: state.range,
      options: [{ value: "5y", label: "5Y" }, { value: "all", label: "All" }] },
    { type: "date", id: "scan-asof", label: "AS OF" },
  ],
  onChange: (id, value) => {
    if (id === "scan-style") state.style = value;
    else if (id === "scan-fresh") state.fresh = value === "new";
    else if (id === "scan-trend") state.trend = value;
    else if (id === "scan-range") state.range = value;
    else if (id === "scan-asof") state.asOf = value && value < globalLatest() ? value : null;
    refresh();
  },
});

/* ---------- load ---------- */

grid.on("tableBuilt", async () => {
  try {
    const menuRes = await fetch("data/instruments.json", { cache: "no-cache" });
    if (!menuRes.ok) throw new Error(`HTTP ${menuRes.status}`);
    const menu = await menuRes.json();
    const list = menu.instruments || [];
    const loaded = await Promise.all(
      list.map(async (m) => {
        try {
          const res = await fetch(`data/charts/${encodeURIComponent(m.ticker)}.json`, { cache: "no-cache" });
          if (!res.ok) return null;
          const d = await res.json();
          return { ticker: m.ticker, name: m.name, theme: m.theme, bars: (d.bars || []).map((b) => [b[0], b[1], b[1]]) };
        } catch { return null; }
      })
    );
    INSTR.push(...loaded.filter(Boolean));
    if (!INSTR.length) { setEmptyMsg("No instrument data found."); return; }

    const dateEl = document.getElementById("scan-asof");
    if (dateEl) {
      dateEl.min = globalEarliest();
      dateEl.max = globalLatest();
      dateEl.value = globalLatest();
    }
    refresh();
  } catch (err) {
    setEmptyMsg(`Could not load scanner data (${err.message})`);
  }
});
