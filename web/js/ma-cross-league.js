/* Moving-Average Cross — league table page logic.
   Loads all instrument bars in parallel, computes per-instrument moving-average
   cross stats from the same shared settings, renders a sortable comparison
   table. Re-uses the strategy-engine so numbers match the single-instrument
   page. The d1/d2/d3 stat slots map to the 5 / 10 / 20 day horizons; this table
   surfaces the day-5 and day-20 columns. */

import {
  findCrossEvents,
  computeStats,
  fmt, fmtInt, cls,
  escapeHtml,
} from "./strategy-engine.js";

const DATA_BASE = "data";

const state = {
  direction: "up",
  period:    200,
  entry:     "close",
  range:     "5y",
  sortKey:   "avg_d3",   // avg over the 20-day horizon
  sortDir:   "desc",
};

let instruments = [];
const cache = new Map();
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

/* ---------- per-instrument row builder ---------- */

function computeRow(inst){
  const payload = cache.get(inst.slug);
  if(!payload) return null;
  const events = findCrossEvents(payload.bars, state);
  const stats  = computeStats(events);
  const d5 = stats[0], d20 = stats[2];
  return {
    slug:     inst.slug,
    name:     inst.name,
    ticker:   inst.ticker,
    n:        d5.n,
    rate_d1:  d5.rate,
    avg_d1:   d5.avg,
    rate_d3:  d20.rate,
    avg_d3:   d20.avg,
    worst_d3: d20.worst,
  };
}

function sortRows(rows){
  const m = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[state.sortKey], vb = b[state.sortKey];
    if(typeof va === "string") return va.localeCompare(vb) * m;
    if(!Number.isFinite(va) && !Number.isFinite(vb)) return 0;
    if(!Number.isFinite(va)) return 1;
    if(!Number.isFinite(vb)) return -1;
    return (va - vb) * m;
  });
}

/* ---------- render ---------- */

function renderControlsState(){
  setSegActive("direction-seg", state.direction);
  setSegActive("entry-seg",     state.entry);
  setSegActive("range-seg",     state.range);

  document.getElementById("period-val").textContent = `${state.period} DAYS`;
  document.getElementById("period-range").value = state.period;
}

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderHeadIndicators(){
  for(const th of document.querySelectorAll("#league-head .sort-able")){
    const isActive = th.dataset.key === state.sortKey;
    th.classList.toggle("sort-asc",  isActive && state.sortDir === "asc");
    th.classList.toggle("sort-desc", isActive && state.sortDir === "desc");
  }
}

function renderTable(){
  const rows = instruments.map(computeRow).filter(Boolean);
  const sorted = sortRows(rows);
  const body = document.getElementById("league-body");

  body.innerHTML = sorted.map(r => {
    const nCls = (r.n < 10) ? "dim" : "";
    const rateD1cls = (r.n === 0) ? "" : (r.rate_d1 >= 50 ? "cell-pos" : "cell-neg");
    const rateD3cls = (r.n === 0) ? "" : (r.rate_d3 >= 50 ? "cell-pos" : "cell-neg");
    return `<tr>
      <td class="ix"><a href="instrument.html?instrument=${encodeURIComponent(r.slug)}"><span class="ix-name">${escapeHtml(r.name)}</span><span class="ix-ticker">${escapeHtml(r.ticker)}</span></a></td>
      <td class="${nCls}">${r.n}</td>
      <td class="${rateD1cls}">${r.n === 0 ? "—" : fmtInt(r.rate_d1) + "%"}</td>
      <td class="${cls(r.avg_d1)}">${fmt(r.avg_d1)}</td>
      <td class="${rateD3cls}">${r.n === 0 ? "—" : fmtInt(r.rate_d3) + "%"}</td>
      <td class="${cls(r.avg_d3)}">${fmt(r.avg_d3)}</td>
      <td class="${Number.isFinite(r.worst_d3) ? 'cell-neg' : ''}">${fmt(r.worst_d3)}</td>
    </tr>`;
  }).join("");

  const totalEvents = rows.reduce((a, r) => a + r.n, 0);
  document.getElementById("league-note").textContent =
    `${rows.length} instruments · ${totalEvents} total events`;
  renderHeadIndicators();
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- wiring ---------- */

function update(){
  renderControlsState();
  renderTable();
}

function wireControls(){
  for(const segId of ["direction-seg", "entry-seg", "range-seg"]){
    document.getElementById(segId).addEventListener("click", e => {
      const btn = e.target.closest(".opt");
      if(!btn) return;
      const key = segId.split("-")[0];
      state[key] = btn.dataset.value;
      update();
    });
  }
  document.getElementById("period-range").addEventListener("input", e => {
    state.period = parseInt(e.target.value, 10);
    renderControlsState();
  });
  document.getElementById("period-range").addEventListener("change", update);
}

function wireSort(){
  document.getElementById("league-head").addEventListener("click", e => {
    const th = e.target.closest("th.sort-able");
    if(!th) return;
    const key = th.dataset.key;
    if(state.sortKey === key){
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortKey = key;
      state.sortDir = th.dataset.defaultDir || "desc";
    }
    renderTable();
  });
}

/* ---------- boot ---------- */

(async function init(){
  try{
    await loadAll();
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
