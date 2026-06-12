/* Price Tracker — single-instrument price chart + snapshot.
   Loads the selected instrument's daily bars and renders a hand-rolled SVG
   price line (closing price) plus four snapshot stats. Reached by clicking an
   instrument anywhere on the site (scanner / league tables) via
   ?instrument=<slug>, or by picking from the dropdown.

   Note on the future: instruments will come in two flavours — a single-symbol
   instrument (this page) and a portfolio instrument (a basket / pair, already
   served by portfolios.html). This page is the single-symbol tracker; when the
   portfolio-instrument type lands, the symbol links can route by type. All
   computation is local to the browser; data is pre-built JSON from web/data/. */

import { escapeHtml } from "./strategy-engine.js";

const DATA_BASE = "data";

const state = {
  instrument: "spx",
  window: "1y",   // chart + snapshot window: '90d' | '1y' | '5y' | 'all'
};

// Trailing-window lengths in calendar days. 'all' keeps the whole series.
const WINDOW_DAYS = { "90d": 90, "1y": 365, "5y": 365 * 5, "all": null };
const WINDOW_WORD = { "90d": "90 days", "1y": "1 year", "5y": "5 years", "all": "all history" };

const cache = new Map();   // slug -> {meta, bars}
let instruments = [];
let builtAt = null;

/* ---------- data loaders ---------- */

async function loadInstruments(){
  const res = await fetch(`${DATA_BASE}/instruments.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load instruments.json (${res.status})`);
  const j = await res.json();
  instruments = j.instruments;
  builtAt = j.built_at;
}

// Preselect an instrument from ?instrument=<slug> (e.g. a scanner / league
// deep-link), but only if it's a real instrument in the menu.
function applyInstrumentParam(){
  const slug = new URLSearchParams(location.search).get("instrument");
  if(slug && instruments.some(i => i.slug === slug)) state.instrument = slug;
  else if(!instruments.some(i => i.slug === state.instrument) && instruments.length)
    state.instrument = instruments[0].slug;
}

async function loadBars(slug){
  if(cache.has(slug)) return cache.get(slug);
  const res = await fetch(`${DATA_BASE}/${slug}.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load ${slug}.json (${res.status})`);
  const j = await res.json();
  cache.set(slug, j);
  return j;
}

/* ---------- window slicing ---------- */

// Trailing slice of the bars by calendar days from the last bar. Falls back to
// the whole (or last two) bars if the window predates the first bar.
function sliceWindow(bars, win){
  const days = WINDOW_DAYS[win];
  if(days == null) return bars;
  const cutoff = Date.parse(bars[bars.length - 1][0]) - days * 86400000;
  const sliced = bars.filter(b => Date.parse(b[0]) >= cutoff);
  return sliced.length >= 2 ? sliced : bars.slice(-2);
}

/* ---------- snapshot ---------- */

// bars are [date, open, close]; close is index 2.
function computeSnapshot(allBars, viewBars){
  const last     = allBars[allBars.length - 1][2];
  const lastDate = allBars[allBars.length - 1][0];
  const prev     = allBars.length >= 2 ? allBars[allBars.length - 2][2] : null;
  const dayChange = prev != null ? last / prev - 1 : null;

  // Change across the visible window (first close of the slice -> last close).
  const winStart = viewBars[0][2];
  const winChange = winStart ? last / winStart - 1 : null;

  // High / low close over the visible window.
  let hi = viewBars[0][2], lo = viewBars[0][2], hiDate = viewBars[0][0], loDate = viewBars[0][0];
  for(const b of viewBars){
    if(b[2] > hi){ hi = b[2]; hiDate = b[0]; }
    if(b[2] < lo){ lo = b[2]; loDate = b[0]; }
  }

  // Year to date: first close on/after Jan 1 of the last bar's year.
  const year = lastDate.slice(0, 4);
  let ytdStart = null;
  for(const b of allBars){ if(b[0] >= `${year}-01-01`){ ytdStart = b[2]; break; } }
  const ytd = ytdStart ? last / ytdStart - 1 : null;

  return {
    last, lastDate, dayChange,
    winChange, winStart, winFirstDate: viewBars[0][0],
    hi, hiDate, lo, loDate,
    ytd, year,
  };
}

/* ---------- formatting ---------- */

function fmtPrice(v){
  if(v == null || !Number.isFinite(v)) return "—";
  return v.toLocaleString("en-GB", {minimumFractionDigits:2, maximumFractionDigits:2});
}
function fmtPct(v){
  if(v == null || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : (v < 0 ? "−" : "");
  return sign + (Math.abs(v) * 100).toFixed(1) + "%";
}
// Compact price for axis ticks — fewer digits so labels stay readable.
function fmtAxis(v){
  const a = Math.abs(v);
  if(a >= 1000) return v.toLocaleString("en-GB", {maximumFractionDigits:0});
  if(a >= 100)  return v.toFixed(0);
  if(a >= 10)   return v.toFixed(1);
  return v.toFixed(2);
}
function pnCls(v){ return v == null || !Number.isFinite(v) ? "" : (v > 0 ? "pos" : (v < 0 ? "neg" : "")); }

/* ---------- SVG chart ---------- */

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// X-axis ticks adapt to the visible span: months for short windows (year shown
// at each January boundary), calendar years for long ones. ~8 labels max.
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

function renderChart(bars, label){
  // Narrower viewBox on phones so axis labels don't scale into illegibility
  // (the SVG always stretches to the container width). See css mobile section.
  const mobile = window.innerWidth <= 700;
  const W = mobile ? 480 : 1000, H = mobile ? 340 : 380;
  const padL = mobile ? 54 : 78, padR = mobile ? 14 : 24, padT = 24, padB = 36;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const vals = bars.map(b => b[2]);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const rangeV = maxV - minV || Math.abs(maxV) || 1;
  const padV = rangeV * 0.05;
  const yMin = minV - padV;
  const yMax = maxV + padV;
  const yRange = yMax - yMin;

  const xOf = i => padL + (i / (bars.length - 1)) * innerW;
  const yOf = v => padT + (1 - (v - yMin) / yRange) * innerH;

  const pts = bars.map((b, i) => `${xOf(i).toFixed(1)},${yOf(b[2]).toFixed(1)}`).join(" ");
  const xLabels = buildXTicks(bars);

  const yLabels = [];
  for(let k = 0; k <= 4; k++){
    const v = yMin + (k / 4) * yRange;
    yLabels.push({v, y: yOf(v)});
  }

  const lastX = xOf(bars.length - 1), lastY = yOf(vals[vals.length - 1]);

  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="eq-chart" shape-rendering="geometricPrecision">
    <rect x="${padL}" y="${padT}" width="${innerW}" height="${innerH}" fill="var(--inset)" stroke="var(--line)" stroke-width="1"/>

    ${yLabels.map(({v, y}) => `
      <line x1="${padL}" y1="${y.toFixed(1)}" x2="${padL+innerW}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="0.6" opacity="0.7"/>
      <text x="${padL-8}" y="${(y+4).toFixed(1)}" fill="var(--dim)" font-family="VT323, monospace" font-size="15" text-anchor="end">${escapeHtml(fmtAxis(v))}</text>
    `).join("")}

    ${xLabels.map(({i, label}) => `
      <line x1="${xOf(i).toFixed(1)}" y1="${padT}" x2="${xOf(i).toFixed(1)}" y2="${padT+innerH}" stroke="var(--line)" stroke-width="0.6" opacity="0.4"/>
      <text x="${xOf(i).toFixed(1)}" y="${padT+innerH+18}" fill="var(--dim)" font-family="VT323, monospace" font-size="15" text-anchor="middle">${escapeHtml(label)}</text>
    `).join("")}

    <polyline points="${pts}" fill="none" stroke="var(--cyan)" stroke-width="1.8" stroke-linejoin="round"/>
    <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="3.5" fill="var(--cyan)"/>

    <text x="${padL+12}" y="${padT+22}" fill="var(--cyan)" font-family="'Press Start 2P', monospace" font-size="10">${escapeHtml(label)}</text>
  </svg>`;
}

/* ---------- render ---------- */

function renderInstrumentMenu(){
  const sel = document.getElementById("instrument-select");
  const opt = i => `<option value="${i.slug}">${escapeHtml(i.label)}</option>`;
  // Group into <optgroup> sections, preserving first-seen order.
  const groups = [];
  const byGroup = new Map();
  for(const i of instruments){
    const g = i.group || "";
    if(!byGroup.has(g)){ byGroup.set(g, []); groups.push(g); }
    byGroup.get(g).push(i);
  }
  sel.innerHTML = (groups.length === 1 && groups[0] === "")
    ? instruments.map(opt).join("")
    : groups.map(g =>
        `<optgroup label="${escapeHtml(g)}">${byGroup.get(g).map(opt).join("")}</optgroup>`
      ).join("");
  sel.value = state.instrument;
  updateInstrumentLabel();
}

function updateInstrumentLabel(){
  const inst = instruments.find(i => i.slug === state.instrument);
  if(!inst) return;
  document.getElementById("instrument-name").textContent = inst.name || inst.label;
  document.getElementById("instrument-ticker").textContent = inst.ticker || "";
}

function renderStats(snap){
  const dirWord = snap.dayChange == null ? "" : (snap.dayChange > 0 ? "up on the day" : (snap.dayChange < 0 ? "down on the day" : "flat on the day"));
  const rows = [
    {
      label: "LATEST CLOSE",
      main: fmtPrice(snap.last), mainCls: "",
      side: fmtPct(snap.dayChange), sideCls: pnCls(snap.dayChange),
      sub: `${escapeHtml(dirWord)} · ${snap.lastDate}`,
    },
    {
      label: `CHANGE · ${WINDOW_WORD[state.window].toUpperCase()}`,
      main: fmtPct(snap.winChange), mainCls: pnCls(snap.winChange),
      side: `from ${fmtPrice(snap.winStart)}`, sideCls: "",
      sub: `${snap.winFirstDate} → ${snap.lastDate}`,
    },
    {
      label: "WINDOW HIGH / LOW",
      main: fmtPrice(snap.hi), mainCls: "",
      side: `${fmtPrice(snap.lo)} low`, sideCls: "",
      sub: `high ${snap.hiDate} · low ${snap.loDate}`,
    },
    {
      label: "YEAR TO DATE",
      main: fmtPct(snap.ytd), mainCls: pnCls(snap.ytd),
      side: "", sideCls: "",
      sub: `since ${snap.year}-01-01`,
    },
  ];
  document.getElementById("stat-grid").innerHTML = rows.map(r => `
    <div class="stat">
      <div class="stat-label">${escapeHtml(r.label)}</div>
      <div class="stat-main ${r.mainCls}">${escapeHtml(r.main)}</div>
      ${r.side ? `<div class="stat-side ${r.sideCls}">${escapeHtml(r.side)}</div>` : ""}
      <div class="stat-sub">${escapeHtml(r.sub)}</div>
    </div>
  `).join("");
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- main update ---------- */

async function update(){
  const payload = await loadBars(state.instrument);
  const inst = instruments.find(i => i.slug === state.instrument);
  const view = sliceWindow(payload.bars, state.window);

  const snap = computeSnapshot(payload.bars, view);
  renderStats(snap);

  const wrap = document.getElementById("chart-wrap");
  wrap.innerHTML = renderChart(view, (inst && inst.name) || state.instrument);

  document.getElementById("chart-note").textContent =
    `${view[0][0]} → ${view[view.length - 1][0]} · ${view.length} trading days`;
  document.getElementById("snapshot-note").textContent =
    inst ? `${inst.name} · ${inst.ticker}` : "";
}

/* ---------- wiring ---------- */

function wireControls(){
  document.getElementById("instrument-select").addEventListener("change", e => {
    state.instrument = e.target.value;
    updateInstrumentLabel();
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
  // viewBox geometry matches the viewport. Cheap — bars are cached.
  let lastMobile = window.innerWidth <= 700;
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const nowMobile = window.innerWidth <= 700;
      if(nowMobile !== lastMobile){ lastMobile = nowMobile; update(); }
    }, 150);
  });
}

/* ---------- boot ---------- */

(async function init(){
  try{
    await loadInstruments();
    applyInstrumentParam();
    renderInstrumentMenu();
    renderBuiltLine();
    wireControls();
    await update();
  } catch(err){
    document.getElementById("chart-wrap").innerHTML =
      `<div class="chart-error">Failed to load: ${escapeHtml(err.message)}</div>`;
    console.error(err);
  }
})();
