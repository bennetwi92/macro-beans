// Weekly review · step 2 — SHORTLIST: what qualifies this week?
//
// One row per candidate from the build's scorecards (scorecard.js
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
import { loadScorecards, stepStrip, esc, gradeChip, changeNote, failInto, px } from "./review.js";
import { BLOCKS, BLOCK_LABELS, PROFILES } from "./scorecard.js";

const root = document.getElementById("shortlist-root");
root.innerHTML = `<div id="sl-grid"></div>`;

const state = { status: "ACTIVE", setup: "ALL", q: "" };
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
const SHORT = { market: "MKT", stage: "STG", rs: "RS", structure: "STR", momentum: "MOM", analogue: "LWK", earnings: "ERN", fundamental: "FND" };

createOptionsBar("optbar", {
  primary: [
    {
      type: "seg",
      id: "sl-status",
      label: "SHOW",
      value: state.status,
      options: [
        { value: "BUY", label: "BUY" },
        { value: "ACTIVE", label: "BUY+WATCH" },
        { value: "SETUPS", label: "ALL SETUPS" },
        { value: "ALL", label: "ALL NAMES" },
      ],
    },
    {
      type: "seg",
      id: "sl-setup",
      label: "SETUP",
      value: state.setup,
      options: [
        { value: "ALL", label: "ALL" },
        { value: "PULLBACK", label: "PULLBACK" },
        { value: "BREAKOUT", label: "BREAKOUT" },
        { value: "REVERSAL", label: "REVERSAL" },
      ],
    },
    { type: "text", id: "sl-q", label: "FIND", placeholder: "ticker or name" },
  ],
  onChange: (id, v) => {
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
      `what qualifies? · ${b.level} budget: ≤ ${b.maxNew} new at ${b.riskPct}% risk · week to ${sc.week}`;
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
        ? "Nothing to buy this week. Cash is a position, and a week with no qualifying trade is a result, not a failure."
        : "Nothing matches.";
  }
}

const statusFmt = (cell) => {
  const r = cell.getRow().getData();
  const s = r.status;
  const chip = s ? `<span class="rv-chip rv-${s.toLowerCase()}">${s}</span>` : `<span class="dim-note">—</span>`;
  const ch = r.change === "NEW" ? ` <span class="rv-new">NEW</span>` : r.change ? ` <span class="rv-was">${esc(r.change)}</span>` : "";
  return chip + ch;
};

function build() {
  grid = new Tabulator("#sl-grid", {
    data: rows,
    layout: "fitData",
    height: "100%",
    index: "t",
    placeholder: "Nothing matches.",
    initialSort: [
      { column: "total", dir: "desc" },
      { column: "rank", dir: "desc" },
    ],
    columns: [
      {
        title: "NAME",
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
      { title: "STATUS", field: "status", minWidth: 108, formatter: statusFmt, sorter: (a, b, ra, rb) => ra.getData().rank - rb.getData().rank },
      { title: "SETUP", field: "setup", minWidth: 80, formatter: (c) => `<span class="rv-setup">${esc(c.getValue() || "")}</span>` },
      {
        title: "SCORE",
        field: "total",
        hozAlign: "right",
        minWidth: 56,
        sorter: "number",
        formatter: (c) => (c.getValue() == null ? "—" : `<b>${c.getValue().toFixed(0)}</b>`),
        headerTooltip: "The weighted headline over the available blocks (0–100). A consistent checklist, not a forecast.",
      },
      ...COLS.map((k) => ({
        title: SHORT[k],
        field: `blocks.${k}.s`,
        hozAlign: "center",
        minWidth: 38,
        sorter: "number",
        headerTooltip: BLOCK_LABELS[k],
        formatter: (c) => gradeChip(c.getRow().getData().blocks?.[k]),
      })),
      {
        title: "STOP",
        field: "plan.riskPct",
        hozAlign: "right",
        minWidth: 52,
        sorter: "number",
        formatter: (c) => (c.getValue() == null ? "—" : `−${c.getValue().toFixed(1)}%`),
        headerTooltip: "Distance from this week's close to the strategy's initial stop.",
      },
      {
        title: "R:R",
        field: "plan.rr",
        hozAlign: "right",
        minWidth: 44,
        sorter: "number",
        formatter: (c) => (c.getValue() == null ? "—" : c.getValue().toFixed(1)),
        headerTooltip: "Room to the nearest resistance per unit of risk (capped at 6 ATR in blue sky).",
      },
      { title: "CLOSE", field: "c", hozAlign: "right", minWidth: 62, formatter: (c) => px(c.getValue()) },
      {
        title: "STAGE",
        field: "st",
        hozAlign: "center",
        minWidth: 48,
        formatter: (c) => {
          const r = c.getRow().getData();
          return r.st == null ? "—" : `${r.st}<span class="dim-note">·${r.age}w</span>`;
        },
      },
      {
        title: "EARNINGS",
        field: "next",
        minWidth: 84,
        formatter: (c) => {
          const r = c.getRow().getData();
          const soon = (r.flags || []).some((f) => f.startsWith("earnings"));
          return c.getValue() ? `<span class="${soon ? "cd-flag" : "dim-note"}">${esc(c.getValue())}</span>` : "—";
        },
      },
      { title: "SECTOR", field: "s", minWidth: 120, formatter: (c) => `<span class="dim-note">${esc(c.getValue() || "")}</span>` },
      {
        title: "WHY",
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
  });
  // Rotating a phone crosses the breakpoint — re-cap the name column.
  NARROW.addEventListener("change", () => {
    const col = grid.getColumn("t");
    const w = nameWidth();
    col.updateDefinition(w);
  });
}
