// Weekly review · step 5 — ORDERS: what do I actually do?
//
// The week's orders for one account, from construct.js `construct`: EXIT what
// the rules say is over, TRAIL the stops they have ratcheted, TRIM anything
// past the concentration band, then BUY this week's candidates in score order,
// each sized from its stop, until the TAPE's budget, the heat cap, the cash or
// a concentration cap says stop. Ends in a plain-text checklist to take to the
// broker. Nothing here places an order.

import "./nav.js";
import { requireAuth, mountAccountBar, fmtGBP, esc } from "./neon.js";
import { loadScorecards, stepStrip, px, num, levelClass, failInto } from "./review.js";
import { loadBook, evaluate } from "./rv-holdings.js";
import { construct, CAPS, COSTS } from "./construct.js";
import { toGBP, fxRates } from "./prices.js";

const root = document.getElementById("orders-root");
const optbar = document.getElementById("optbar");
let book = null;
let accountId = null;

(async function boot() {
  try {
    const sc = await loadScorecards();
    document.getElementById("steps").innerHTML = stepStrip("orders", { week: sc.week });
  } catch (e) {
    return failInto(root, "the weekly scorecards", e);
  }
  const session = await requireAuth(root);
  mountAccountBar(optbar, session);
  try {
    book = await loadBook();
  } catch (e) {
    return failInto(root, "the trading book", e);
  }
  if (!book.accounts.length) {
    root.innerHTML = `<div class="rv-page"><div class="rv-empty">No accounts yet. Add one on <a href="portfolio.html" style="color:var(--cyan)">Portfolio</a>.</div></div>`;
    return;
  }
  // Default to the ISA: the account this strategy was sized for.
  accountId = (book.accounts.find((a) => /isa/i.test(a.type || a.name)) || book.accounts[0]).id;
  run();
})();

async function run() {
  root.innerHTML = `<div class="rv-empty">Building this week's orders…</div>`;
  const ev = await evaluate(book, accountId);
  const sc = ev.sc;
  const budget = sc.tape?.budget;
  const holdings = ev.holdings.map((h) => ({
    t: h.t,
    qty: h.qty,
    entryGBP: h.entryGBP,
    // Unscored positions carry no strategy stop: counted at zero risk, since
    // nothing here manages them.
    stopGBP: h.m?.prevStop != null ? toGBP(h.m.prevStop, h.cur) : h.stopGBP ?? h.entryGBP,
    newStopGBP: h.stopGBP,
    newStopNative: h.stopNative,
    priceGBP: h.priceGBP ?? h.entryGBP,
    sector: h.sector,
    action: h.m?.action === "EXIT" ? "EXIT" : "HOLD",
    reason: h.m?.reason,
    returns: h.returns,
  }));
  const candidates = sc.rows
    .filter((r) => r.status === "BUY" && r.plan)
    .sort((a, b) => b.total - a.total)
    .map((r) => ({ t: r.t, total: r.total, setup: r.setup, sector: r.s, entry: r.plan.entry, stop: r.plan.stop, returns: r.ret }));
  const fxOk = fxRates().gbpusd != null;
  const res = construct({
    equityGBP: ev.equityGBP,
    cashGBP: ev.cashGBP,
    holdings,
    candidates: fxOk ? candidates : [],
    budget,
    toGBP: (x) => toGBP(x, "USD"),
  });
  render(sc, ev, res, budget, fxOk);
}

function render(sc, ev, res, budget, fxOk) {
  const acctSel =
    `<div class="od-acct">ACCOUNT <select id="od-acct">` +
    book.accounts.map((a) => `<option value="${a.id}"${a.id === accountId ? " selected" : ""}>${esc(a.name)}${a.type ? ` · ${esc(a.type)}` : ""}</option>`).join("") +
    `</select><span>equity <b style="color:var(--ink)">${fmtGBP(ev.equityGBP)}</b> · cash ${fmtGBP(ev.cashGBP)}</span></div>`;
  const heatCapPct = budget?.heatMax ?? 0;
  const pctOf = (x) => (ev.equityGBP > 0 ? `${num((x / ev.equityGBP) * 100, 2)}%` : "—");
  const rows = res.orders.map(orderRow).join("");
  const skipped = res.skipped
    .map((s) => `<tr><td><a href="card.html?t=${encodeURIComponent(s.t)}" style="color:var(--ink)">${esc(s.t)}</a></td><td class="r">${s.total?.toFixed(0) ?? "—"}</td><td class="wrap dim-note">${esc(s.reason)}</td></tr>`)
    .join("");
  root.innerHTML =
    `<div class="rv-page">` +
    acctSel +
    `<div class="rv-banner ${levelClass(budget?.level)}">` +
    `<span class="rv-banner-lv">${budget?.level ?? "—"}</span>` +
    `<span class="rv-banner-kv">risk / new position <b>${budget?.riskPct ?? "—"}%</b></span>` +
    `<span class="rv-banner-kv">heat <b>${pctOf(res.heatBefore)}</b> → <b>${pctOf(res.heatAfter)}</b> of ${heatCapPct}% cap</span>` +
    `<span class="rv-banner-kv">positions after <b>${res.positionsAfter}</b> / ${CAPS.maxPositions}</span>` +
    `<span class="rv-banner-kv">cash after <b>${fmtGBP(res.cashAfter)}</b></span>` +
    `</div>` +
    (!fxOk ? `<div class="cd-veto" style="margin-bottom:10px">No GBP/USD rate in this build, so BUYs can't be sized. Holdings are still reviewed.</div>` : "") +
    `<section class="rv-sec"><div class="rv-h"><span>This week's orders · for Monday's open</span><span class="rv-h-r">week to ${esc(sc.week)}</span></div>` +
    (res.orders.length
      ? `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th>action</th><th>name</th><th class="r">qty</th><th class="r">price</th><th class="r">value £</th><th class="r">stop</th><th class="r">risk £</th><th>reason</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="rv-empty" style="padding:10px 0">No orders this week. Nothing to exit and nothing qualifies within the budget. Cash is a position.</div>`) +
    `</section>` +
    (skipped
      ? `<section class="rv-sec"><div class="rv-h"><span>Candidates not taken</span><span class="rv-h-r">and why</span></div>` +
        `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th>name</th><th class="r">score</th><th>reason</th></tr></thead><tbody>${skipped}</tbody></table></div></section>`
      : "") +
    `<section class="rv-sec"><div class="rv-h"><span>Checklist to take to the broker</span></div>` +
    `<textarea class="od-copy" readonly>${esc(checklist(sc, res))}</textarea></section>` +
    `<p class="rv-note">Order of work: exits first (they free cash and heat), then stop moves, then trims, then buys, best score first. A holding the rules would exit that is also a fresh BUY this week is a RESET: it's kept under the new trade's stop, not sold and bought back. Each buy risks ${budget?.riskPct ?? "—"}% of equity scaled 60–100% by score, so size = risk ÷ (entry − stop), capped at ${CAPS.maxPositionPct}% of equity, ${CAPS.maxPerSector} names a sector, and no near-twin (correlation over ${CAPS.maxCorr}) of a holding. The only rebalancing is the ${CAPS.trimPct}% trim band, because trading more often doesn't pay (docs/rebalancing/report.md). Costs assume ${COSTS.fxPct}% FX each way. Prices are Friday's close, and Monday's open will differ: keep the stop, re-size if it gaps.</p>` +
    `</div>`;
  document.getElementById("od-acct").onchange = (e) => {
    accountId = e.target.value;
    run();
  };
}

function orderRow(o) {
  const cls = `rv-chip rv-${o.action.toLowerCase()}`;
  const link = `<a href="card.html?t=${encodeURIComponent(o.t)}" style="color:var(--ink)"><span class="ps-tkr">${esc(o.t)}</span></a>`;
  if (o.action === "RESET") {
    return `<tr><td><span class="rv-chip rv-trail">RESET</span></td><td>${link}</td><td></td><td></td><td></td><td class="r">$${px(o.stopNative)}</td><td></td><td class="wrap dim-note">${esc(o.reason)}</td></tr>`;
  }
  if (o.action === "TRAIL") {
    return `<tr><td><span class="${cls}">STOP ↑</span></td><td>${link}</td><td></td><td></td><td></td><td class="r">$${px(o.stopNative)}</td><td></td><td class="wrap dim-note">${esc(o.reason)}</td></tr>`;
  }
  return (
    `<tr><td><span class="${cls}">${o.action}</span></td><td>${link}</td>` +
    `<td class="r">${num(o.qty, 2)}</td>` +
    `<td class="r">${o.entryNative != null ? `$${px(o.entryNative)}` : fmtGBP(o.priceGBP)}</td>` +
    `<td class="r">${fmtGBP((o.valueGBP ?? o.qty * o.priceGBP) || 0)}</td>` +
    `<td class="r">${o.stopNative != null ? `$${px(o.stopNative)}` : ""}</td>` +
    `<td class="r">${o.riskGBP != null ? fmtGBP(o.riskGBP) : ""}</td>` +
    `<td class="wrap dim-note">${esc(o.reason || "")}</td></tr>`
  );
}

function checklist(sc, res) {
  const L = [`Weekly review — week to ${sc.week}`, ""];
  if (!res.orders.length) L.push("No orders. Hold cash.");
  for (const o of res.orders) {
    if (o.action === "EXIT") L.push(`[ ] SELL ALL ${o.t} (${num(o.qty, 2)}) at the open — ${o.reason}`);
    else if (o.action === "TRIM") L.push(`[ ] SELL ${num(o.qty, 2)} ${o.t} at the open — ${o.reason}`);
    else if (o.action === "TRAIL") L.push(`[ ] MOVE STOP ${o.t} to $${px(o.stopNative)}`);
    else if (o.action === "RESET") L.push(`[ ] KEEP ${o.t}, MOVE STOP to $${px(o.stopNative)} — fresh ${o.setup} this week`);
    else if (o.action === "BUY") L.push(`[ ] BUY ${num(o.qty, 2)} ${o.t} at the open (~$${px(o.entryNative)}), then STOP at $${px(o.stopNative)} — ${o.reason}`);
  }
  L.push("", "Log every fill on the Trades page so the book stays the source of truth.");
  return L.join("\n");
}
