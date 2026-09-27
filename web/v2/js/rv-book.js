// Weekly review · step 4 — BOOK: does what I hold still stand?
//
// Every open position re-judged by the strategy (rv-holdings.js): the stop
// the rules give it this week, whether the thesis is intact, degraded or
// broken, where it stands in R, and whether a report is due. The actions
// themselves are issued on ORDERS; this page is the review.

import "./nav.js";
import { requireAuth, mountAccountBar, fmtGBP, esc } from "./neon.js";
import { loadScorecards, stepStrip, px, num, failInto } from "./review.js";
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
  root.innerHTML = `<div class="rv-empty">Reviewing the book…</div>`;
  try {
    const book = await loadBook();
    const byAcct = [];
    for (const acc of book.accounts) byAcct.push({ acc, ev: await evaluate(book, acc.id) });
    week = byAcct[0]?.ev.sc.week ?? null;
    render(byAcct);
  } catch (e) {
    failInto(root, "the trading book", e);
  }
})();

function render(byAcct) {
  if (!byAcct.length) {
    root.innerHTML = `<div class="rv-page"><div class="rv-empty">No accounts yet. Add one on <a href="portfolio.html" style="color:var(--cyan)">Portfolio</a>, then log trades on <a href="trades.html" style="color:var(--cyan)">Trades</a>.</div></div>`;
    return;
  }
  const all = byAcct.flatMap((x) => x.ev.holdings);
  const exits = all.filter((h) => h.m?.action === "EXIT");
  const due = all.filter((h) => h.earningsSoon);
  root.innerHTML =
    `<div class="rv-page">` +
    `<div class="rv-banner ${exits.length ? "rv-def" : "rv-full"}">` +
    `<span class="rv-banner-lv">${exits.length ? `${exits.length} TO EXIT` : "BOOK INTACT"}</span>` +
    `<span class="rv-banner-kv">open positions <b>${all.length}</b></span>` +
    `<span class="rv-banner-kv">scored <b>${all.filter((h) => h.scored).length}</b></span>` +
    `<span class="rv-banner-kv">reports due <b>${due.length}</b></span>` +
    `</div>` +
    byAcct.map(({ acc, ev }) => account(acc, ev)).join("") +
    `<p class="rv-note">Stops are <b>derived</b>, not typed in. For each position the strategy's own trade is replayed from the week before its first buy, at its actual average cost: the initial stop under that week's low (at least 1 ATR), break-even at +1R, then 1 ATR under the 10-week. So the resting order at the broker should sit where this page says. If it doesn't, the page is right and the order is out of date. Positions outside the S&P 500 universe (the LSE ETFs) aren't scored.</p>` +
    `</div>`;
}

function account(acc, ev) {
  const rows = ev.holdings.map(row).join("");
  const heat = ev.holdings.reduce((s, h) => s + (h.riskGBP || 0), 0);
  return (
    `<section class="rv-sec"><div class="rv-h"><span>${esc(acc.name)}${acc.type ? ` · ${esc(acc.type)}` : ""}</span>` +
    `<span class="rv-h-r">equity ${fmtGBP(ev.equityGBP)} · cash ${fmtGBP(ev.cashGBP)} · open risk ${fmtGBP(heat)}${ev.equityGBP > 0 ? ` (${num((heat / ev.equityGBP) * 100, 1)}%)` : ""}</span></div>` +
    (ev.holdings.length
      ? `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr>` +
        `<th>name</th><th>verdict</th><th>thesis</th><th class="r">qty</th><th class="r">avg</th><th class="r">last</th>` +
        `<th class="r">stop</th><th class="r">R now</th><th class="r">held</th><th class="r">value</th><th>why</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="dim-note">No open positions.</div>`) +
    `</section>`
  );
}

function row(h) {
  const m = h.m;
  const act = !h.scored ? `<span class="rv-chip">OUTSIDE</span>` : m ? `<span class="rv-chip rv-${m.action.toLowerCase()}">${m.action}</span>` : `<span class="rv-chip">—</span>`;
  const raised = m && m.prevStop != null && m.stop != null && m.stop > m.prevStop + 1e-9;
  const why = !h.scored
    ? "not in the scored universe"
    : [
        m?.reason,
        m?.action === "EXIT" && h.row?.status === "BUY" ? `but a fresh ${h.row.setup} BUY this week: RESET on ORDERS` : null,
        h.earningsSoon ? `report due ${h.earningsSoon}` : null,
      ].filter(Boolean).join(" · ");
  const held = h.firstBuy && week ? Math.max(0, Math.round(daysBetween(h.firstBuy, week) / 7)) : null;
  return (
    `<tr class="${m?.action === "EXIT" ? "bk-pos-exit " : ""}${h.scored ? "rv-link" : ""}"${h.scored ? ` onclick="location.href='card.html?t=${encodeURIComponent(h.t)}'"` : ""}>` +
    `<td><span class="ps-tkr">${esc(h.t)}</span></td>` +
    `<td>${act}</td>` +
    `<td class="${h.thesis.cls}">${h.thesis.word}${h.row?.st ? ` <span class="dim-note">st${h.row.st}</span>` : ""}</td>` +
    `<td class="r">${num(h.qty, 2)}</td>` +
    `<td class="r">${px(h.avgNative)}</td>` +
    `<td class="r">${px(h.priceNative)}</td>` +
    `<td class="r">${h.stopNative == null ? "—" : px(h.stopNative)}${raised ? ` <span class="rv-new">↑</span>` : ""}</td>` +
    `<td class="r ${h.rNow > 0 ? "up" : h.rNow < 0 ? "down" : ""}">${h.rNow == null ? "—" : `${h.rNow >= 0 ? "+" : ""}${h.rNow.toFixed(2)}R`}</td>` +
    `<td class="r">${held != null ? `${held}w` : "—"}</td>` +
    `<td class="r">${h.valueGBP == null ? "—" : fmtGBP(h.valueGBP)}</td>` +
    `<td class="wrap dim-note">${esc(why)}</td>` +
    `</tr>`
  );
}
