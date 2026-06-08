/* Buy the Bounce — strategy page logic.
   Loads daily bars for the selected instrument, finds events that match the
   user's filter (direction/threshold/entry/range), computes summary stats,
   and renders the verdict + scoreboard + event log. All computation is local
   to the browser; data is pre-built JSON served from web/data/. */

const DATA_BASE = "data";
const HORIZONS = [1, 2, 3];

const state = {
  instrument: "spx",
  direction:  "down",
  threshold:  2.0,   // absolute percent; sign comes from direction
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

async function loadBars(slug){
  if(cache.has(slug)) return cache.get(slug);
  const res = await fetch(`${DATA_BASE}/${slug}.json`, {cache:"no-cache"});
  if(!res.ok) throw new Error(`failed to load ${slug}.json (${res.status})`);
  const j = await res.json();
  cache.set(slug, j);
  return j;
}

/* ---------- event detection + stats ---------- */

/* bars: [[date_iso, open, close], ...]
   opts: {direction:'down'|'up', threshold:pct (positive number), entry:'close'|'open', range:'5y'|'all'}
   returns: [{date, trig, d1, d2, d3}] in chronological order. */
function findEvents(bars, opts){
  const thr = opts.threshold / 100;
  const sign = opts.direction === "down" ? -1 : 1;
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const needed = opts.entry === "open" ? 4 : 3;     // bars after t we need
  const events = [];

  for(let i = 1; i < bars.length - needed; i++){
    const [date, , close]      = bars[i];
    const prevClose            = bars[i-1][2];
    const trig                 = close / prevClose - 1;
    if(sign === -1 && trig > -thr) continue;
    if(sign === +1 && trig < +thr) continue;
    if(minDate && date < minDate) continue;

    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){
      entryPrice    = close;
      exitIndexBase = i;                // exits are i+1, i+2, i+3
    } else {
      entryPrice    = bars[i+1][1];     // next day's open
      exitIndexBase = i+1;              // exits are i+2, i+3, i+4
    }
    const ds = HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);

    events.push({
      date,
      trig: trig * 100,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
    });
  }
  return events;
}

function yearsAgo(bars, n){
  const lastDate = bars[bars.length - 1][0];
  const [Y, M, D] = lastDate.split("-").map(Number);
  return `${Y - n}-${String(M).padStart(2,"0")}-${String(D).padStart(2,"0")}`;
}

function computeStats(events){
  return HORIZONS.map((_, idx) => {
    const key = ["d1","d2","d3"][idx];
    const vals = events.map(e => e[key]);
    const n = vals.length;
    if(n === 0) return {n:0, wins:0, rate:NaN, avg:NaN, med:NaN, worst:NaN, best:NaN};
    const wins = vals.filter(v => v > 0).length;
    return {
      n, wins,
      rate:  wins / n * 100,
      avg:   vals.reduce((a,b)=>a+b,0) / n,
      med:   median(vals),
      worst: Math.min(...vals),
      best:  Math.max(...vals),
    };
  });
}

function median(arr){
  const s = [...arr].sort((a,b)=>a-b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m-1] + s[m]) / 2;
}

/* ---------- formatting ---------- */

const fmt = v => {
  if(!Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : (v < 0 ? "−" : "");
  return sign + Math.abs(v).toFixed(1) + "%";
};
const cls = v => !Number.isFinite(v) ? "" : (v > 0 ? "cell-pos" : (v < 0 ? "cell-neg" : ""));
const fmtInt = v => Number.isFinite(v) ? Math.round(v).toString() : "—";

/* ---------- rendering ---------- */

function renderInstrumentMenu(){
  const sel = document.getElementById("instrument-select");
  sel.innerHTML = instruments.map(i =>
    `<option value="${i.slug}">${i.label}</option>`
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
  const badge = document.getElementById("strat-badge");
  if(badge) badge.innerHTML = `${escapeHtml(inst.label)}<br>${escapeHtml(inst.sublabel)}`;
}

function renderControlsState(){
  // direction / entry / range chips
  setSegActive("direction-seg", state.direction);
  setSegActive("entry-seg",     state.entry);
  setSegActive("range-seg",     state.range);

  // threshold slider value + sign + track ends
  const sign = state.direction === "down" ? "−" : "+";
  const val  = document.getElementById("threshold-val");
  val.textContent = `${sign}${state.threshold.toFixed(1)}%`;
  val.classList.toggle("up", state.direction === "up");

  document.getElementById("track-low").textContent  = `${sign}1%`;
  document.getElementById("track-high").textContent = `${sign}6%`;

  document.getElementById("threshold-range").value = state.threshold;
}

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderSummary(stats){
  const rows = [
    { label:"WINS",        sub:s => `out of ${s.n} events`,    get:s => `${s.wins} / ${s.n}`,   color:() => "" },
    { label:"WIN RATE",    sub:() => "how often it worked",    get:s => `${fmtInt(s.rate)}%`,    color:s => s.rate >= 50 ? "pos" : "neg" },
    { label:"AVG RETURN",  sub:() => "per event",              get:s => fmt(s.avg),              color:s => s.avg > 0 ? "pos" : "neg" },
    { label:"MEDIAN",      sub:() => "the typical event",      get:s => fmt(s.med),              color:s => s.med > 0 ? "pos" : "neg" },
    { label:"WORST TRADE", sub:() => "the risk you take",      get:s => fmt(s.worst),            color:() => "neg" },
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
    body.innerHTML = `<tr class="empty"><td colspan="5">No events match these settings. Loosen the threshold or widen the date range.</td></tr>`;
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

function renderVerdict(meta, events, stats){
  const vEl = document.getElementById("verdict");
  const tEl = document.getElementById("verdict-text");
  const mEl = document.getElementById("verdict-meta");
  if(!vEl || !tEl || !mEl) return;     // verdict section is optional
  const n = events.length;
  const dirWord = state.direction === "down" ? "fell" : "rose";
  const dirMove = state.direction === "down" ? "drop" : "spike";
  const entryWord = state.entry === "close" ? "at the close" : "at the next day's open";
  const periodWord = state.range === "5y" ? "the last 5 years" : "the full history";

  vEl.classList.remove("warn");
  if(n === 0){
    vEl.classList.add("warn");
    tEl.innerHTML = `<b>No events</b> match these settings in ${escapeHtml(periodWord)}. Loosen the move threshold or widen the date range.`;
    mEl.textContent = "Nothing to summarise yet.";
    return;
  }
  if(n < 10){
    vEl.classList.add("warn");
    tEl.innerHTML = `Only <b>${n} example${n===1?"":"s"}</b> match these settings — too few to draw any conclusion. Loosen the move threshold or widen the date range before reading anything into this.`;
    mEl.textContent = "Rule of thumb: you want at least 10–15 past events before a pattern means much.";
    return;
  }

  const d1 = stats[0], d3 = stats[2];
  const edgeWord =
    d1.avg >  0.10 ? "positive" :
    d1.avg < -0.10 ? "negative" : "barely there";

  tEl.innerHTML =
    `Over ${escapeHtml(periodWord)} ${escapeHtml(meta.label)} ${dirWord} more than `+
    `<b>${state.threshold.toFixed(1)}%</b> on <b>${n} days</b>. ` +
    `Entering ${escapeHtml(entryWord)} and holding one day was positive ` +
    `<b>${fmtInt(d1.rate)}% of the time</b>, for an average return of ` +
    `<b>${fmt(d1.avg)}</b>. The worst single trade lost <b>${fmt(d1.worst)}</b> — that's the real risk.`;

  mEl.innerHTML =
    `Edge is ${edgeWord} and the sample (${n} events) is ${n>=30?"big enough to take seriously":"workable but small"}. ` +
    `By day 3 the win rate was <b>${fmtInt(d3.rate)}%</b> with an average return of <b>${fmt(d3.avg)}</b>.`;
}

function renderBuiltLine(){
  if(!builtAt) return;
  const d = builtAt.slice(0, 10);
  document.getElementById("built-line").textContent = `MACRO BEANS · DATA REFRESHED ${d}`;
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"
  })[c]);
}

/* ---------- main update loop ---------- */

async function update(){
  renderControlsState();
  const payload = await loadBars(state.instrument);
  const events = findEvents(payload.bars, state);
  const stats  = computeStats(events);
  renderVerdict(payload.meta, events, stats);
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

  document.getElementById("threshold-range").addEventListener("input", e => {
    state.threshold = parseFloat(e.target.value);
    renderControlsState();
  });
  document.getElementById("threshold-range").addEventListener("change", () => {
    update();
  });
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
    document.getElementById("verdict-text").textContent =
      `Failed to load data: ${err.message}`;
    document.getElementById("verdict").classList.add("warn");
    console.error(err);
  }
})();
