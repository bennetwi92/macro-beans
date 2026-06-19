/* Symbols reference — one row per concrete ticker.
   An instrument with two symbols (e.g. Gold: SGLN.L web + GLD research) shows
   as two rows. Loads the registry-derived reference.json, renders a sortable,
   filterable table. Web symbols carry freshness; research symbols don't (the
   static site can't see the DuckDB cache), so their BARS / LAST DATA read "—". */

import { escapeHtml } from "./strategy-engine.js";

const DATA_URL = "data/reference.json";

const state = {
  venue:    "all",
  surface:  "all",
  category: "all",
  q:        "",
  sortKey:  "ticker",
  sortDir:  "asc",
};

let symbols = [];
let builtAt = null;

/* ---------- helpers ---------- */

function decorate(sym){
  return {
    ...sym,
    last_date: sym.last_date || "",
    n_bars:    Number.isFinite(sym.n_bars) ? sym.n_bars : null,
  };
}

/* ---------- filtering ---------- */

function applyFilters(rows){
  const q = state.q.trim().toLowerCase();
  return rows.filter(r => {
    if(state.venue    !== "all" && r.venue   !== state.venue)    return false;
    if(state.surface  !== "all" && r.surface !== state.surface)  return false;
    if(state.category !== "all" && r.category !== state.category) return false;
    if(q){
      const hay = `${r.ticker} ${r.instrument_name} ${r.instrument_slug}`.toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
}

function sortRows(rows){
  const m = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    let va = a[state.sortKey], vb = b[state.sortKey];
    // Nulls (missing bars) sink to the bottom regardless of direction.
    const aNull = va === "" || va === null;
    const bNull = vb === "" || vb === null;
    if(aNull && bNull) return 0;
    if(aNull) return 1;
    if(bNull) return -1;
    if(typeof va === "string" || typeof vb === "string"){
      return String(va).localeCompare(String(vb)) * m;
    }
    return (va - vb) * m;
  });
}

/* ---------- render ---------- */

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderControls(){
  setSegActive("venue-seg",   state.venue);
  setSegActive("surface-seg", state.surface);
}

function renderHeadIndicators(){
  for(const th of document.querySelectorAll("#table-head .sort-able")){
    const isActive = th.dataset.key === state.sortKey;
    th.classList.toggle("sort-asc",  isActive && state.sortDir === "asc");
    th.classList.toggle("sort-desc", isActive && state.sortDir === "desc");
  }
}

function instrumentCell(r){
  const inner = `<span class="ix-name">${escapeHtml(r.instrument_name)}</span><span class="ix-ticker">${escapeHtml(r.instrument_slug)}</span>`;
  // Only web instruments live on the price tracker.
  if(r.surface === "web"){
    return `<td class="ix"><a href="instrument.html?instrument=${encodeURIComponent(r.instrument_slug)}">${inner}</a></td>`;
  }
  return `<td class="ix">${inner}</td>`;
}

function renderTable(){
  const rows = sortRows(applyFilters(symbols));
  const body = document.getElementById("table-body");

  if(rows.length === 0){
    body.innerHTML = `<tr><td colspan="7" class="empty">No symbols match these filters.</td></tr>`;
  } else {
    body.innerHTML = rows.map(r => `<tr>
      <td class="trig">${escapeHtml(r.ticker)}</td>
      ${instrumentCell(r)}
      <td><span class="pill">${escapeHtml(r.venue)}</span></td>
      <td><span class="pill ${r.surface}">${r.surface.toUpperCase()}</span></td>
      <td class="dim">${escapeHtml(r.category)}</td>
      <td class="${r.n_bars === null ? "dim" : ""}">${r.n_bars === null ? "—" : r.n_bars.toLocaleString()}</td>
      <td class="${r.last_date ? "" : "dim"}">${r.last_date || "—"}</td>
    </tr>`).join("");
  }

  document.getElementById("table-note").textContent =
    `${rows.length} of ${symbols.length} symbols`;
  renderHeadIndicators();
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

function populateCategories(){
  const cats = [...new Set(symbols.map(s => s.category))].sort();
  const sel = document.getElementById("category-select");
  for(const c of cats){
    const opt = document.createElement("option");
    opt.value = c; opt.textContent = c;
    sel.appendChild(opt);
  }
}

/* ---------- wiring ---------- */

function update(){
  renderControls();
  renderTable();
}

function wireControls(){
  for(const segId of ["venue-seg", "surface-seg"]){
    document.getElementById(segId).addEventListener("click", e => {
      const btn = e.target.closest(".opt");
      if(!btn) return;
      state[segId.split("-")[0]] = btn.dataset.value;
      update();
    });
  }
  document.getElementById("category-select").addEventListener("change", e => {
    state.category = e.target.value;
    update();
  });
  document.getElementById("find-input").addEventListener("input", e => {
    state.q = e.target.value;
    renderTable();
  });
}

function wireSort(){
  document.getElementById("table-head").addEventListener("click", e => {
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
    const res = await fetch(DATA_URL, {cache:"no-cache"});
    if(!res.ok) throw new Error(`failed to load reference.json (${res.status})`);
    const data = await res.json();
    symbols = data.symbols.map(decorate);
    builtAt = data.built_at;
    populateCategories();
    renderBuiltLine();
    wireControls();
    wireSort();
    update();
  } catch(err){
    document.getElementById("table-note").textContent = `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
