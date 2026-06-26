// Reports page entry module.
// A research library as a two-screen drill-in: a full-screen filterable list,
// and a full-screen reader you reach by clicking a note and leave via Back.
// The list is data/reports.json; each note's HTML loads on demand from
// data/reports/<slug>.html. Deep-link a note with ?r=<slug>.

import "./nav.js";
import { createOptionsBar } from "./options-bar.js";

const params = new URLSearchParams(location.search);
let REPORTS = [];
let filter = "";

const $ = (id) => document.getElementById(id);
const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

/* ---------- options bar (live filter, list screen only) ---------- */

createOptionsBar("optbar", {
  primary: [{ type: "search", id: "report-filter", label: "FILTER", placeholder: "Filter reports…" }],
});
document.addEventListener("input", (e) => {
  if (e.target && e.target.id === "report-filter") {
    filter = e.target.value.trim().toLowerCase();
    renderIndex();
  }
});

/* ---------- list screen ---------- */

function matches(r) {
  if (!filter) return true;
  return (
    r.title.toLowerCase().includes(filter) ||
    r.category.toLowerCase().includes(filter) ||
    (r.summary || "").toLowerCase().includes(filter)
  );
}

function renderIndex() {
  const root = $("report-index");
  if (!root) return;
  const shown = REPORTS.filter(matches);
  if (!shown.length) {
    root.innerHTML = `<div class="report-none">No reports match.</div>`;
    return;
  }
  const cats = [];
  const byCat = new Map();
  for (const r of shown) {
    if (!byCat.has(r.category)) { byCat.set(r.category, []); cats.push(r.category); }
    byCat.get(r.category).push(r);
  }
  let html = "";
  for (const cat of cats) {
    html += `<div class="report-cat">${escapeHtml(cat)}</div>`;
    for (const r of byCat.get(cat)) {
      html +=
        `<a class="report-item" data-slug="${escapeHtml(r.slug)}" href="?r=${encodeURIComponent(r.slug)}">` +
        `<span class="ri-title">${escapeHtml(r.title)}</span>` +
        (r.summary ? `<span class="ri-sum">${escapeHtml(r.summary)}</span>` : "") +
        `<span class="ri-meta">${escapeHtml(r.source)} · ${r.words} words</span>` +
        `</a>`;
    }
  }
  root.innerHTML = html;
}

/* ---------- screen switching ---------- */

function showList() {
  $("report-reader").hidden = true;
  $("report-list").hidden = false;
  $("optbar").style.display = "";
  document.title = "Reports · Macro Beans";
  window.scrollTo(0, 0);
}

async function showReader(slug) {
  const r = REPORTS.find((x) => x.slug === slug);
  if (!r) return showList();
  $("report-list").hidden = true;
  $("report-reader").hidden = false;
  $("optbar").style.display = "none";
  $("reader-title").textContent = r.title;
  document.title = `${r.title} · Macro Beans`;
  window.scrollTo(0, 0);
  const view = $("report-view");
  view.innerHTML = `<div class="report-empty">Loading…</div>`;
  try {
    const res = await fetch(`data/reports/${encodeURIComponent(slug)}.html`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const html = await res.text();
    const meta =
      `<div class="report-meta">${escapeHtml(r.category)} · ${escapeHtml(r.source)} · ${r.words} words` +
      (r.updated ? ` · updated ${escapeHtml(r.updated)}` : "") +
      `</div>`;
    view.innerHTML = `<article class="report-body">${meta}${html}</article>`;
  } catch (err) {
    view.innerHTML = `<div class="report-empty">Could not load report (${escapeHtml(err.message)})</div>`;
  }
}

// Navigation = update history + render. popstate just renders for the URL.
function goReport(slug) {
  history.pushState({ slug }, "", `?r=${encodeURIComponent(slug)}`);
  showReader(slug);
}
function goList() {
  history.pushState({}, "", location.pathname);
  showList();
}

window.addEventListener("popstate", () => {
  const slug = new URLSearchParams(location.search).get("r");
  if (slug) showReader(slug);
  else showList();
});

$("report-index").addEventListener("click", (e) => {
  const item = e.target.closest("[data-slug]");
  if (!item) return;
  e.preventDefault();
  goReport(item.dataset.slug);
});
$("report-back").addEventListener("click", goList);

/* ---------- load ---------- */

fetch("data/reports.json", { cache: "no-cache" })
  .then((r) => r.json())
  .then((d) => {
    REPORTS = d.reports || [];
    renderIndex();
    const initial = params.get("r");
    if (initial && REPORTS.some((r) => r.slug === initial)) showReader(initial);
    else showList();
  })
  .catch((err) => {
    $("report-index").innerHTML = `<div class="report-none">Could not load reports (${escapeHtml(err.message)})</div>`;
  });
