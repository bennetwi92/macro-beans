/* Best Months — calendar-seasonality page logic.
   Loads daily bars for the selected instrument, collapses them into one return
   per calendar month, and shows how each month of the year has historically
   performed as a colour-shaded calendar plus a short summary. All computation
   is local to the browser; data is pre-built JSON served from web/data/. */

import { computeMonths, seasonHalves } from "./seasonality-engine.js";
import { fmt, fmtInt, escapeHtml } from "./strategy-engine.js";

const DATA_BASE = "data";

// Below this many years a month's average is mostly noise — flag it.
const THIN_YEARS = 8;

const state = {
  instrument: "spx",
  metric:     "avg",    // 'avg' = average return, 'green' = win rate
  range:      "10y",    // '10y' | 'all'
};

const cache = new Map();
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

async function loadBars(slug){
  if(cache.has(slug)) return cache.get(slug);
  const res = await fetch(`${DATA_BASE}/${slug}.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load ${slug}.json (${res.status})`);
  const j = await res.json();
  cache.set(slug, j);
  return j;
}

/* ---------- menu / controls ---------- */

function renderInstrumentMenu(){
  const sel = document.getElementById("instrument-select");
  const opt = i => `<option value="${i.slug}">${i.label}</option>`;
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
  const nameEl = document.getElementById("instrument-name");
  const tickerEl = document.getElementById("instrument-ticker");
  if(nameEl) nameEl.textContent = inst.name || inst.label;
  if(tickerEl) tickerEl.textContent = inst.ticker || "";
}

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderControlsState(){
  setSegActive("metric-seg", state.metric);
  setSegActive("range-seg",  state.range);
}

/* ---------- heatmap ---------- */

// Signed magnitude that drives a cell's colour for the active metric.
function cellMagnitude(m){
  return state.metric === "avg" ? m.avg : (m.green - 50);
}

function renderHeat(months){
  const live = months.filter(m => m.n > 0);
  const maxMag = Math.max(0.0001, ...live.map(m => Math.abs(cellMagnitude(m))));

  document.getElementById("heat").innerHTML = months.map(m => {
    if(m.n === 0){
      return `<div class="heat-cell thin">
        <div class="hc-mon">${m.name.toUpperCase()}</div>
        <div class="hc-big">—</div>
        <div class="hc-sub">no data</div>
      </div>`;
    }
    const mag = cellMagnitude(m);
    const pos = mag >= 0;
    const i = Math.min(1, Math.abs(mag) / maxMag).toFixed(3);
    const big = state.metric === "avg" ? fmt(m.avg) : `${fmtInt(m.green)}%`;
    const sub = state.metric === "avg"
      ? `${fmtInt(m.green)}% green · ${m.n} yr${m.n === 1 ? "" : "s"}`
      : `avg ${fmt(m.avg)} · ${m.n} yr${m.n === 1 ? "" : "s"}`;
    const thin = m.n < THIN_YEARS ? " thin" : "";
    return `<div class="heat-cell ${pos ? "pos" : "neg"}${thin}" style="--i:${i}">
      <div class="hc-mon">${m.name.toUpperCase()}</div>
      <div class="hc-big">${big}</div>
      <div class="hc-sub">${sub}</div>
    </div>`;
  }).join("");
}

/* ---------- summary ---------- */

function renderSummary(months, halves){
  const live = months.filter(m => m.n > 0);
  const note = document.getElementById("summary-note");
  if(live.length === 0){
    document.getElementById("stat-grid").innerHTML = "";
    note.textContent = "not enough history";
    return;
  }
  const years = Math.max(...live.map(m => m.n));
  note.textContent =
    `${years} year${years === 1 ? "" : "s"} of history · shaded by ${state.metric === "avg" ? "average return" : "win rate"}`;

  const strongest = live.reduce((a, b) => b.avg > a.avg ? b : a);
  const weakest   = live.reduce((a, b) => b.avg < a.avg ? b : a);
  const reliable  = live.reduce((a, b) => b.green > a.green ? b : a);
  const { winter, summer } = halves;
  const sellInMay = Number.isFinite(winter.avg) && Number.isFinite(summer.avg)
    ? (winter.avg > summer.avg)
    : null;

  const monthName = m => MONTH_FULL[m.m - 1];

  const cards = [
    {
      label: "STRONGEST MONTH",
      main:  monthName(strongest),
      mainCls: "pos",
      side:  fmt(strongest.avg),
      sideCls: strongest.avg > 0 ? "pos" : "neg",
      sub:   `up ${fmtInt(strongest.green)}% of ${strongest.n} years`,
    },
    {
      label: "WEAKEST MONTH",
      main:  monthName(weakest),
      mainCls: "neg",
      side:  fmt(weakest.avg),
      sideCls: weakest.avg > 0 ? "pos" : "neg",
      sub:   `up ${fmtInt(weakest.green)}% of ${weakest.n} years`,
    },
    {
      label: "MOST RELIABLE MONTH",
      main:  monthName(reliable),
      mainCls: "",
      side:  `${fmtInt(reliable.green)}% green`,
      sideCls: reliable.green >= 50 ? "pos" : "neg",
      sub:   `finished up the most often`,
    },
    {
      label: "SELL IN MAY?",
      main:  sellInMay == null ? "—" : (sellInMay ? "WORKS" : "NO EDGE"),
      mainCls: sellInMay ? "pos" : "",
      side:  Number.isFinite(winter.avg) ? `${fmt(winter.avg)} vs ${fmt(summer.avg)}` : "—",
      sideCls: "",
      sub:   `Nov–Apr vs May–Oct, average month`,
    },
  ];

  document.getElementById("stat-grid").innerHTML = cards.map(c => `
    <div class="stat">
      <div class="stat-label">${escapeHtml(c.label)}</div>
      <div class="stat-main ${c.mainCls}">${escapeHtml(c.main)}</div>
      <div class="stat-side ${c.sideCls}">${escapeHtml(c.side)}</div>
      <div class="stat-sub">${escapeHtml(c.sub)}</div>
    </div>
  `).join("");
}

const MONTH_FULL = ["January","February","March","April","May","June",
                    "July","August","September","October","November","December"];

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- main update ---------- */

async function update(){
  renderControlsState();
  const payload = await loadBars(state.instrument);
  const months  = computeMonths(payload.bars, state);
  const halves  = seasonHalves(payload.bars, state);
  renderHeat(months);
  renderSummary(months, halves);
}

/* ---------- wiring ---------- */

function wireControls(){
  document.getElementById("instrument-select").addEventListener("change", e => {
    state.instrument = e.target.value;
    updateInstrumentLabel();
    update();
  });
  for(const segId of ["metric-seg", "range-seg"]){
    document.getElementById(segId).addEventListener("click", e => {
      const btn = e.target.closest(".opt");
      if(!btn) return;
      const key = segId.split("-")[0];   // 'metric' | 'range'
      state[key] = btn.dataset.value;
      update();
    });
  }
}

/* ---------- boot ---------- */

(async function init(){
  try{
    await loadInstruments();
    renderInstrumentMenu();
    renderBuiltLine();
    wireControls();
    await update();
  } catch(err){
    document.getElementById("heat-note").textContent = `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
