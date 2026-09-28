// Weekly review · step 5 — ORDERS (shown as TO DO): what exactly do I do on Monday?
//
// The week's orders for one account, from construct.js `construct`: EXIT what
// the rules say is over, TRAIL the stops they have ratcheted, TRIM anything
// past the concentration band, then BUY this week's candidates in score order,
// each sized from its stop, until the TAPE's budget, the heat cap, the cash or
// a concentration cap says stop. Ends in a plain-text checklist to take to the
// broker. Nothing here places an order.

import "./nav.js";
import { requireAuth, mountAccountBar, fmtGBP, esc } from "./neon.js";
import { loadScorecards, stepStrip, px, num, levelClass, failInto, SAY } from "./review.js";
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
    return failInto(root, "your stocks", e);
  }
  if (!book.accounts.length) {
    root.innerHTML = `<div class="rv-page"><div class="rv-empty">Nothing here yet. Add your broker account on <a href="portfolio.html" style="color:var(--cyan)">Portfolio</a>.</div></div>`;
    return;
  }
  // Default to the ISA: the account this strategy was sized for.
  accountId = (book.accounts.find((a) => /isa/i.test(a.type || a.name)) || book.accounts[0]).id;
  run();
})();

async function run() {
  root.innerHTML = `<div class="rv-empty">Working out this week's to-do list…</div>`;
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
    `</select><span>worth <b style="color:var(--ink)">${fmtGBP(ev.equityGBP)}</b> · cash ${fmtGBP(ev.cashGBP)}</span></div>`;
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
    `<span class="rv-banner-lv">${SAY.level[budget?.level] ?? "—"}</span>` +
    `<span class="rv-banner-kv">each new stock risks <b>${budget?.riskPct ?? "—"}%</b> of your account</span>` +
    `<span class="rv-banner-kv">stocks owned after <b>${res.positionsAfter}</b> of ${CAPS.maxPositions} max</span>` +
    `<span class="rv-banner-kv">cash left <b>${fmtGBP(res.cashAfter)}</b></span>` +
    `<span class="rv-banner-kv" title="What you would lose if every stop-loss were hit at once">at risk <b>${pctOf(res.heatBefore)}</b> → <b>${pctOf(res.heatAfter)}</b> (limit ${heatCapPct}%)</span>` +
    `</div>` +
    (!fxOk ? `<div class="cd-veto" style="margin-bottom:10px">The pound/dollar exchange rate is missing this week, so we can't work out how many shares to buy. Sells and stop-loss changes below still apply.</div>` : "") +
    `<section class="rv-sec"><div class="rv-h"><span>Your to-do list · place these for Monday's open</span><span class="rv-h-r">prices to Friday ${esc(sc.week)}</span></div>` +
    (res.orders.length
      ? `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th>do</th><th>stock</th><th class="r">shares</th><th class="r">price</th><th class="r">cost £</th><th class="r">stop-loss</th><th class="r">could lose £</th><th>why</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="rv-empty" style="padding:10px 0">Nothing to do this week. Nothing needs selling and nothing is worth buying. Holding cash is fine.</div>`) +
    `</section>` +
    (skipped
      ? `<section class="rv-sec"><div class="rv-h"><span>Buys we left out</span><span class="rv-h-r">and why</span></div>` +
        `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th>stock</th><th class="r">score</th><th>why</th></tr></thead><tbody>${skipped}</tbody></table></div></section>`
      : "") +
    `<section class="rv-sec"><div class="rv-h"><span>Checklist: copy this and work through it in your broker's app</span></div>` +
    `<textarea class="od-copy" readonly>${esc(checklist(sc, res))}</textarea></section>` +
    `<p class="rv-note">Do them in this order: sells first (they free up cash), then stop-loss changes, then buys, best first. The number of shares is set so that if a stock falls to its stop-loss you lose about ${budget?.riskPct ?? "—"}% of your account, never more. To spread risk, no stock is more than ${CAPS.maxPositionPct}% of the account, you hold at most ${CAPS.maxPerSector} from one industry, and we skip a stock that moves almost in step with one you own. Prices are Friday's; Monday's will be a little different, which is fine. Keep the same stop-loss price.</p>` +
    `<details class="rv-note"><summary>The fine print</summary>Each buy risks ${budget?.riskPct ?? "—"}% of your account, scaled 60–100% by score: shares = risk ÷ (buy price − stop-loss). "Moves in step" means a correlation over ${CAPS.maxCorr}. A stock is trimmed only once it grows past ${CAPS.trimPct}% of the account, because trading more often doesn't pay. Costs assume ${COSTS.fxPct}% currency conversion each way. A stock the rules would sell that is a fresh buy the same week is kept, with the new stop-loss, rather than sold and bought back.</details>` +
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
    return `<tr><td><span class="rv-chip rv-trail">${SAY.action.RESET}</span></td><td>${link}</td><td></td><td></td><td></td><td class="r">$${px(o.stopNative)}</td><td></td><td class="wrap dim-note">${esc(o.reason)}</td></tr>`;
  }
  if (o.action === "TRAIL") {
    return `<tr><td><span class="${cls}">${SAY.action.TRAIL} ↑</span></td><td>${link}</td><td></td><td></td><td></td><td class="r">$${px(o.stopNative)}</td><td></td><td class="wrap dim-note">${esc(o.reason)}</td></tr>`;
  }
  return (
    `<tr><td><span class="${cls}">${SAY.action[o.action] ?? o.action}</span></td><td>${link}</td>` +
    `<td class="r">${num(o.qty, 2)}</td>` +
    `<td class="r">${o.entryNative != null ? `$${px(o.entryNative)}` : fmtGBP(o.priceGBP)}</td>` +
    `<td class="r">${fmtGBP((o.valueGBP ?? o.qty * o.priceGBP) || 0)}</td>` +
    `<td class="r">${o.stopNative != null ? `$${px(o.stopNative)}` : ""}</td>` +
    `<td class="r">${o.riskGBP != null ? fmtGBP(o.riskGBP) : ""}</td>` +
    `<td class="wrap dim-note">${esc(o.reason || "")}</td></tr>`
  );
}

function checklist(sc, res) {
  const L = [`Weekly to-do — prices to Friday ${sc.week}`, ""];
  if (!res.orders.length) L.push("Nothing to do this week. Hold cash.");
  for (const o of res.orders) {
    if (o.action === "EXIT") L.push(`[ ] SELL ALL ${num(o.qty, 2)} shares of ${o.t} at market on Monday. Why: ${o.reason}`);
    else if (o.action === "TRIM") L.push(`[ ] SELL ${num(o.qty, 2)} shares of ${o.t} at market on Monday. Why: ${o.reason}`);
    else if (o.action === "TRAIL") L.push(`[ ] ${o.t}: change the stop-loss order to $${px(o.stopNative)}`);
    else if (o.action === "RESET") L.push(`[ ] KEEP ${o.t}, and change its stop-loss order to $${px(o.stopNative)} (it's a fresh buy again this week)`);
    else if (o.action === "BUY") L.push(`[ ] BUY ${num(o.qty, 2)} shares of ${o.t} at market on Monday (about $${px(o.entryNative)}), then set a stop-loss order at $${px(o.stopNative)}`);
  }
  L.push("", "Afterwards, record what you actually bought and sold on the Trades page so next week's review is right.");
  return L.join("\n");
}
