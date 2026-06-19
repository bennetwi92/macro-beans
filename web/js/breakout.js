/* Breakout — strategy page logic.
   Loads daily bars for the selected instrument, finds every break of an N-day
   high (or low), measures what happened over the next 1 / 5 / 10 days, and
   renders the scoreboard + event log. All computation is local to the browser;
   data is pre-built JSON served from web/data/. */

import {
  findBreakoutEvents,
  computeStats,
  fmt, fmtInt, cls,
  escapeHtml,
} from "./strategy-engine.js";

const DATA_BASE = "data";

const state = {
  instrument: "spx",
  direction:  "up",     // 'up' = new high, 'down' = new low
  lookback:   20,       // trailing trading days the extreme is measured over
  entry:      "close",
  range:      "5y",
};

const cache = new Map();              // slug -> {meta, bars}
let instruments = [];                  // menu entries
let builtAt = null;                    // ISO string from instruments.json

/* ---------- data loaders ---------- */

async function loadInstruments(){
  const res = await fetch(`${DATA_BASE}/instruments.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load instruments.json (${res.status})`);
  const j = await res.json();
  instruments = j.instruments;
  builtAt = j.built_at;
}

// Preselect an instrument from ?instrument=<slug> (e.g. a scanner deep-link).
function applyInstrumentParam(){
  const slug = new URLSearchParams(location.search).get("instrument");
  if(slug && instruments.some(i => i.slug === slug)) state.instrument = slug;
}

async function loadBars(slug){
  if(cache.has(slug)) return cache.get(slug);
  const res = await fetch(`${DATA_BASE}/${slug}.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load ${slug}.json (${res.status})`);
  const j = await res.json();
  cache.set(slug, j);
  return j;
}

/* ---------- rendering ---------- */

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

function renderControlsState(){
  setSegActive("direction-seg", state.direction);
  setSegActive("entry-seg",     state.entry);
  setSegActive("range-seg",     state.range);

  document.getElementById("lookback-val").textContent = `${state.lookback} DAYS`;
  document.getElementById("lookback-range").value = state.lookback;
}

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderSummary(stats){
  const rows = [
    { label:"WINS",        sub:s => `out of ${s.n} events`, get:s => `${s.wins} / ${s.n}`, color:() => "" },
    { label:"WIN RATE",    sub:() => "how often it worked",  get:s => `${fmtInt(s.rate)}%`, color:s => s.rate >= 50 ? "pos" : "neg" },
    { label:"AVG RETURN",  sub:() => "per event",            get:s => fmt(s.avg),           color:s => s.avg > 0 ? "pos" : "neg" },
    { label:"MEDIAN",      sub:() => "the typical event",    get:s => fmt(s.med),           color:s => s.med > 0 ? "pos" : "neg" },
    { label:"WORST TRADE", sub:() => "the risk you take",    get:s => fmt(s.worst),         color:() => "neg" },
  ];
  document.getElementById("score-body").innerHTML = rows.map(r =>
    `<tr><th>${r.label}<span class='sub'>${r.sub(stats[0])}</span></th>` +
    stats.map(s => `<td class='${r.color(s)}'>${s.n === 0 ? "—" : r.get(s)}</td>`).join("") +
    `</tr>`
  ).join("");
}

function renderLog(events){
  const body = document.getElementById("log-body");
  const count = document.getElementById("log-count");
  if(events.length === 0){
    body.innerHTML = `<tr class="empty"><td colspan="5">No breakouts match these settings. Shorten the look-back or widen the date range.</td></tr>`;
    count.textContent = "0 events";
    return;
  }
  body.innerHTML = [...events].reverse().map(e =>
    `<tr><td>${e.date}</td>` +
    `<td class='trig'>${fmt(e.trig)}</td>` +
    `<td class='${cls(e.d1)}'>${fmt(e.d1)}</td>` +
    `<td class='${cls(e.d2)}'>${fmt(e.d2)}</td>` +
    `<td class='${cls(e.d3)}'>${fmt(e.d3)}</td></tr>`
  ).join("");
  count.textContent = `${events.length} event${events.length === 1 ? "" : "s"} found`;
}

function renderBuiltLine(){
  if(!builtAt) return;
  document.getElementById("built-line").textContent =
    `MACRO BEANS · DATA REFRESHED ${builtAt.slice(0, 10)}`;
}

/* ---------- main update loop ---------- */

async function update(){
  renderControlsState();
  const payload = await loadBars(state.instrument);
  const events  = findBreakoutEvents(payload.bars, state);
  const stats   = computeStats(events);
  renderSummary(stats);
  renderLog(events);
}

/* ---------- wiring ---------- */

function wireControls(){
  document.getElementById("instrument-select").addEventListener("change", e => {
    state.instrument = e.target.value;
    updateInstrumentLabel();
    update();
  });

  for(const segId of ["direction-seg","entry-seg","range-seg"]){
    document.getElementById(segId).addEventListener("click", e => {
      const btn = e.target.closest(".opt");
      if(!btn) return;
      const key = segId.split("-")[0];
      state[key] = btn.dataset.value;
      update();
    });
  }

  document.getElementById("lookback-range").addEventListener("input", e => {
    state.lookback = parseInt(e.target.value, 10);
    renderControlsState();
  });
  document.getElementById("lookback-range").addEventListener("change", update);
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
    document.getElementById("log-count").textContent = `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
