// Weekly review · step 4 — BOOK (shown as MY STOCKS): should I keep what I own?
//
// Every open position re-judged by the strategy (rv-holdings.js): the stop
// the rules give it this week, whether the thesis is intact, degraded or
// broken, where it stands in R, and whether a report is due. The actions
// themselves are issued on ORDERS; this page is the review.

import "./nav.js";
import { requireAuth, mountAccountBar, fmtGBP, esc } from "./neon.js";
import { loadScorecards, stepStrip, px, num, failInto, SAY, setupName, xRisk } from "./review.js";
import { daysBetween } from "./scorecard.js";
import { loadBook, evaluate } from "./rv-holdings.js";

const root = document.getElementById("book-root");
const optbar = document.getElementById("optbar");
let week = null;

(async function boot() {
  try {
    const sc = await loadScorecards();
    document.getElementById("steps").innerHTML = stepStrip("book", { week: sc.week });
  } catch (e) {
    return failInto(root, "the weekly scorecards", e);
  }
  const session = await requireAuth(root);
  mountAccountBar(optbar, session);
  root.innerHTML = `<div class="rv-empty">Checking your stocks…</div>`;
  try {
    const book = await loadBook();
    const byAcct = [];
    for (const acc of book.accounts) byAcct.push({ acc, ev: await evaluate(book, acc.id) });
    week = byAcct[0]?.ev.sc.week ?? null;
    render(byAcct);
  } catch (e) {
    failInto(root, "your stocks", e);
  }
})();

function render(byAcct) {
  if (!byAcct.length) {
    root.innerHTML = `<div class="rv-page"><div class="rv-empty">Nothing here yet. Add your broker account on <a href="portfolio.html" style="color:var(--cyan)">Portfolio</a>, then record what you bought on <a href="trades.html" style="color:var(--cyan)">Trades</a>.</div></div>`;
    return;
  }
  const all = byAcct.flatMap((x) => x.ev.holdings);
  const exits = all.filter((h) => h.m?.action === "EXIT");
  const due = all.filter((h) => h.earningsSoon);
  root.innerHTML =
    `<div class="rv-page">` +
    `<div class="rv-banner ${exits.length ? "rv-def" : "rv-full"}">` +
    `<span class="rv-banner-lv">${exits.length ? `SELL ${exits.length}` : "KEEP THEM ALL"}</span>` +
    `<span class="rv-banner-kv">${exits.length ? `${exits.length} of your ${all.length} stocks should be sold this week` : `all ${all.length} of your stocks are fine to keep this week`}</span>` +
    (due.length ? `<span class="rv-banner-kv">${due.length} ${due.length === 1 ? "reports" : "report"} earnings soon</span>` : "") +
    `</div>` +
    byAcct.map(({ acc, ev }) => account(acc, ev)).join("") +
    `<p class="rv-note">Click a stock to see its full check. The stop-loss is worked out for you from when and at what price you bought, and it only ever moves up. Make sure the stop-loss order at your broker matches the one here (↑ means it went up this week; the To do page lists the changes). "Result so far" compares your gain or loss with the amount you risked: +1× means you're up by as much as you risked. Stocks outside the S&P 500 (such as UK ETFs) aren't covered.</p>` +
    `</div>`;
}

function account(acc, ev) {
  const rows = ev.holdings.map(row).join("");
  const heat = ev.holdings.reduce((s, h) => s + (h.riskGBP || 0), 0);
  return (
    `<section class="rv-sec"><div class="rv-h"><span>${esc(acc.name)}${acc.type ? ` · ${esc(acc.type)}` : ""}</span>` +
    `<span class="rv-h-r">worth ${fmtGBP(ev.equityGBP)} · cash ${fmtGBP(ev.cashGBP)} · you'd lose ${fmtGBP(heat)}${ev.equityGBP > 0 ? ` (${num((heat / ev.equityGBP) * 100, 1)}%)` : ""} if every stop-loss hit</span></div>` +
    (ev.holdings.length
      ? `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr>` +
        `<th>stock</th><th>do</th><th>trend</th><th class="r">shares</th><th class="r">you paid</th><th class="r">price now</th>` +
        `<th class="r">stop-loss</th><th class="r">result so far</th><th class="r">held</th><th class="r">worth</th><th>why</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="dim-note">You don't own any stocks in this account.</div>`) +
    `</section>`
  );
}

function row(h) {
  const m = h.m;
  const act = !h.scored ? `<span class="rv-chip">—</span>` : m ? `<span class="rv-chip rv-${m.action.toLowerCase()}">${SAY.action[m.action] ?? m.action}</span>` : `<span class="rv-chip">—</span>`;
  const raised = m && m.prevStop != null && m.stop != null && m.stop > m.prevStop + 1e-9;
  const why = !h.scored
    ? "not covered: we only check S&P 500 stocks"
    : [
        m?.reason,
        m?.action === "EXIT" && h.row?.status === "BUY" ? `but it's a fresh buy (${setupName(h.row.setup)}) this week, so keep it: see To do` : null,
        h.earningsSoon ? `earnings report due ${h.earningsSoon}: the price may jump` : null,
      ].filter(Boolean).join(" · ");
  const held = h.firstBuy && week ? Math.max(0, Math.round(daysBetween(h.firstBuy, week) / 7)) : null;
  return (
    `<tr class="${m?.action === "EXIT" ? "bk-pos-exit " : ""}${h.scored ? "rv-link" : ""}"${h.scored ? ` onclick="location.href='card.html?t=${encodeURIComponent(h.t)}'"` : ""}>` +
    `<td><span class="ps-tkr">${esc(h.t)}</span></td>` +
    `<td>${act}</td>` +
    `<td class="${h.thesis.cls}">${h.thesis.word}</td>` +
    `<td class="r">${num(h.qty, 2)}</td>` +
    `<td class="r">${px(h.avgNative)}</td>` +
    `<td class="r">${px(h.priceNative)}</td>` +
    `<td class="r">${h.stopNative == null ? "—" : px(h.stopNative)}${raised ? ` <span class="rv-new">↑</span>` : ""}</td>` +
    `<td class="r ${h.rNow > 0 ? "up" : h.rNow < 0 ? "down" : ""}">${h.rNow == null ? "—" : `${xRisk(h.rNow)} risk`}</td>` +
    `<td class="r">${held != null ? `${held} wk` : "—"}</td>` +
    `<td class="r">${h.valueGBP == null ? "—" : fmtGBP(h.valueGBP)}</td>` +
    `<td class="wrap dim-note">${esc(why)}</td>` +
    `</tr>`
  );
}
