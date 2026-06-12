/* Instruments reference — one row per logical exposure.
   Loads the registry-derived reference.json (a single fetch), renders a
   sortable, filterable table. Reuses the league-table styling and the shared
   escapeHtml. No price computation here — this is a catalog view. */

import { escapeHtml } from "./strategy-engine.js";

const DATA_URL = "data/reference.json";

const state = {
  category: "all",
  surface:  "all",
  coverage: "all",
  q:        "",
  sortKey:  "name",
  sortDir:  "asc",
};

let instruments = [];
let builtAt = null;

/* ---------- helpers ---------- */

function surfaceKey(inst){
  const web = inst.surfaces.includes("web");
  const res = inst.surfaces.includes("research");
  if(web && res) return "both";
  if(web) return "web";
  if(res) return "research";
  return "none";
}

function surfaceLabel(key){
  return { web:"WEB", research:"RESEARCH", both:"WEB + RESEARCH", none:"—" }[key] || "—";
}

/* Decorate each instrument with the derived keys the table sorts/filters on. */
function decorate(inst){
  const sk = surfaceKey(inst);
  return {
    ...inst,
    surf_key:     sk,
    surfaces_str: surfaceLabel(sk),
    last_date:    inst.last_date || "",
  };
}

/* ---------- filtering ---------- */

function applyFilters(rows){
  const q = state.q.trim().toLowerCase();
  return rows.filter(r => {
    if(state.category !== "all" && r.category !== state.category) return false;
    if(state.surface === "web"      && !r.surfaces.includes("web"))      return false;
    if(state.surface === "research" && !r.surfaces.includes("research")) return false;
    if(state.surface === "both"     && r.surf_key !== "both")            return false;
    if(state.coverage === "full"    && !(r.n_strategies > 0 && r.covered === r.n_strategies)) return false;
    if(state.coverage === "partial" && r.covered === r.n_strategies)     return false;
    if(q){
      const hay = `${r.name} ${r.slug} ${r.category} ${r.group || ""}`.toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  });
}

function sortRows(rows){
  const m = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[state.sortKey], vb = b[state.sortKey];
    if(typeof va === "string" || typeof vb === "string"){
      // Empty strings (e.g. missing last_date) sink to the bottom.
      if(va === "" && vb === "") return 0;
      if(va === "") return 1;
      if(vb === "") return -1;
      return String(va).localeCompare(String(vb)) * m;
    }
    return (va - vb) * m;
  });
}

/* ---------- render ---------- */

function renderControls(){
  setSegActive("surface-seg",  state.surface);
  setSegActive("coverage-seg", state.coverage);
}

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderHeadIndicators(){
  for(const th of document.querySelectorAll("#table-head .sort-able")){
    const isActive = th.dataset.key === state.sortKey;
    th.classList.toggle("sort-asc",  isActive && state.sortDir === "asc");
    th.classList.toggle("sort-desc", isActive && state.sortDir === "desc");
  }
}

function nameCell(r){
  const name = `<span class="ix-name">${escapeHtml(r.name)}</span><span class="ix-ticker">${escapeHtml(r.slug)}</span>`;
  // Only web instruments live on the price tracker; deep-link those only.
  if(r.surfaces.includes("web")){
    return `<td class="ix"><a href="instrument.html?instrument=${encodeURIComponent(r.slug)}">${name}</a></td>`;
  }
  return `<td class="ix">${name}</td>`;
}

function coverageCell(r){
  const full = r.n_strategies > 0 && r.covered === r.n_strategies;
  const none = r.covered === 0;
  const cls  = full ? "cell-pos" : (none ? "cell-neg" : "");
  return `<td class="${cls}">${r.covered} / ${r.n_strategies}</td>`;
}

function renderTable(){
  const rows = sortRows(applyFilters(instruments));
  const body = document.getElementById("table-body");

  if(rows.length === 0){
    body.innerHTML = `<tr><td colspan="7" class="empty">No instruments match these filters.</td></tr>`;
  } else {
    body.innerHTML = rows.map(r => `<tr>
      ${nameCell(r)}
      <td class="dim">${escapeHtml(r.category)}</td>
      <td class="dim">${escapeHtml(r.group || "—")}</td>
      <td><span class="pill ${r.surf_key}">${r.surfaces_str}</span></td>
      <td>${r.symbol_count}</td>
      ${coverageCell(r)}
      <td class="${r.last_date ? "" : "dim"}">${r.last_date || "—"}</td>
    </tr>`).join("");
  }

  document.getElementById("table-note").textContent =
    `${rows.length} of ${instruments.length} instruments`;
  renderHeadIndicators();
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

function populateCategories(){
  const cats = [...new Set(instruments.map(i => i.category))].sort();
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
  for(const segId of ["surface-seg", "coverage-seg"]){
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
    instruments = data.instruments.map(decorate);
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
