/* Best Months — league grid page logic.
   Loads every instrument's bars in parallel, computes each one's 12 monthly
   averages, and lays them out as a colour-shaded instrument × month grid.
   Re-uses the seasonality-engine so the numbers match the single-instrument
   page. Click a month header to rank instruments by that month. */

import { computeMonths, MONTH_NAMES } from "./seasonality-engine.js";
import { fmt, fmtInt, escapeHtml } from "./strategy-engine.js";

const DATA_BASE = "data";

const state = {
  metric:  "avg",     // 'avg' | 'green'
  range:   "10y",     // '10y' | 'all'
  sortKey: "name",    // 'name' | a month number 1-12
  sortDir: "asc",
};

let instruments = [];
const cache = new Map();          // slug -> {meta, bars}
const monthsCache = new Map();    // `${slug}|${range}` -> [12 month stats]
let builtAt = null;

/* ---------- data loading ---------- */

async function loadAll(){
  const menuRes = await fetch(`${DATA_BASE}/instruments.json`, {cache:"no-cache"});
  if(!menuRes.ok) throw new Error(`failed to load instruments.json (${menuRes.status})`);
  const menu = await menuRes.json();
  instruments = menu.instruments;
  builtAt = menu.built_at;

  await Promise.all(instruments.map(async inst => {
    const res = await fetch(`${DATA_BASE}/${inst.slug}.json`, {cache:"no-cache"});
    if(!res.ok) throw new Error(`failed to load ${inst.slug}.json (${res.status})`);
    cache.set(inst.slug, await res.json());
  }));
}

function monthsFor(inst){
  const key = `${inst.slug}|${state.range}`;
  if(monthsCache.has(key)) return monthsCache.get(key);
  const payload = cache.get(inst.slug);
  const months = computeMonths(payload.bars, state);
  monthsCache.set(key, months);
  return months;
}

// Signed magnitude that drives a cell's colour for the active metric.
function magnitude(m){
  if(m.n === 0) return NaN;
  return state.metric === "avg" ? m.avg : (m.green - 50);
}

/* ---------- render ---------- */

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderHead(){
  const cells = [`<th class="sort-able ix-col" data-key="name" data-default-dir="asc">INSTRUMENT</th>`];
  for(let m = 1; m <= 12; m++){
    cells.push(`<th class="sort-able" data-key="${m}" data-default-dir="desc">${MONTH_NAMES[m-1].toUpperCase()}</th>`);
  }
  document.getElementById("league-head").innerHTML = cells.join("");
}

function renderHeadIndicators(){
  for(const th of document.querySelectorAll("#league-head .sort-able")){
    const isActive = th.dataset.key === String(state.sortKey);
    th.classList.toggle("sort-asc",  isActive && state.sortDir === "asc");
    th.classList.toggle("sort-desc", isActive && state.sortDir === "desc");
  }
}

function sortInstruments(rows){
  const m = state.sortDir === "asc" ? 1 : -1;
  if(state.sortKey === "name"){
    return [...rows].sort((a, b) => a.inst.name.localeCompare(b.inst.name) * m);
  }
  const mi = Number(state.sortKey) - 1;
  return [...rows].sort((a, b) => {
    const va = magnitude(a.months[mi]), vb = magnitude(b.months[mi]);
    if(!Number.isFinite(va) && !Number.isFinite(vb)) return 0;
    if(!Number.isFinite(va)) return 1;
    if(!Number.isFinite(vb)) return -1;
    return (va - vb) * m;
  });
}

function renderGrid(){
  // Build rows, find a global colour reference so shading is comparable.
  const rows = instruments.map(inst => ({ inst, months: monthsFor(inst) }));
  let maxMag = 0.0001;
  for(const r of rows){
    for(const mo of r.months){
      const g = magnitude(mo);
      if(Number.isFinite(g)) maxMag = Math.max(maxMag, Math.abs(g));
    }
  }

  const sorted = sortInstruments(rows);
  const body = document.getElementById("league-body");

  body.innerHTML = sorted.map(({ inst, months }) => {
    const cells = months.map(mo => {
      if(mo.n === 0) return `<td class="hl-cell thin">—</td>`;
      const g = magnitude(mo);
      const pos = g >= 0;
      const i = Math.min(1, Math.abs(g) / maxMag).toFixed(3);
      const txt = state.metric === "avg" ? fmt(mo.avg) : `${fmtInt(mo.green)}%`;
      const thin = mo.n < 8 ? " thin" : "";
      return `<td class="hl-cell ${pos ? "pos" : "neg"}${thin}" style="--i:${i}">${txt}</td>`;
    }).join("");
    return `<tr>
      <td class="ix"><span class="ix-name">${escapeHtml(inst.name)}</span><span class="ix-ticker">${escapeHtml(inst.ticker)}</span></td>
      ${cells}
    </tr>`;
  }).join("");

  document.getElementById("league-note").textContent =
    `${rows.length} instruments · shaded by ${state.metric === "avg" ? "average return" : "win rate"}`;
  renderHeadIndicators();
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- wiring ---------- */

function update(){
  setSegActive("metric-seg", state.metric);
  setSegActive("range-seg",  state.range);
  renderGrid();
}

function wireControls(){
  for(const segId of ["metric-seg", "range-seg"]){
    document.getElementById(segId).addEventListener("click", e => {
      const btn = e.target.closest(".opt");
      if(!btn) return;
      state[segId.split("-")[0]] = btn.dataset.value;
      update();
    });
  }
}

function wireSort(){
  document.getElementById("league-head").addEventListener("click", e => {
    const th = e.target.closest("th.sort-able");
    if(!th) return;
    const key = th.dataset.key;
    if(String(state.sortKey) === key){
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key === "name" ? "name" : Number(key);
      state.sortDir = th.dataset.defaultDir || "desc";
    }
    renderGrid();
  });
}

/* ---------- boot ---------- */

(async function init(){
  try{
    await loadAll();
    renderHead();
    renderBuiltLine();
    wireControls();
    wireSort();
    update();
  } catch(err){
    document.getElementById("league-note").textContent =
      `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
