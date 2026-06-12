/* Scanner — the "what's triggered right now" page.
   Loads every instrument's bars in parallel (the league-table pattern),
   tests each daily-event strategy's firing condition against the most
   recent bar, and lists only the setups that are live as of the last
   close. Each live signal carries the historical track record of that
   exact setup on that instrument, so a trigger is never shown without
   evidence. All computation is local to the browser; data is pre-built
   JSON served from web/data/. */

import {
  findEvents,
  findStreakEvents,
  liveBounce,
  liveStreak,
  computeStats,
  fmt, fmtInt, cls,
  escapeHtml,
} from "./strategy-engine.js";

const DATA_BASE = "data";

const state = {
  direction: "down",
  threshold: 2.0,    // bounce: single-day move, absolute %
  streak:    3,      // red/green streak: consecutive closes
  range:     "5y",   // track-record window
  sortKey:   "avg",
  sortDir:   "desc",
};

// The two daily-event strategies the scanner covers. Each knows how to
// detect a live signal, describe it, and look up its historical edge.
const STRATEGIES = [
  {
    key:   "bounce",
    label: "Buy the Bounce",
    page:  "buy-the-bounce.html",
    hold:  "3 days",
    detect(bars){ return liveBounce(bars, state); },
    signal(sig){ return fmt(sig.move) + " day"; },
    signalCls(sig){ return cls(sig.move); },
    stats(bars){
      const ev = findEvents(bars, {
        direction: state.direction, threshold: state.threshold,
        entry: "close", range: state.range,
      });
      return computeStats(ev)[2];   // 3-day horizon
    },
  },
  {
    key:   "streak",
    label: "Red Streak",
    page:  "red-streak.html",
    hold:  "5 days",
    detect(bars){ return liveStreak(bars, state); },
    signal(sig){
      const colour = state.direction === "down" ? "red" : "green";
      return `${sig.run} ${colour} closes`;
    },
    signalCls(){ return ""; },
    stats(bars){
      const ev = findStreakEvents(bars, {
        direction: state.direction, streak: state.streak,
        entry: "close", range: state.range,
      });
      return computeStats(ev)[2];   // 5-day horizon (STREAK_HORIZONS[2])
    },
  },
];

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

/* ---------- signal scan ---------- */

// Build one row per (instrument × strategy) that is firing on the latest bar.
function scanRows(){
  const rows = [];
  for(const inst of instruments){
    const payload = cache.get(inst.slug);
    if(!payload || !payload.bars || payload.bars.length < 2) continue;
    const bars = payload.bars;
    for(const strat of STRATEGIES){
      const sig = strat.detect(bars);
      if(!sig.triggered) continue;
      const st = strat.stats(bars);
      rows.push({
        slug:        inst.slug,
        name:        inst.name,
        ticker:      inst.ticker,
        strategy:    strat.label,
        page:        strat.page,
        signal:      strat.signal(sig),
        signalCls:   strat.signalCls(sig),
        hold:        strat.hold,
        rate:        st.rate,
        avg:         st.avg,
        n:           st.n,
      });
    }
  }
  return rows;
}

// Latest bar date across all loaded instruments — the session the scan is "as of".
function asOfDate(){
  let latest = "";
  for(const payload of cache.values()){
    const bars = payload && payload.bars;
    if(bars && bars.length){
      const d = bars[bars.length - 1][0];
      if(d > latest) latest = d;
    }
  }
  return latest;
}

/* ---------- sorting ---------- */

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
  setSegActive("range-seg",     state.range);

  const sign = state.direction === "down" ? "−" : "+";
  const tv = document.getElementById("threshold-val");
  tv.textContent = `${sign}${state.threshold.toFixed(1)}%`;
  tv.classList.toggle("up", state.direction === "up");
  document.getElementById("track-low").textContent  = `${sign}1%`;
  document.getElementById("track-high").textContent = `${sign}6%`;
  document.getElementById("threshold-range").value = state.threshold;

  const colour = state.direction === "down" ? "RED" : "GREEN";
  document.getElementById("streak-val").textContent = `${state.streak} ${colour} DAYS`;
  document.getElementById("streak-range").value = state.streak;
}

function setSegActive(segId, value){
  const seg = document.getElementById(segId);
  for(const opt of seg.querySelectorAll(".opt")){
    opt.classList.toggle("on", opt.dataset.value === value);
  }
}

function renderHeadIndicators(){
  for(const th of document.querySelectorAll("#scan-head .sort-able")){
    const isActive = th.dataset.key === state.sortKey;
    th.classList.toggle("sort-asc",  isActive && state.sortDir === "asc");
    th.classList.toggle("sort-desc", isActive && state.sortDir === "desc");
  }
}

function renderTable(){
  const rows = sortRows(scanRows());
  const body = document.getElementById("scan-body");
  const asOf = asOfDate();

  if(rows.length === 0){
    body.innerHTML =
      `<tr><td colspan="7" class="empty">No setups triggered as of ${escapeHtml(asOf) || "the last close"} — markets quiet. Loosen the settings above to widen the net.</td></tr>`;
    document.getElementById("scan-note").textContent =
      asOf ? `nothing triggered · as of ${asOf}` : "nothing triggered";
    renderHeadIndicators();
    return;
  }

  body.innerHTML = rows.map(r => {
    const small   = r.n < 10;
    const rateCls = (r.n === 0) ? "" : (r.rate >= 50 ? "cell-pos" : "cell-neg");
    return `<tr>
      <td class="ix"><a href="${escapeHtml(r.page)}?instrument=${encodeURIComponent(r.slug)}"><span class="ix-name">${escapeHtml(r.name)}</span><span class="ix-ticker">${escapeHtml(r.ticker)}</span></a></td>
      <td>${escapeHtml(r.strategy)}</td>
      <td class="${r.signalCls}">${escapeHtml(r.signal)}</td>
      <td class="dim">${escapeHtml(r.hold)}</td>
      <td class="${rateCls}">${r.n === 0 ? "—" : fmtInt(r.rate) + "%"}</td>
      <td class="${cls(r.avg)}">${fmt(r.avg)}</td>
      <td class="${small ? "dim" : ""}">${fmtInt(r.n)}${small ? " ⚠" : ""}</td>
    </tr>`;
  }).join("");

  const insts = new Set(rows.map(r => r.slug)).size;
  document.getElementById("scan-note").textContent =
    `${rows.length} signal${rows.length === 1 ? "" : "s"} across ${insts} market${insts === 1 ? "" : "s"}${asOf ? ` · as of ${asOf}` : ""}`;
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
  for(const segId of ["direction-seg", "range-seg"]){
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
  document.getElementById("threshold-range").addEventListener("change", update);

  document.getElementById("streak-range").addEventListener("input", e => {
    state.streak = parseInt(e.target.value, 10);
    renderControlsState();
  });
  document.getElementById("streak-range").addEventListener("change", update);
}

function wireSort(){
  document.getElementById("scan-head").addEventListener("click", e => {
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
    document.getElementById("scan-note").textContent =
      `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
