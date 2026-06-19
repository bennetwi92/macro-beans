/* Cheap or Dear — value screen page logic.
   Loads every instrument's bars in parallel (the league pattern) and, for each,
   computes a price-based "cheap vs its own history" snapshot: distance below
   the 1-year high, distance from the 200-day average, position in the 5-year
   range, plus the average forward 1-month return on past days the market sat
   below its average (the only forward-looking, evidence column). Ranked and
   sortable. All computation is local to the browser; data is pre-built JSON. */

import {
  valueMetrics,
  fmt, fmtInt, cls,
  escapeHtml,
} from "./strategy-engine.js";

const DATA_BASE = "data";

// "cheap" evidence needs a workable sample of below-average days to mean much.
const MIN_CHEAP_DAYS = 30;

const state = {
  sortKey: "vsSma200",   // cheapest-versus-average first
  sortDir: "asc",
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
  const m = valueMetrics(payload.bars);
  return {
    slug:         inst.slug,
    name:         inst.name,
    ticker:       inst.ticker,
    offHigh52:    m.offHigh52,
    vsSma200:     m.vsSma200,
    rangePos5y:   m.rangePos5y,
    fwdWhenCheap: m.fwdWhenCheap,
    nCheap:       m.nCheap,
  };
}

function sortRows(rows){
  const m = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[state.sortKey], vb = b[state.sortKey];
    if(typeof va === "string") return va.localeCompare(vb) * m;
    if(!Number.isFinite(va) && !Number.isFinite(vb)) return 0;
    if(!Number.isFinite(va)) return 1;   // NaN always sinks
    if(!Number.isFinite(vb)) return -1;
    return (va - vb) * m;
  });
}

/* ---------- render ---------- */

function renderHeadIndicators(){
  for(const th of document.querySelectorAll("#screen-head .sort-able")){
    const isActive = th.dataset.key === state.sortKey;
    th.classList.toggle("sort-asc",  isActive && state.sortDir === "asc");
    th.classList.toggle("sort-desc", isActive && state.sortDir === "desc");
  }
}

function renderTable(){
  const rows = sortRows(instruments.map(computeRow).filter(Boolean));
  const body = document.getElementById("screen-body");

  body.innerHTML = rows.map(r => {
    const thin = !Number.isFinite(r.fwdWhenCheap) || r.nCheap < MIN_CHEAP_DAYS;
    const rangeTxt = Number.isFinite(r.rangePos5y) ? `${fmtInt(r.rangePos5y)}%` : "—";
    return `<tr>
      <td class="ix"><a href="instrument.html?instrument=${encodeURIComponent(r.slug)}"><span class="ix-name">${escapeHtml(r.name)}</span><span class="ix-ticker">${escapeHtml(r.ticker)}</span></a></td>
      <td>${fmt(r.offHigh52)}</td>
      <td>${fmt(r.vsSma200)}</td>
      <td class="dim">${rangeTxt}</td>
      <td class="${thin ? "dim" : cls(r.fwdWhenCheap)}">${Number.isFinite(r.fwdWhenCheap) ? fmt(r.fwdWhenCheap) + (thin ? " ⚠" : "") : "—"}</td>
    </tr>`;
  }).join("");

  document.getElementById("screen-note").textContent =
    `${rows.length} markets${builtAt ? ` · as of ${builtAt.slice(0, 10)}` : ""}`;
  renderHeadIndicators();
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- wiring ---------- */

function wireSort(){
  document.getElementById("screen-head").addEventListener("click", e => {
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
    wireSort();
    renderTable();
  } catch(err){
    document.getElementById("screen-note").textContent =
      `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
