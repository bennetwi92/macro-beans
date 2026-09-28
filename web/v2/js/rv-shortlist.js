// Weekly review · step 2 — SHORTLIST: what qualifies this week?
//
// Shown to the user as step 2, IDEAS. One row per candidate from the build's scorecards (scorecard.js
// `scoreCard`, run over the S&P 500 as of the last completed week): its
// setup, BUY / WATCH / PASS, the headline, a letter per analysis block, the
// trade's geometry, and what changed since last week. A row opens the CARD.
//
// The headline is a consistent checklist, not a forecast — the backtest found
// no block that reliably ranks setups on a survivorship-biased universe
// (docs/scorecard/weekly_strategy_backtest.md §6). The grid is sorted by it
// because a consistent order beats an arbitrary one; the CARD is where the
// decision is made.

import "./nav.js";
import { TabulatorFull as Tabulator } from "https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.2/dist/js/tabulator_esm.min.js";
import { createOptionsBar } from "./options-bar.js";
import { loadScorecards, stepStrip, esc, gradeChip, changeNote, failInto, px, SAY, setupName } from "./review.js";
import { BLOCKS, BLOCK_LABELS, PROFILES } from "./scorecard.js";

const root = document.getElementById("shortlist-root");
root.innerHTML = `<div id="sl-grid"></div>`;

const state = { status: "ACTIVE", setup: "ALL", q: "", detail: false };
let rows = [];
let grid = null;
let built = false;

// The blocks that can carry weight somewhere. Pattern is weightless in every
// profile (see PROFILES) and would be a column of dots.
const COLS = BLOCKS.filter((k) => Object.values(PROFILES).some((p) => p.weights[k] > 0));
// On a phone the frozen NAME column must not eat the screen: `fitData` sizes it
// to the longest company name, which leaves the status and grades a sliver to
// swipe through. Cap it, and let long names ellipsise (full name on hover).
const NARROW = window.matchMedia("(max-width: 600px)");
const nameWidth = () => (NARROW.matches ? { minWidth: 70, maxWidth: 118 } : { minWidth: 150, maxWidth: 240 });
const SHORT = { market: "MKT", stage: "TREND", rs: "VS MKT", structure: "ROOM", momentum: "MOM", analogue: "RECORD", earnings: "EARN", fundamental: "BIZ" };
// Columns only shown with MORE DETAIL on: the per-check grades and the numbers
// behind the trade. The simple view answers "what, and why" only.
const DETAIL = [...COLS.map((k) => `blocks.${k}.s`), "plan.rr", "st", "s"];

createOptionsBar("optbar", {
  primary: [
    {
      type: "seg",
      id: "sl-status",
      label: "SHOW",
      value: state.status,
      options: [
        { value: "BUY", label: "BUY ONLY" },
        { value: "ACTIVE", label: "BUY + NOT YET" },
        { value: "SETUPS", label: "ALL SIGNALS" },
        { value: "ALL", label: "EVERY STOCK" },
      ],
    },
    {
      type: "seg",
      id: "sl-setup",
      label: "TYPE",
      value: state.setup,
      options: [
        { value: "ALL", label: "ALL" },
        { value: "PULLBACK", label: SAY.setup.PULLBACK },
        { value: "BREAKOUT", label: SAY.setup.BREAKOUT },
        { value: "REVERSAL", label: SAY.setup.REVERSAL },
      ],
    },
    { type: "text", id: "sl-q", label: "FIND", placeholder: "ticker or company" },
    {
      type: "seg",
      id: "sl-detail",
      label: "VIEW",
      value: "SIMPLE",
      options: [
        { value: "SIMPLE", label: "SIMPLE" },
        { value: "DETAIL", label: "MORE DETAIL" },
      ],
    },
  ],
  onChange: (id, v) => {
    if (id === "sl-detail") {
      state.detail = v === "DETAIL";
      return showDetail();
    }
    if (id === "sl-status") state.status = v;
    if (id === "sl-setup") state.setup = v;
    if (id === "sl-q") state.q = String(v || "").trim().toUpperCase();
    apply();
  },
});
document.getElementById("sl-q")?.addEventListener("input", (e) => {
  state.q = e.target.value.trim().toUpperCase();
  apply();
});

(async function boot() {
  let sc;
  try {
    sc = await loadScorecards();
  } catch (e) {
    return failInto(root, "the weekly scorecards", e);
  }
  const b = sc.tape?.budget;
  document.getElementById("steps").innerHTML = stepStrip("shortlist", { week: sc.week });
  if (b) {
    document.querySelector(".rv-step-q").textContent =
      `which stocks look worth buying? · ${SAY.level[b.level].toLowerCase()} week: buy up to ${b.maxNew} · click a row to check it`;
  }
  rows = sc.rows.map((r) => ({ ...r, change: changeNote(r), rank: r.status === "BUY" ? 3 : r.status === "WATCH" ? 2 : r.status === "PASS" ? 1 : 0 }));
  build();
})();

function visible(r) {
  if (state.status === "BUY" && r.status !== "BUY") return false;
  if (state.status === "ACTIVE" && r.status !== "BUY" && r.status !== "WATCH") return false;
  if (state.status === "SETUPS" && !r.setup) return false;
  if (state.setup !== "ALL" && r.setup !== state.setup) return false;
  if (state.q && !r.t.includes(state.q) && !String(r.n).toUpperCase().includes(state.q)) return false;
  return true;
}

function apply() {
  if (!grid || !built) return;
  grid.setFilter(visible);
  const n = rows.filter(visible).length;
  const el = document.querySelector("#sl-grid .tabulator-placeholder-contents");
  if (el && !n) {
    el.textContent =
      state.status === "BUY"
        ? "Nothing worth buying this week. That's fine: holding cash and waiting is a perfectly good decision."
        : "No stocks match these filters.";
  }
}

function showDetail() {
  if (!grid || !built) return;
  for (const f of DETAIL) {
    const col = grid.getColumn(f);
    if (col) state.detail ? col.show() : col.hide();
  }
}

const statusFmt = (cell) => {
  const r = cell.getRow().getData();
  const s = r.status;
  const chip = s ? `<span class="rv-chip rv-${s.toLowerCase()}">${SAY.status[s]}</span>` : `<span class="dim-note">—</span>`;
  const ch = r.change === "NEW" ? ` <span class="rv-new">NEW</span>` : r.change ? ` <span class="rv-was">${esc(r.change)}</span>` : "";
  return chip + ch;
};

function build() {
  grid = new Tabulator("#sl-grid", {
    data: rows,
    layout: "fitData",
    height: "100%",
    index: "t",
    placeholder: "No stocks match these filters.",
    initialSort: [
      { column: "total", dir: "desc" },
      { column: "rank", dir: "desc" },
    ],
    columns: [
      {
        title: "STOCK",
        field: "t",
        frozen: true,
        ...nameWidth(),
        cssClass: "sl-name",
        tooltip: (e, c) => `${c.getRow().getData().t} · ${c.getRow().getData().n}`,
        formatter: (c) => {
          const r = c.getRow().getData();
          return `<span class="ps-tkr">${esc(r.t)}</span> <span class="ps-name">${esc(r.n)}</span>`;
        },
      },
      { title: "", field: "rank", visible: false },
      { title: "VERDICT", field: "status", minWidth: 120, headerTooltip: "BUY: worth buying this week. NOT YET: close, check again next week. SKIP: something important is wrong.", formatter: statusFmt, sorter: (a, b, ra, rb) => ra.getData().rank - rb.getData().rank },
      {
        title: "TYPE",
        field: "setup",
        minWidth: 90,
        headerTooltip: `DIP: ${SAY.setupLong.PULLBACK}. NEW HIGH: ${SAY.setupLong.BREAKOUT}. TURNAROUND: ${SAY.setupLong.REVERSAL}.`,
        formatter: (c) => `<span class="rv-setup" title="${esc(SAY.setupLong[c.getValue()] || "")}">${esc(setupName(c.getValue()))}</span>`,
      },
      {
        title: "SCORE",
        field: "total",
        hozAlign: "right",
        minWidth: 56,
        sorter: "number",
        formatter: (c) => (c.getValue() == null ? "—" : `<b>${c.getValue().toFixed(0)}</b>`),
        headerTooltip: "0 to 100: how many of the checks this stock passes, weighted by how much each matters. Higher is better, but it's a checklist, not a prediction.",
      },
      ...COLS.map((k) => ({
        title: SHORT[k],
        field: `blocks.${k}.s`,
        hozAlign: "center",
        minWidth: 38,
        sorter: "number",
        headerTooltip: `${BLOCK_LABELS[k]} (A is best, E is worst)`,
        visible: false,
        formatter: (c) => gradeChip(c.getRow().getData().blocks?.[k]),
      })),
      {
        title: "MAX LOSS",
        field: "plan.riskPct",
        hozAlign: "right",
        minWidth: 52,
        sorter: "number",
        formatter: (c) => (c.getValue() == null ? "—" : `−${c.getValue().toFixed(1)}%`),
        headerTooltip: "How far the price can fall before you sell to cut the loss (the stop-loss).",
      },
      {
        title: "GAIN:LOSS",
        field: "plan.rr",
        visible: false,
        hozAlign: "right",
        minWidth: 44,
        sorter: "number",
        formatter: (c) => (c.getValue() == null ? "—" : c.getValue().toFixed(1)),
        headerTooltip: "How far it could rise to its next past high, for each 1 it could lose. 2 or more is good.",
      },
      { title: "PRICE $", field: "c", hozAlign: "right", minWidth: 62, formatter: (c) => px(c.getValue()) },
      {
        title: "TREND",
        field: "st",
        visible: false,
        minWidth: 90,
        headerTooltip: "Which way the stock's longer-term trend points, and for how many weeks.",
        formatter: (c) => {
          const r = c.getRow().getData();
          return r.st == null ? "—" : `${SAY.stage[r.st]}<span class="dim-note"> ${r.age}w</span>`;
        },
      },
      {
        title: "NEXT RESULTS",
        field: "next",
        headerTooltip: "When the company next reports its profits. Prices can jump either way on the day.",
        minWidth: 84,
        formatter: (c) => {
          const r = c.getRow().getData();
          const soon = (r.flags || []).some((f) => f.startsWith("earnings"));
          return c.getValue() ? `<span class="${soon ? "cd-flag" : "dim-note"}">${esc(c.getValue())}</span>` : "—";
        },
      },
      { title: "INDUSTRY", field: "s", minWidth: 120, visible: false, formatter: (c) => `<span class="dim-note">${esc(c.getValue() || "")}</span>` },
      {
        title: "WHY",
        headerTooltip: "The reason for the verdict, in a line.",
        field: "why",
        minWidth: 240,
        cssClass: "sl-why",
        formatter: (c) => {
          const r = c.getRow().getData();
          return esc([r.why, ...(r.vetoes || [])].filter(Boolean).join(" · "));
        },
      },
    ],
  });
  grid.on("rowClick", (e, row) => {
    location.href = `card.html?t=${encodeURIComponent(row.getData().t)}`;
  });
  grid.on("tableBuilt", () => {
    built = true;
    apply();
    showDetail();
  });
  // Rotating a phone crosses the breakpoint — re-cap the name column.
  NARROW.addEventListener("change", () => {
    const col = grid.getColumn("t");
    const w = nameWidth();
    col.updateDefinition(w);
  });
}
