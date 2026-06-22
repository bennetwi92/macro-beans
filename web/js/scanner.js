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
  findMultiDayEvents,
  findBreakoutEvents,
  findRangeEvents,
  findCrossEvents,
  liveBounce,
  liveStreak,
  liveMultiDay,
  liveBreakout,
  liveRange,
  liveCross,
  computeStats,
  indexAsOf,
  forwardReturn,
  HORIZONS,
  STREAK_HORIZONS,
  MULTIDAY_HORIZONS,
  BREAKOUT_HORIZONS,
  RANGE_HORIZONS,
  CROSS_HORIZONS,
  fmt, fmtInt, cls,
  escapeHtml,
} from "./strategy-engine.js";

// Fixed, sensible defaults for the strategies the scanner can't give a slider
// to (the control surface stays small). These mirror each page's defaults.
const MD_MOVE    = { threshold: 8, window: 5 };   // multi-day move
const BREAK_LOOK = 20;                            // breakout look-back
const RANGE_SET  = { band: 3, window: 10 };       // tight range
const CROSS_PER  = 200;                           // moving-average length

const DATA_BASE = "data";

const state = {
  direction: "down",
  threshold: 2.0,    // bounce: single-day move, absolute %
  streak:    3,      // red/green streak: consecutive closes
  range:     "5y",   // track-record window
  asOf:      null,   // rewind date (ISO); null = live, as of the last close
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
    horizons: HORIZONS,                // outcome held to the last horizon (3 days)
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
    horizons: STREAK_HORIZONS,         // 5 days
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
  {
    key:   "multiday",
    label: "Multi-Day Move",
    page:  "multi-day-move.html",
    hold:  "10 days",
    horizons: MULTIDAY_HORIZONS,       // 10 days
    detect(bars){ return liveMultiDay(bars, { direction: state.direction, ...MD_MOVE }); },
    signal(sig){ return `${fmt(sig.move)} / ${MD_MOVE.window}d`; },
    signalCls(sig){ return cls(sig.move); },
    stats(bars){
      const ev = findMultiDayEvents(bars, {
        direction: state.direction, threshold: MD_MOVE.threshold, window: MD_MOVE.window,
        entry: "close", range: state.range,
      });
      return computeStats(ev)[2];   // 10-day horizon (MULTIDAY_HORIZONS[2])
    },
  },
  {
    key:   "breakout",
    label: "Breakout",
    page:  "breakout.html",
    hold:  "10 days",
    horizons: BREAKOUT_HORIZONS,       // 10 days
    detect(bars){ return liveBreakout(bars, { direction: state.direction, lookback: BREAK_LOOK }); },
    signal(){ return state.direction === "up" ? `${BREAK_LOOK}-day high` : `${BREAK_LOOK}-day low`; },
    signalCls(){ return ""; },
    stats(bars){
      const ev = findBreakoutEvents(bars, {
        direction: state.direction, lookback: BREAK_LOOK,
        entry: "close", range: state.range,
      });
      return computeStats(ev)[2];   // 10-day horizon (BREAKOUT_HORIZONS[2])
    },
  },
  {
    // Tight Range has no direction — it shows in either scan mode.
    key:   "range",
    label: "Tight Range",
    page:  "tight-range.html",
    hold:  "10 days",
    horizons: RANGE_HORIZONS,          // 10 days
    detect(bars){ return liveRange(bars, RANGE_SET); },
    signal(sig){ return `${sig.spread.toFixed(1)}% range`; },
    signalCls(){ return ""; },
    stats(bars){
      const ev = findRangeEvents(bars, {
        band: RANGE_SET.band, window: RANGE_SET.window,
        entry: "close", range: state.range,
      });
      return computeStats(ev)[2];   // 10-day horizon (RANGE_HORIZONS[2])
    },
  },
  {
    key:   "cross",
    label: "Moving-Average Cross",
    page:  "ma-cross.html",
    hold:  "20 days",
    horizons: CROSS_HORIZONS,          // 20 days
    detect(bars){ return liveCross(bars, { direction: state.direction, period: CROSS_PER }); },
    signal(){ return state.direction === "up" ? `above ${CROSS_PER}-day` : `below ${CROSS_PER}-day`; },
    signalCls(){ return ""; },
    stats(bars){
      const ev = findCrossEvents(bars, {
        direction: state.direction, period: CROSS_PER,
        entry: "close", range: state.range,
      });
      return computeStats(ev)[2];   // 20-day horizon (CROSS_HORIZONS[2])
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

// The date the scan is framed on — the user's rewind date, or the latest close.
function effectiveDate(){
  return state.asOf || globalLatest();
}

// True when we've rewound far enough that there is future to score against.
function isHistory(){
  return Boolean(state.asOf) && state.asOf < globalLatest();
}

// Build one row per (instrument × strategy) firing on the bar as of effectiveDate().
// In rewind mode each row also carries the realised OUTCOME: the actual return
// over the setup's hold window, read from the bars that came after the entry.
function scanRows(){
  const asOf = effectiveDate();
  const history = isHistory();
  const rows = [];
  for(const inst of instruments){
    const payload = cache.get(inst.slug);
    if(!payload || !payload.bars) continue;
    const bars = payload.bars;
    // Truncate to the bar as of the rewind date: every detector and the track
    // record then see only what was knowable then (no look-ahead).
    const idx = indexAsOf(bars, asOf);
    if(idx < 2) continue;                       // too little history to score
    // In live mode idx is the last bar, so the full series is already the view —
    // only allocate a truncated copy when actually rewound.
    const view = (idx === bars.length - 1) ? bars : bars.slice(0, idx + 1);
    for(const strat of STRATEGIES){
      const sig = strat.detect(view);
      if(!sig.triggered) continue;
      const st = strat.stats(view);
      const hold = strat.horizons.at(-1);
      const outcome = history ? forwardReturn(bars, idx, hold) : NaN;
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
        outcome,                                // realised return over the hold window
        pending:     history && !Number.isFinite(outcome),  // window not elapsed yet
      });
    }
  }
  return rows;
}

// Latest bar date across all loaded instruments — the most recent session.
function globalLatest(){
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

// Earliest bar date across all loaded instruments — the rewind floor.
function globalEarliest(){
  let earliest = "";
  for(const payload of cache.values()){
    const bars = payload && payload.bars;
    if(bars && bars.length){
      const d = bars[0][0];
      if(!earliest || d < earliest) earliest = d;
    }
  }
  return earliest;
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

  // Reflect the as-of state, but only write when it actually differs so a
  // slider drag (which also runs this) never disturbs the date field.
  const asof = document.getElementById("asof-date");
  const want = state.asOf || globalLatest();
  if(asof.value !== want) asof.value = want;
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
  const asOf = effectiveDate();
  const history = isHistory();

  // The OUTCOME column only makes sense once there's a past to look back from.
  document.getElementById("scan-table").classList.toggle("hide-outcome", !history);
  // The header must not claim "now" when we've rewound to a past close.
  document.getElementById("scan-title").textContent = history ? "TRIGGERED THEN" : "TRIGGERED NOW";

  if(rows.length === 0){
    body.innerHTML =
      `<tr><td colspan="8" class="empty">No setups triggered as of ${escapeHtml(asOf) || "the last close"} — markets quiet. Loosen the settings above to widen the net.</td></tr>`;
    document.getElementById("scan-note").textContent =
      asOf ? `nothing triggered · as of ${asOf}` : "nothing triggered";
    renderHeadIndicators();
    return;
  }

  body.innerHTML = rows.map(r => {
    const small   = r.n < 10;
    const rateCls = (r.n === 0) ? "" : (r.rate >= 50 ? "cell-pos" : "cell-neg");
    const outcome = r.pending
      ? `<td class="col-outcome dim">pending</td>`
      : `<td class="col-outcome ${cls(r.outcome)}">${fmt(r.outcome)}</td>`;
    return `<tr>
      <td class="ix"><a href="instrument.html?instrument=${encodeURIComponent(r.slug)}"><span class="ix-name">${escapeHtml(r.name)}</span><span class="ix-ticker">${escapeHtml(r.ticker)}</span></a></td>
      <td><a class="strat-cell" href="${escapeHtml(r.page)}?instrument=${encodeURIComponent(r.slug)}">${escapeHtml(r.strategy)}</a></td>
      <td class="${r.signalCls}">${escapeHtml(r.signal)}</td>
      <td class="dim">${escapeHtml(r.hold)}</td>
      ${outcome}
      <td class="${rateCls}">${r.n === 0 ? "—" : fmtInt(r.rate) + "%"}</td>
      <td class="${cls(r.avg)}">${fmt(r.avg)}</td>
      <td class="${small ? "dim" : ""}">${fmtInt(r.n)}${small ? " ⚠" : ""}</td>
    </tr>`;
  }).join("");

  const insts = new Set(rows.map(r => r.slug)).size;
  const frame = history ? `rewound to ${asOf}` : (asOf ? `as of ${asOf}` : "");
  document.getElementById("scan-note").textContent =
    `${rows.length} signal${rows.length === 1 ? "" : "s"} across ${insts} market${insts === 1 ? "" : "s"}${frame ? ` · ${frame}` : ""}`;
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

  document.getElementById("asof-date").addEventListener("change", e => {
    setAsOf(e.target.value);
    syncUrl();
    update();
  });
}

// Set the rewind date. An empty field or any date at/after the latest close
// means "live" (state.asOf = null); anything earlier rewinds.
function setAsOf(value){
  state.asOf = (value && value < globalLatest()) ? value : null;
}

// Bound the date field to the available history and seed it from the URL.
function setupDateControl(){
  const input = document.getElementById("asof-date");
  input.min = globalEarliest();
  input.max = globalLatest();
  const url = new URLSearchParams(location.search).get("asof");
  if(url) setAsOf(url);
}

// Reflect the rewind date in the URL (?asof=…) so a view is shareable; live
// mode drops the param entirely.
function syncUrl(){
  const url = new URL(location.href);
  if(state.asOf) url.searchParams.set("asof", state.asOf);
  else url.searchParams.delete("asof");
  history.replaceState(null, "", url);
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
    setupDateControl();
    wireControls();
    wireSort();
    update();
  } catch(err){
    document.getElementById("scan-note").textContent =
      `Failed to load data: ${err.message}`;
    console.error(err);
  }
})();
