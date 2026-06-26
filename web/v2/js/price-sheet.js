// Price sheet page entry module.
// Renders the shared nav + options bar, then a Tabulator grid fed by the
// pre-built snapshot at data/price-sheet.json (scripts/site/build_price_sheet.py).

import "./nav.js";
import { createOptionsBar } from "./options-bar.js";
import { rowAsOf } from "./price-metrics.js";
import { TabulatorFull as Tabulator } from "https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.2/dist/js/tabulator_esm.min.js";

/* ---------- options bar ---------- */

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

createOptionsBar("optbar", {
  primary: [{ type: "date", id: "ps-date", label: "DATE", value: todayISO() }],
  onChange: (id, value) => {
    if (id === "ps-date" && value) renderAsOf(value);
  },
});

/* ---------- formatters (display + conditional colour) ---------- */

// Always toggle BOTH classes so reused cells don't keep a stale colour.
function paint(cell, up, down) {
  const el = cell.getElement();
  el.classList.toggle("up", up);
  el.classList.toggle("down", down);
}

const num2 = (cell) => {
  const v = cell.getValue();
  return v == null ? "" : v.toFixed(2);
};
const num1 = (cell) => {
  const v = cell.getValue();
  return v == null ? "" : v.toFixed(1);
};
const pct1 = (cell) => {
  const v = cell.getValue();
  if (v == null || Number.isNaN(v)) return "";
  paint(cell, v > 0, v < 0);
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
};
const rsiFmt = (cell) => {
  const v = cell.getValue();
  if (v == null) return "";
  paint(cell, v <= 30, v >= 70); // oversold green, overbought red
  return String(Math.round(v));
};
const ratio200 = (cell) => {
  const v = cell.getValue();
  if (v == null) return "";
  paint(cell, v > 1, v < 1); // above / below 200-day average
  return v.toFixed(2);
};
const volrFmt = (cell) => {
  const v = cell.getValue();
  if (v == null) return "";
  paint(cell, v < 0.85, v > 1.15); // calm vs expanding volatility
  return v.toFixed(2);
};
const nameFmt = (cell) => {
  const d = cell.getRow().getData();
  return `<span class="ps-name">${d.name}</span> <span class="ps-tkr">${d.ticker}</span>`;
};
const chartFmt = (cell) => {
  const t = cell.getRow().getData().ticker;
  return (
    `<a class="ps-chart" href="chart.html?i=${t}" title="Open chart" onclick="event.stopPropagation()">` +
    `<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">` +
    `<polyline points="1,11 5,7 8,9 14,3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></a>`
  );
};

/* ---------- grid ---------- */

const R = "right";
const grid = new Tabulator("#ps-grid", {
  data: [],
  layout: "fitData",
  height: "100%",
  placeholder: "Loading…",
  initialSort: [{ column: "d1", dir: "desc" }],
  columns: [
    { title: "INSTRUMENT", field: "name", frozen: true, width: 168, formatter: nameFmt },
    { title: "THEME", field: "theme", width: 142, cssClass: "ps-theme" },
    // LAST / OPEN / GAP are hidden for now: the data is pulled overnight (EOD),
    // so there is no live last price, session open, or intraday gap to show.
    // CLOSE is the latest settled close. (The metrics still compute internally.)
    { title: "CLOSE", field: "last", width: 74, hozAlign: R, formatter: num2 },
    { title: "1D%", field: "d1", width: 62, hozAlign: R, formatter: pct1 },
    { title: "1W%", field: "w1", width: 62, hozAlign: R, formatter: pct1 },
    { title: "1M%", field: "m1", width: 64, hozAlign: R, formatter: pct1 },
    { title: "1Y%", field: "y1", width: 66, hozAlign: R, formatter: pct1 },
    { title: "RSI", field: "rsi", width: 54, hozAlign: R, formatter: rsiFmt },
    { title: "PX/200D", field: "px200", width: 76, hozAlign: R, formatter: ratio200 },
    { title: "VOL45", field: "vol45", width: 64, hozAlign: R, formatter: num1 },
    { title: "V45/V1Y", field: "volr", width: 78, hozAlign: R, formatter: volrFmt },
    { title: "", field: "chart", width: 36, hozAlign: "center", headerSort: false, formatter: chartFmt },
  ],
});

/* ---------- load bars, compute as-of the picked date ---------- */

let INSTRUMENTS = [];

// Include the chosen day's own bar (end of local day).
const asOfMs = (iso) => Date.parse(`${iso}T23:59:59`);

function renderAsOf(iso) {
  if (!INSTRUMENTS.length) return;
  const ms = asOfMs(iso);
  const rows = INSTRUMENTS.map((inst) => ({
    ticker: inst.ticker,
    name: inst.name,
    theme: inst.theme,
    ...rowAsOf(inst.bars, ms),
  }));
  grid.setData(rows);
}

grid.on("tableBuilt", async () => {
  try {
    const res = await fetch("data/price-sheet.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    INSTRUMENTS = payload.instruments || [];
    if (!INSTRUMENTS.length) {
      grid.setPlaceholder("No instruments");
      return;
    }
    // Bound the date picker: earliest available bar .. today.
    const dateEl = document.getElementById("ps-date");
    if (dateEl) {
      let min = null;
      for (const inst of INSTRUMENTS) {
        if (inst.bars.length && (min === null || inst.bars[0][0] < min)) min = inst.bars[0][0];
      }
      if (min) dateEl.min = min;
      dateEl.max = todayISO();
    }
    renderAsOf(dateEl && dateEl.value ? dateEl.value : todayISO());
  } catch (err) {
    grid.setPlaceholder(`Could not load price data (${err.message})`);
  }
});
