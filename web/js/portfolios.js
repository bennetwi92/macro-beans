/* Portfolios — relative-value pair-portfolio dashboard.
   Loads the selected portfolio's pre-computed equity curve and renders a
   hand-rolled SVG line chart plus four snapshot stats. */

import { escapeHtml } from "./strategy-engine.js";

const DATA_BASE = "data";

const state = {
  slug: null,
  mode: "letf",   // 'letf' or 'under'
};

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

/* ---------- SVG chart ---------- */

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

  // Year ticks: first bar of each year
  const yearTicks = [];
  let lastYear = "";
  bars.forEach((b, i) => {
    const y = b[0].slice(0, 4);
    if(y !== lastYear){
      yearTicks.push({i, year: y});
      lastYear = y;
    }
  });
  const yearStep = Math.ceil(yearTicks.length / 8);   // ~8 labels max
  const yearLabels = yearTicks.filter((_, k) => k % yearStep === 0);

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

    ${yearLabels.map(({i, year}) => `
      <line x1="${xOf(i).toFixed(1)}" y1="${padT}" x2="${xOf(i).toFixed(1)}" y2="${padT+innerH}" stroke="var(--line)" stroke-width="0.6" opacity="0.4"/>
      <text x="${xOf(i).toFixed(1)}" y="${padT+innerH+18}" fill="var(--dim)" font-family="VT323, monospace" font-size="15" text-anchor="middle">${year}</text>
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
    `${p.long.letf} + ${p.short.letf}`;
}

function renderModeChips(){
  const seg = document.getElementById("mode-seg");
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === state.mode);
  }
}

function renderBlurb(meta){
  document.getElementById("portfolio-blurb").textContent = meta.blurb;
  const beta = meta.beta_clip
    ? `, beta clipped to [${meta.beta_clip[0]}, ${meta.beta_clip[1]}]`
    : "";
  document.getElementById("portfolio-legs-line").innerHTML =
    `Long leg: <b>${escapeHtml(meta.long.label)}</b> via ` +
    `<b>${escapeHtml(meta.long.letf)}</b> (${meta.long.lev}x). ` +
    `Short leg: <b>${escapeHtml(meta.short.label)}</b> via ` +
    `<b>${escapeHtml(meta.short.letf)}</b> (${meta.short.lev}x short). ` +
    `Hedge ratio recomputed daily from prior ${meta.lookback}-day window${beta}.`;
}

function renderStats(snap, mode){
  const modeWord = mode === "letf" ? "LETF wrapper" : "1x underlying";
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

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- main update ---------- */

async function update(){
  const payload = await loadPortfolio(state.slug);
  const modeIdx = state.mode === "letf" ? 2 : 1;
  const color = state.mode === "letf" ? "var(--cyan)" : "var(--magenta)";
  const label = state.mode === "letf" ? "LETF WRAPPER" : "1X UNDERLYING";

  renderPortfolioLabel(payload.meta);
  renderModeChips();
  renderBlurb(payload.meta);

  const snap = computeSnapshot(payload.bars, modeIdx);
  renderStats(snap, state.mode);

  const wrap = document.getElementById("chart-wrap");
  wrap.innerHTML = renderChart(payload.bars, modeIdx, label, color);
  document.getElementById("chart-note").textContent =
    `£1 invested ${snap.firstDate} · ${payload.bars.length} trading days`;
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
