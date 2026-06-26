// Chart page entry module.
// Shared nav + options bar (instrument search + 45D/1Y/ALL zoom), then a
// full-bleed SVG line chart. Instrument bars are loaded on demand from
// data/charts/<ticker>.json; the search list comes from data/instruments.json.
// Opening with ?i=<ticker> (e.g. from the price-sheet chart icon) pre-loads it.

import "./nav.js";
import { createOptionsBar } from "./options-bar.js";

const params = new URLSearchParams(location.search);
const ZOOMS = { "45d": 45, "1y": 365, all: null };

let menu = [];
let current = null; // {ticker, name, theme}
let bars = []; // [[iso, close], ...] full history
let zoom = "1y";

/* ---------- options bar ---------- */

createOptionsBar("optbar", {
  primary: [
    {
      type: "search",
      id: "chart-search",
      label: "INSTRUMENT",
      placeholder: "Search ticker or name…",
      value: params.get("i") || "",
    },
    {
      type: "seg",
      id: "chart-zoom",
      label: "ZOOM",
      value: zoom,
      options: [
        { value: "45d", label: "45D" },
        { value: "1y", label: "1Y" },
        { value: "all", label: "ALL" },
      ],
    },
  ],
  onChange: (id, value) => {
    if (id === "chart-zoom") {
      zoom = value;
      render();
    } else if (id === "chart-search") {
      selectByQuery(value);
    }
  },
});

/* ---------- data ---------- */

function attachDatalist() {
  const input = document.getElementById("chart-search");
  if (!input) return;
  const dl = document.createElement("datalist");
  dl.id = "chart-instruments";
  for (const m of menu) {
    const o = document.createElement("option");
    o.value = m.ticker;
    o.textContent = m.name;
    dl.appendChild(o);
  }
  document.body.appendChild(dl);
  input.setAttribute("list", "chart-instruments");
}

function selectByQuery(q) {
  if (!q) return;
  const s = q.trim().toLowerCase();
  const hit =
    menu.find((m) => m.ticker.toLowerCase() === s) ||
    menu.find((m) => m.name.toLowerCase() === s) ||
    menu.find((m) => m.ticker.toLowerCase().startsWith(s)) ||
    menu.find((m) => m.name.toLowerCase().includes(s));
  if (hit) loadInstrument(hit.ticker);
}

async function loadInstrument(ticker) {
  const meta = menu.find((m) => m.ticker.toLowerCase() === ticker.toLowerCase());
  const realTicker = meta ? meta.ticker : ticker;
  try {
    const res = await fetch(`data/charts/${encodeURIComponent(realTicker)}.json`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    current = { ticker: d.ticker, name: d.name, theme: d.theme };
    bars = d.bars || [];
    const input = document.getElementById("chart-search");
    if (input) input.value = d.ticker;
    document.title = `${d.name} · Macro Beans`;
    render();
  } catch (err) {
    current = null;
    bars = [];
    showMessage(`Could not load ${realTicker} (${err.message})`);
  }
}

fetch("data/instruments.json", { cache: "no-cache" })
  .then((r) => r.json())
  .then((d) => {
    menu = d.instruments || [];
    attachDatalist();
    const initial = params.get("i");
    if (initial) loadInstrument(initial);
    else render();
  })
  .catch((err) => showMessage(`Could not load instruments (${err.message})`));

/* ---------- render ---------- */

const fmtV = (v) => (Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(2));

function showMessage(msg) {
  const wrap = document.getElementById("chart");
  if (wrap) wrap.innerHTML = `<div class="chart-empty">${msg}</div>`;
}

function sliceByZoom(all, z) {
  const days = ZOOMS[z];
  if (!days) return all;
  const cut = Date.parse(all[all.length - 1][0]) - days * 86400000;
  return all.filter((b) => Date.parse(b[0]) >= cut);
}

function render() {
  const wrap = document.getElementById("chart");
  if (!wrap) return;
  if (!current) return showMessage("Search for an instrument to chart.");
  const slice = sliceByZoom(bars, zoom);
  if (slice.length < 2) return showMessage("Not enough data for this range.");

  const W = Math.max(320, wrap.clientWidth);
  const H = Math.max(200, wrap.clientHeight);
  const padL = 54, padR = 16, padT = 18, padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // bars are [iso, open, close]; the line chart draws close (index 2).
  let lo = Infinity, hi = -Infinity;
  for (const b of slice) {
    if (b[2] < lo) lo = b[2];
    if (b[2] > hi) hi = b[2];
  }
  if (lo === hi) { lo *= 0.99; hi *= 1.01; }

  const x = (i) => padL + (plotW * i) / (slice.length - 1);
  const y = (v) => padT + plotH * (1 - (v - lo) / (hi - lo));

  let pts = "";
  for (let i = 0; i < slice.length; i++) pts += `${i ? " " : ""}${x(i).toFixed(1)},${y(slice[i][2]).toFixed(1)}`;

  const grid = [hi, (lo + hi) / 2, lo]
    .map((v) => {
      const yy = y(v).toFixed(1);
      return (
        `<line class="chart-grid" x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"/>` +
        `<text class="chart-axis" x="${padL - 7}" y="${(+yy + 3).toFixed(1)}" text-anchor="end">${fmtV(v)}</text>`
      );
    })
    .join("");

  const first = slice[0], last = slice[slice.length - 1];
  const xlab =
    `<text class="chart-axis" x="${padL}" y="${H - 7}" text-anchor="start">${first[0]}</text>` +
    `<text class="chart-axis" x="${W - padR}" y="${H - 7}" text-anchor="end">${last[0]}</text>`;
  const dot = `<circle class="chart-dot" cx="${x(slice.length - 1).toFixed(1)}" cy="${y(last[2]).toFixed(1)}" r="2.6"/>`;

  const svg =
    `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">` +
    grid +
    `<polyline class="chart-line" points="${pts}"/>` +
    dot +
    xlab +
    `</svg>`;

  const chg = (last[2] / first[2] - 1) * 100;
  const cls = chg >= 0 ? "up" : "down";
  const head =
    `<div class="chart-head">` +
    `<span class="chart-name">${current.name}</span> ` +
    `<span class="chart-tkr">${current.ticker}</span>` +
    `<span class="chart-sep">·</span>` +
    `<span class="chart-last">${fmtV(last[2])}</span> ` +
    `<span class="${cls}">${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%</span>` +
    `</div>`;

  wrap.innerHTML = head + svg;
}

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(render, 120);
});
