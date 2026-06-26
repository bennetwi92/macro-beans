// Portfolio page — account-level roll-ups. Per account: cash (deposits/
// withdrawals + trade settlement) + market value of open positions, plus
// realised/unrealised PnL and total value. An overall summary on top. GBP.

import "./nav.js";
import { db, esc, fmtGBP, requireAuth, mountAccountBar } from "./neon.js";
import { gbpPositionMetrics, tradeCashGBP } from "./book.js";
import { loadPrices } from "./prices.js";

const root = document.getElementById("pf-root");
const optbar = document.getElementById("optbar");

const KINDS = ["Deposit", "Withdrawal", "Dividend", "Fee", "Adjustment"];
let accounts = [], positions = [], trades = [], cash = [];

(async function boot() {
  const session = await requireAuth(root);
  mountAccountBar(optbar, session);
  await loadPrices();
  loadAll();
})();

async function loadAll() {
  root.innerHTML = `<div class="req-msg">Loading portfolio…</div>`;
  const [a, p, t, c] = await Promise.all([
    db.from("accounts").select("*").order("name"),
    db.from("positions").select("*"),
    db.from("trades").select("*"),
    db.from("cash_flows").select("*").order("dated", { ascending: false }).order("created_at", { ascending: false }),
  ]);
  if (a.error) { root.innerHTML = `<div class="req-msg">Could not load (${esc(a.error.message)})</div>`; return; }
  accounts = a.data || []; positions = p.data || []; trades = t.data || []; cash = c.data || [];
  render();
}

/* ---------- compute ---------- */

function accountMetrics(acc, posById) {
  const accPos = positions.filter((p) => p.account_id === acc.id);
  const posIds = new Set(accPos.map((p) => p.id));
  let realized = 0, unreal = 0, mktVal = 0, openCount = 0, unmarked = 0;
  for (const p of accPos) {
    const m = gbpPositionMetrics(p, trades.filter((t) => t.position_id === p.id));
    realized += m.realized;
    if (m.open) { openCount += 1; if (m.markGBP != null) { mktVal += m.mktVal; unreal += m.unreal; } else unmarked += 1; }
  }
  let cashBal = 0;
  for (const cf of cash) if (cf.account_id === acc.id) cashBal += +cf.amount;
  for (const t of trades) { const p = posById[t.position_id]; if (p && posIds.has(t.position_id)) cashBal += tradeCashGBP(t, p.currency || "GBP"); }
  return { realized, unreal, mktVal, cashBal, totalValue: cashBal + mktVal, totalPnL: realized + unreal, openCount, unmarked };
}

/* ---------- render ---------- */

const pnl = (v) => (v == null ? `<span class="dim-note">—</span>` : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${fmtGBP(v)}</span>`);
const metric = (label, value) => `<div class="pf-metric"><div class="pf-ml">${label}</div><div class="pf-mv">${value}</div></div>`;

function addAccountSection() {
  return (
    `<section class="np-sec"><div class="np-h">ADD ACCOUNT</div><div class="acct-add">` +
    `<input id="acct-name" class="req-in" placeholder="Account name (e.g. SIPP)">` +
    `<select id="acct-type" class="req-in"><option value="">type…</option><option>ISA</option><option>SIPP</option><option>GIA</option><option>CFD</option><option>Other</option></select>` +
    `<button id="acct-add" class="req-btn">Add account</button></div></section>`
  );
}

function render() {
  if (!accounts.length) {
    root.innerHTML = `<div class="np-wrap"><div class="req-msg">No accounts yet — add one below, then log trades on the Trades page.</div>${addAccountSection()}</div>`;
    wireAccounts();
    return;
  }
  const posById = Object.fromEntries(positions.map((p) => [p.id, p]));
  const ms = accounts.map((a) => ({ acc: a, m: accountMetrics(a, posById) }));
  const tot = ms.reduce((s, x) => ({
    totalValue: s.totalValue + x.m.totalValue, cashBal: s.cashBal + x.m.cashBal, mktVal: s.mktVal + x.m.mktVal,
    realized: s.realized + x.m.realized, unreal: s.unreal + x.m.unreal, totalPnL: s.totalPnL + x.m.totalPnL,
    openCount: s.openCount + x.m.openCount, unmarked: s.unmarked + x.m.unmarked,
  }), { totalValue: 0, cashBal: 0, mktVal: 0, realized: 0, unreal: 0, totalPnL: 0, openCount: 0, unmarked: 0 });

  root.innerHTML =
    `<div class="np-wrap">` +
    overallCard(tot) +
    ms.map(({ acc, m }) => accountCard(acc, m)).join("") +
    addAccountSection() +
    `</div>`;
  wire();
  wireAccounts();
}

function overallCard(t) {
  return (
    `<section class="pf-overall">` +
    `<div class="pf-overall-h"><span class="np-h">PORTFOLIO</span><span class="pf-total">${fmtGBP(t.totalValue)}</span></div>` +
    `<div class="pf-metrics">` +
    metric("Cash", fmtGBP(t.cashBal)) +
    metric("Market value", fmtGBP(t.mktVal)) +
    metric("Realised", pnl(t.realized)) +
    metric("Unrealised", pnl(t.unreal)) +
    metric("Total PnL", pnl(t.totalPnL)) +
    metric("Open positions", String(t.openCount)) +
    `</div>` +
    (t.unmarked ? `<div class="dim-note pf-warn">${t.unmarked} open position${t.unmarked === 1 ? "" : "s"} without a mark — set marks on the Positions page for full valuation.</div>` : "") +
    `</section>`
  );
}

function accountCard(acc, m) {
  const flows = cash.filter((cf) => cf.account_id === acc.id);
  return (
    `<section class="np-sec pf-card">` +
    `<div class="pf-card-h"><div class="np-h">${esc(acc.name)}${acc.type ? ` · ${esc(acc.type)}` : ""}</div><div class="pf-card-r"><span class="pf-card-total">${fmtGBP(m.totalValue)}</span><button class="req-ic pf-del-acct" data-delacct="${acc.id}" title="Delete account and ALL its data">✕</button></div></div>` +
    `<div class="pf-metrics">` +
    metric("Cash", fmtGBP(m.cashBal)) +
    metric("Market value", fmtGBP(m.mktVal)) +
    metric("Realised", pnl(m.realized)) +
    metric("Unrealised", pnl(m.unreal)) +
    metric("Total PnL", pnl(m.totalPnL)) +
    metric("Open positions", String(m.openCount) + (m.unmarked ? ` <span class="dim-note">(${m.unmarked} unmarked)</span>` : "")) +
    `</div>` +
    cashSection(acc, flows) +
    `</section>`
  );
}

function cashSection(acc, flows) {
  const rows = flows.length
    ? flows.map((cf) => `<tr><td>${esc(cf.dated)}</td><td>${esc(cf.kind)}</td><td class="r ${(+cf.amount) < 0 ? "down" : "up"}">${fmtGBP(cf.amount)}</td><td>${esc(cf.note || "")}</td><td class="r"><button class="req-ic" data-delcash="${cf.id}" title="Delete">✕</button></td></tr>`).join("")
    : `<tr><td colspan="5" class="dim-note">No deposits/withdrawals yet.</td></tr>`;
  return (
    `<details class="pf-cash"><summary>Cash flows <span class="dim-note">(deposits, withdrawals, dividends…) — balance also includes trade settlement</span></summary>` +
    `<div class="cash-add">` +
    `<select class="req-in cf-kind" data-acct="${acc.id}">${KINDS.map((k) => `<option>${k}</option>`).join("")}</select>` +
    `<input class="req-in cf-amt" data-acct="${acc.id}" type="number" step="any" placeholder="amount £">` +
    `<input class="req-in cf-date" data-acct="${acc.id}" type="date" value="${todayISO()}">` +
    `<input class="req-in cf-note" data-acct="${acc.id}" placeholder="note (optional)">` +
    `<button class="req-btn cf-add" data-acct="${acc.id}">Add</button>` +
    `</div>` +
    `<div class="logwrap"><table class="np-tbl"><thead><tr><th>Date</th><th>Kind</th><th class="r">Amount</th><th>Note</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` +
    `</details>`
  );
}

const todayISO = () => { const d = new Date(); const p = (x) => String(x).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; };

/* ---------- cash flow ops ---------- */

function wire() {
  root.addEventListener("click", (e) => {
    const t = e.target;
    if (t.classList.contains("cf-add")) addCash(t.dataset.acct);
    else if (t.dataset.delcash) delCash(t.dataset.delcash);
    else if (t.dataset.delacct) delAccount(t.dataset.delacct);
  });
}

function wireAccounts() {
  const btn = document.getElementById("acct-add");
  if (btn) btn.onclick = addAccount;
}

async function addAccount() {
  const name = document.getElementById("acct-name").value.trim();
  const type = document.getElementById("acct-type").value || null;
  if (!name) return;
  const { error } = await db.from("accounts").insert({ name, type }).select();
  if (error) return alert("Add account failed: " + error.message);
  loadAll();
}

async function delAccount(id) {
  const acc = accounts.find((a) => a.id === id);
  if (!confirm(`Delete account "${acc?.name}" and ALL its positions, trades and cash flows? This cannot be undone.`)) return;
  const { error } = await db.from("accounts").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}

async function addCash(accountId) {
  const q = (sel) => root.querySelector(`${sel}[data-acct="${accountId}"]`);
  const kind = q(".cf-kind").value;
  const raw = parseFloat(q(".cf-amt").value);
  if (!(Math.abs(raw) >= 0) || Number.isNaN(raw)) return;
  const mag = Math.abs(raw);
  let amount;
  if (kind === "Withdrawal" || kind === "Fee") amount = -mag;
  else if (kind === "Adjustment") amount = raw; // as entered (can be negative)
  else amount = mag; // Deposit, Dividend
  const dated = q(".cf-date").value || todayISO();
  const note = q(".cf-note").value.trim() || null;
  const { error } = await db.from("cash_flows").insert({ account_id: accountId, kind, amount, dated, note }).select();
  if (error) return alert("Add cash flow failed: " + error.message);
  loadAll();
}

async function delCash(id) {
  const { error } = await db.from("cash_flows").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}
