/* Macro Beans strategy switcher — a shared sub-nav rendered on every
   strategy and league page. It lets the reader jump straight between
   strategies and flip between the single-instrument view and the league
   table, with the current location highlighted. Driven by STRATEGIES in
   catalog.js so it stays in sync as strategies are added — no per-page
   wiring beyond including this module. */

import { escapeHtml } from "./strategy-engine.js";
import { STRATEGIES } from "./catalog.js";

const here = location.pathname.split("/").pop() || "index.html";

// Which strategy are we on, and are we looking at its league table?
const current = STRATEGIES.find(s => s.page === here || s.league === here);

if (current) {
  const onLeague = current.league === here;

  // One chip per strategy. While viewing a league table, keep the reader in
  // league view when they switch strategy (falling back to the single page
  // for strategies that have no league, e.g. cheap-or-dear).
  const chips = STRATEGIES.map(s => {
    const target = (onLeague && s.league) ? s.league : s.page;
    const on = s === current ? " on" : "";
    return `<a class="sw-chip${on}" href="${escapeHtml(target)}">${escapeHtml(s.title)}</a>`;
  }).join("");

  // Individual ↔ league toggle, only for strategies that have both views.
  const toggle = current.league
    ? `<div class="sw-view" role="group" aria-label="View">
         <a class="sw-opt${onLeague ? "" : " on"}" href="${escapeHtml(current.page)}">ONE INSTRUMENT</a>
         <a class="sw-opt${onLeague ? " on" : ""}" href="${escapeHtml(current.league)}">LEAGUE TABLE</a>
       </div>`
    : "";

  const nav = document.createElement("nav");
  nav.className = "switch";
  nav.setAttribute("aria-label", "Strategies");
  nav.innerHTML = `<div class="sw-strip">${chips}</div>${toggle}`;

  const strat = document.querySelector(".strat");
  if (strat) {
    // The switcher supersedes the lone strategy↔league back-link.
    const link = strat.querySelector(".strat-link");
    if (link) link.remove();
    strat.insertAdjacentElement("afterend", nav);
  } else {
    document.querySelector(".wrap")?.prepend(nav);
  }
}
