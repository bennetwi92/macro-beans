/* Macro Beans home — renders the publication catalog as cards grouped
   by category. Adding a new piece is a one-line edit to catalog.js. */

import { escapeHtml } from "./strategy-engine.js";
import { CATALOG, CATEGORIES, NEW_BADGE_DAYS } from "./catalog.js";

const MS_PER_DAY = 86_400_000;

function isNew(addedIso){
  if(!addedIso) return false;
  const added = new Date(addedIso + "T00:00:00Z").getTime();
  const ageDays = (Date.now() - added) / MS_PER_DAY;
  return ageDays >= 0 && ageDays <= NEW_BADGE_DAYS;
}

function typeLabel(type){
  const cat = CATEGORIES.find(c => c.key === type);
  return cat ? cat.label.replace(/S$/, "") : type.toUpperCase();
}

function renderCard(item){
  const newBadge = isNew(item.added)
    ? `<span class="card-new">NEW</span>` : "";
  return `<a class="card" href="${escapeHtml(item.page)}">
    <div class="card-top">
      <span class="card-type">${escapeHtml(typeLabel(item.type))}</span>
      ${newBadge}
    </div>
    <div class="card-title">${escapeHtml(item.title)}</div>
    <div class="card-blurb">${escapeHtml(item.blurb)}</div>
    <div class="card-action">OPEN →</div>
  </a>`;
}

// Home section anchors are the plural of the category key (e.g. #portfolios,
// #reports) so the masthead nav links land on the right section.
const SECTION_ID = {
  strategy:   "strategies",
  calculator: "calculators",
  portfolio:  "portfolios",
  report:     "reports",
};

function renderCategory(cat){
  const items = CATALOG.filter(i => i.type === cat.key);
  const note = items.length > 0
    ? `${items.length} ${items.length === 1 ? "thing" : "things"}`
    : "coming soon";

  const body = items.length > 0
    ? `<div class="card-grid">${items.map(renderCard).join("")}</div>`
    : `<div class="cat-empty">Nothing here yet — check back as new pieces ship.</div>`;

  return `<section class="panel" id="${escapeHtml(SECTION_ID[cat.key] || cat.key)}">
    <div class="sec-h">
      <span class="tick"></span>
      <h2>${escapeHtml(cat.label)}</h2>
      <span class="note">${escapeHtml(note)}</span>
    </div>
    <p class="cat-blurb">${escapeHtml(cat.blurb)}</p>
    ${body}
  </section>`;
}

document.getElementById("catalog-root").innerHTML =
  CATEGORIES.map(renderCategory).join("");

// Smoothly scroll to anchor on initial load if present
if(location.hash){
  const el = document.querySelector(location.hash);
  if(el) el.scrollIntoView({behavior:"instant", block:"start"});
}
