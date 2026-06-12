/* Portfolios — relative-value pair-portfolio dashboard.
   Loads the selected portfolio's pre-computed equity curve and renders a
   hand-rolled SVG line chart plus four snapshot stats. */

import { escapeHtml } from "./strategy-engine.js";
import { CATALOG } from "./catalog.js";

const DATA_BASE = "data";

// Reports tied to a portfolio, keyed by portfolio slug. Sourced from the
// publication catalog so there's one source of truth for what's published.
const REPORTS_BY_PORTFOLIO = new Map(
  CATALOG.filter(c => c.type === "report" && c.portfolio)
         .map(c => [c.portfolio, c])
);

const state = {
  slug: null,
  mode: "letf",   // slot key: 'letf' = column 2 (wrapper / net), 'under' = column 1 (gross / 1x)
  window: "90d",  // chart window: '90d' | '1y' | '5y' | 'all'. Most readers only care about the recent run.
};

// Trailing-window lengths in calendar days. 'all' keeps the whole series.
const WINDOW_DAYS = { "90d": 90, "1y": 365, "5y": 365 * 5, "all": null };

// Per-kind labels for the two curves. The 'letf' slot is always column 2,
// 'under' is always column 1 — only the wording changes between an LETF
// index pair and a CFD single-share pair.
const KIND_LABELS = {
  letf: {
    clab: "WRAPPER",
    letf:  { chip: "LSE LETF wrap", label: "LETF WRAPPER", word: "LETF wrapper" },
    under: { chip: "1x underlying", label: "1X UNDERLYING", word: "1x underlying" },
  },
  cfd: {
    clab: "VIEW",
    letf:  { chip: "Net of costs", label: "NET OF T212 COSTS", word: "net of T212 costs" },
    under: { chip: "Gross spread", label: "GROSS SPREAD",      word: "gross spread, no costs" },
  },
};

function kindOf(meta){ return meta && meta.kind === "cfd" ? "cfd" : "letf"; }
function legDisp(leg){ return leg.letf || leg.ticker || leg.label; }

let menu = [];
const cache = new Map();
let builtAt = null;

/* ---------- data ---------- */

async function loadMenu(){
  const res = await fetch(`${DATA_BASE}/portfolios.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load portfolios.json (${res.status})`);
  const j = await res.json();
  menu = j.portfolios;
  builtAt = j.built_at;
}

async function loadPortfolio(slug){
  if(cache.has(slug)) return cache.get(slug);
  const res = await fetch(`${DATA_BASE}/portfolios/${slug}.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load ${slug}.json (${res.status})`);
  const j = await res.json();
  cache.set(slug, j);
  return j;
}

/* ---------- stats from bars ---------- */

function computeSnapshot(bars, modeIdx){
  // bars: [[date, equity_under, equity_letf]]; modeIdx 1=under, 2=letf
  const vals = bars.map(b => b[modeIdx]);
  const dates = bars.map(b => b[0]);
  const current = vals[vals.length - 1];

  let athIdx = 0, atlIdx = 0;
  for(let i = 1; i < vals.length; i++){
    if(vals[i] > vals[athIdx]) athIdx = i;
    if(vals[i] < vals[atlIdx]) atlIdx = i;
  }

  // Max drawdown across whole series (largest peak-to-trough %)
  let peak = vals[0], maxDD = 0, ddPeakDate = dates[0], ddTroughDate = dates[0];
  let curPeak = vals[0], curPeakDate = dates[0];
  for(let i = 0; i < vals.length; i++){
    if(vals[i] > curPeak){ curPeak = vals[i]; curPeakDate = dates[i]; }
    const dd = vals[i] / curPeak - 1;
    if(dd < maxDD){
      maxDD = dd;
      ddPeakDate = curPeakDate;
      ddTroughDate = dates[i];
    }
  }

  // YTD: find first bar of current year (use last date's year)
  const currYear = dates[dates.length - 1].slice(0, 4);
  let yStartVal = null;
  for(const [d, vu, vl] of bars){
    if(d >= `${currYear}-01-01`){ yStartVal = (modeIdx === 1 ? vu : vl); break; }
  }
  const ytd = (yStartVal != null) ? (current / yStartVal - 1) : null;

  return {
    current,
    totalReturn: current - 1,
    ath: vals[athIdx], athDate: dates[athIdx],
    atl: vals[atlIdx], atlDate: dates[atlIdx],
    maxDD, ddPeakDate, ddTroughDate,
    ytd,
    firstDate: dates[0],
    lastDate:  dates[dates.length - 1],
  };
}

/* ---------- window slicing ---------- */

// Trailing slice of the equity curve by calendar days from the last bar.
// Falls back to the whole (or last two) bars if the window predates inception.
function sliceWindow(bars, win){
  const days = WINDOW_DAYS[win];
  if(days == null) return bars;
  const cutoff = Date.parse(bars[bars.length - 1][0]) - days * 86400000;
  const sliced = bars.filter(b => Date.parse(b[0]) >= cutoff);
  return sliced.length >= 2 ? sliced : bars.slice(-2);
}

/* ---------- SVG chart ---------- */

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// X-axis ticks adapt to the visible span: months for short windows (with the
// year shown at each January boundary), calendar years for long ones. Returns
// at most ~8 evenly-spaced labels.
function buildXTicks(bars){
  const spanDays = (Date.parse(bars[bars.length - 1][0]) - Date.parse(bars[0][0])) / 86400000;
  const byMonth = spanDays <= 450;
  const ticks = [];
  let lastKey = "";
  bars.forEach((b, i) => {
    const key = byMonth ? b[0].slice(0, 7) : b[0].slice(0, 4);
    if(key !== lastKey){
      const label = byMonth
        ? (b[0].slice(5, 7) === "01" ? b[0].slice(0, 4) : MONTHS[+b[0].slice(5, 7) - 1])
        : key;
      ticks.push({i, label});
      lastKey = key;
    }
  });
  const step = Math.ceil(ticks.length / 8);
  return ticks.filter((_, k) => k % step === 0);
}

function renderChart(bars, modeIdx, label, color){
  // Narrower viewBox on phones so axis labels don't scale down into
  // illegibility (the SVG always stretches to the container width, so a
  // smaller viewBox means a larger effective font). See css mobile section.
  const mobile = window.innerWidth <= 700;
  const W = mobile ? 480 : 1000, H = mobile ? 340 : 380;
  const padL = mobile ? 48 : 70, padR = mobile ? 14 : 24, padT = 24, padB = 36;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const vals = bars.map(b => b[modeIdx]);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const rangeV = maxV - minV || 1;
  const padV = rangeV * 0.05;
  const yMin = minV - padV;
  const yMax = maxV + padV;
  const yRange = yMax - yMin;

  const xOf = i => padL + (i / (bars.length - 1)) * innerW;
  const yOf = v => padT + (1 - (v - yMin) / yRange) * innerH;

  // Polyline points
  const pts = bars.map((b, i) => `${xOf(i).toFixed(1)},${yOf(b[modeIdx]).toFixed(1)}`).join(" ");

  // X-axis ticks: months for short windows, years for long ones.
  const xLabels = buildXTicks(bars);

  // Y axis labels (5 ticks)
  const yLabels = [];
  for(let k = 0; k <= 4; k++){
    const v = yMin + (k / 4) * yRange;
    yLabels.push({v, y: yOf(v)});
  }

  // Break-even (£1) line if 1.0 is inside the range
  const breakEven = (yMin <= 1.0 && 1.0 <= yMax)
    ? `<line x1="${padL}" y1="${yOf(1.0).toFixed(1)}" x2="${padL+innerW}" y2="${yOf(1.0).toFixed(1)}" stroke="var(--gold)" stroke-dasharray="3 4" stroke-width="1" opacity="0.6"/>
       <text x="${padL+innerW-6}" y="${(yOf(1.0)-4).toFixed(1)}" fill="var(--gold)" font-family="VT323, monospace" font-size="14" text-anchor="end" opacity="0.8">£1 break-even</text>`
    : "";

  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="eq-chart" shape-rendering="geometricPrecision">
    <rect x="${padL}" y="${padT}" width="${innerW}" height="${innerH}" fill="var(--inset)" stroke="var(--line)" stroke-width="1"/>

    ${yLabels.map(({v, y}) => `
      <line x1="${padL}" y1="${y.toFixed(1)}" x2="${padL+innerW}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="0.6" opacity="0.7"/>
      <text x="${padL-8}" y="${(y+4).toFixed(1)}" fill="var(--dim)" font-family="VT323, monospace" font-size="15" text-anchor="end">${v.toFixed(2)}</text>
    `).join("")}

    ${xLabels.map(({i, label}) => `
      <line x1="${xOf(i).toFixed(1)}" y1="${padT}" x2="${xOf(i).toFixed(1)}" y2="${padT+innerH}" stroke="var(--line)" stroke-width="0.6" opacity="0.4"/>
      <text x="${xOf(i).toFixed(1)}" y="${padT+innerH+18}" fill="var(--dim)" font-family="VT323, monospace" font-size="15" text-anchor="middle">${escapeHtml(label)}</text>
    `).join("")}

    ${breakEven}

    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round"/>

    <text x="${padL+12}" y="${padT+22}" fill="${color}" font-family="'Press Start 2P', monospace" font-size="10">${escapeHtml(label)}</text>
  </svg>`;
}

/* ---------- formatting ---------- */

function fmtMult(v){ return v.toFixed(2) + "x"; }
function fmtPct(v){
  if(v == null || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : (v < 0 ? "−" : "");
  return sign + (Math.abs(v) * 100).toFixed(1) + "%";
}
function fmtDate(d){ return d ? d : "—"; }

/* ---------- render ---------- */

function renderPortfolioMenu(){
  const sel = document.getElementById("portfolio-select");
  sel.innerHTML = menu.map(p =>
    `<option value="${p.slug}">${escapeHtml(p.name)}</option>`
  ).join("");
  sel.value = state.slug;
}

function renderPortfolioLabel(p){
  document.getElementById("portfolio-name").textContent = p.name;
  document.getElementById("portfolio-legs").textContent =
    `${legDisp(p.long)} + ${legDisp(p.short)}`;
}

function applyKindLabels(meta){
  const cfg = KIND_LABELS[kindOf(meta)];
  document.getElementById("mode-clab").textContent = cfg.clab;
  const seg = document.getElementById("mode-seg");
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === state.mode);
    const slot = cfg[opt.dataset.value];
    if(slot) opt.textContent = slot.chip;
  }
}

function renderBlurb(meta){
  document.getElementById("portfolio-blurb").textContent = meta.blurb;
  const beta = meta.beta_clip
    ? `, hedge ratio clipped to [${meta.beta_clip[0]}, ${meta.beta_clip[1]}]`
    : "";
  const legsEl = document.getElementById("portfolio-legs-line");
  if(kindOf(meta) === "cfd"){
    const markup = meta.markup_annual != null ? (meta.markup_annual * 100).toFixed(1) : "3.0";
    legsEl.innerHTML =
      `Long leg: <b>${escapeHtml(meta.long.label)}</b> (${escapeHtml(meta.long.ticker || "")}). ` +
      `Short leg: <b>${escapeHtml(meta.short.label)}</b> (${escapeHtml(meta.short.ticker || "")}), held short. ` +
      `Hedge ratio recomputed daily from the prior ${meta.lookback}-day window${beta}. ` +
      `The net view applies Trading 212 CFD costs: zero commission, no FX fee (both legs are GBP-listed), ` +
      `and overnight financing every night — the benchmark rate (≈ BoE Bank Rate) plus a ~${markup}% per-year markup on the long leg, ` +
      `minus the same markup credited on the short. On a balanced pair the benchmark cancels and the running cost is roughly twice the markup.`;
  } else {
    legsEl.innerHTML =
      `Long leg: <b>${escapeHtml(meta.long.label)}</b> via ` +
      `<b>${escapeHtml(meta.long.letf)}</b> (${meta.long.lev}x). ` +
      `Short leg: <b>${escapeHtml(meta.short.label)}</b> via ` +
      `<b>${escapeHtml(meta.short.letf)}</b> (${meta.short.lev}x short). ` +
      `Hedge ratio recomputed daily from prior ${meta.lookback}-day window${beta}.`;
  }
}

function renderStats(snap, mode, meta){
  const modeWord = KIND_LABELS[kindOf(meta)][mode].word;
  const rows = [
    {
      label: "CURRENT VALUE",
      sub: `from £1 at inception (${snap.firstDate})`,
      main: `£${fmtMult(snap.current)}`,
      side: fmtPct(snap.totalReturn),
      sideCls: snap.totalReturn > 0 ? "pos" : "neg",
    },
    {
      label: "ALL-TIME HIGH / LOW",
      sub: `peak ${snap.athDate} · trough ${snap.atlDate}`,
      main: `£${fmtMult(snap.ath)}`,
      side: `£${fmtMult(snap.atl)} low`,
      sideCls: "",
    },
    {
      label: "MAX DRAWDOWN",
      sub: `${snap.ddPeakDate} → ${snap.ddTroughDate}`,
      main: fmtPct(snap.maxDD),
      side: "peak-to-trough",
      sideCls: "neg",
    },
    {
      label: "YEAR TO DATE",
      sub: `since ${snap.lastDate.slice(0,4)}-01-01`,
      main: fmtPct(snap.ytd),
      side: "",
      sideCls: snap.ytd == null ? "" : (snap.ytd > 0 ? "pos" : "neg"),
    },
  ];
  document.getElementById("stat-grid").innerHTML = rows.map(r => `
    <div class="stat">
      <div class="stat-label">${escapeHtml(r.label)}</div>
      <div class="stat-main ${r.sideCls}">${r.main}</div>
      ${r.side ? `<div class="stat-side ${r.sideCls}">${escapeHtml(r.side)}</div>` : ""}
      <div class="stat-sub">${escapeHtml(r.sub)}</div>
    </div>
  `).join("");

  document.getElementById("snapshot-note").textContent =
    `${modeWord} · ${snap.firstDate} → ${snap.lastDate}`;
}

// Show a deep-dive link when the selected portfolio has a published report.
function renderReport(){
  const panel = document.getElementById("report-panel");
  const report = REPORTS_BY_PORTFOLIO.get(state.slug);
  if(!report){ panel.hidden = true; return; }
  document.getElementById("report-blurb").textContent = report.blurb;
  document.getElementById("report-link").href = report.page;
  panel.hidden = false;
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- main update ---------- */

async function update(){
  const payload = await loadPortfolio(state.slug);
  const meta = payload.meta;
  const modeIdx = state.mode === "letf" ? 2 : 1;
  const color = state.mode === "letf" ? "var(--cyan)" : "var(--magenta)";
  const label = KIND_LABELS[kindOf(meta)][state.mode].label;

  renderPortfolioLabel(meta);
  applyKindLabels(meta);
  renderBlurb(meta);
  renderReport();

  const snap = computeSnapshot(payload.bars, modeIdx);
  renderStats(snap, state.mode, meta);

  // The chart zooms to the chosen trailing window; the snapshot stats above
  // stay all-time. Values are the running multiple of £1 from inception — the
  // window only changes which slice of that curve we draw.
  const view = sliceWindow(payload.bars, state.window);
  const wrap = document.getElementById("chart-wrap");
  wrap.innerHTML = renderChart(view, modeIdx, label, color);
  document.getElementById("chart-note").textContent =
    `${view[0][0]} → ${view[view.length - 1][0]} · ${view.length} trading days`;
}

/* ---------- wiring ---------- */

function wireControls(){
  document.getElementById("portfolio-select").addEventListener("change", e => {
    state.slug = e.target.value;
    update();
  });
  document.getElementById("mode-seg").addEventListener("click", e => {
    const btn = e.target.closest(".opt");
    if(!btn) return;
    state.mode = btn.dataset.value;
    update();
  });
  document.getElementById("window-seg").addEventListener("click", e => {
    const btn = e.target.closest(".opt");
    if(!btn) return;
    state.window = btn.dataset.value;
    for(const opt of e.currentTarget.querySelectorAll(".opt")){
      opt.classList.toggle("on", opt.dataset.value === state.window);
    }
    update();
  });

  // Re-render the chart when crossing the mobile/desktop breakpoint so the
  // viewBox geometry (see renderChart) matches the viewport. Cheap — the
  // portfolio payload is cached, so update() does no network work.
  let lastMobile = window.innerWidth <= 700;
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const nowMobile = window.innerWidth <= 700;
      if(nowMobile !== lastMobile){
        lastMobile = nowMobile;
        update();
      }
    }, 150);
  });
}

/* ---------- boot ---------- */

(async function init(){
  try{
    await loadMenu();
    state.slug = menu[0].slug;
    renderPortfolioMenu();
    renderBuiltLine();
    wireControls();
    await update();
  } catch(err){
    document.getElementById("chart-wrap").innerHTML =
      `<div class="chart-error">Failed to load: ${escapeHtml(err.message)}</div>`;
    console.error(err);
  }
})();
