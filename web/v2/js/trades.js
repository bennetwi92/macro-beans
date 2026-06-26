// Trades page — compact, inline-editable trade log for daily entry.
// "+ Add trade" drops a blank editable row at the top; fill the cells and save.
// Click any row to edit it inline. Accounts are managed on the Portfolio page.
// Prices are entered in the instrument's native currency (auto-deduced); the
// Value column and all PnL are GBP.

import "./nav.js";
import { db, esc, fmtGBP, fmtNum, todayISO, requireAuth, mountAccountBar } from "./neon.js";
import { loadPrices, guessCurrency, toGBP, CURRENCIES } from "./prices.js";

const root = document.getElementById("trade-root");
const optbar = document.getElementById("optbar");

let accounts = [], positions = [], trades = [];
let editing = null; // trade id being edited, or "__new__", or null

(async function boot() {
  const session = await requireAuth(root);
  mountAccountBar(optbar, session);
  await loadPrices();
  loadAll();
})();

async function loadAll() {
  root.innerHTML = `<div class="req-msg">Loading book…</div>`;
  const [a, p, t] = await Promise.all([
    db.from("accounts").select("*").order("name"),
    db.from("positions").select("*").order("created_at"),
    db.from("trades").select("*,positions(instrument,name,ref,account_id,currency,accounts(name))").order("traded_at", { ascending: false }).order("created_at", { ascending: false }),
  ]);
  if (a.error) { root.innerHTML = `<div class="req-msg">Could not load (${esc(a.error.message)})</div>`; return; }
  accounts = a.data || []; positions = p.data || []; trades = t.data || [];
  render();
}

/* ---------- render ---------- */

function render() {
  if (!accounts.length) {
    root.innerHTML = `<div class="np-wrap"><div class="req-msg">No accounts yet — create one on the <a href="portfolio.html">Portfolio</a> page first.</div></div>`;
    return;
  }
  root.innerHTML =
    `<div class="tr-page">` +
    `<div class="tr-head"><div class="np-h">TRADES <span class="dim-note">${trades.length}</span></div>` +
    `<button id="tr-add" class="req-btn"${editing ? " disabled" : ""}>＋ Add trade</button></div>` +
    `<div class="logwrap"><table class="np-tbl trade-tbl">` +
    `<colgroup><col class="c-date"><col class="c-acct"><col class="c-pos"><col class="c-side"><col class="c-num"><col class="c-num"><col class="c-num"><col class="c-num"><col class="c-act"></colgroup>` +
    `<thead><tr><th>Date</th><th>Account</th><th>Instrument</th><th>Side</th><th class="r">Qty</th><th class="r">Price</th><th class="r">Fees £</th><th class="r">Value £</th><th></th></tr></thead>` +
    `<tbody id="tr-body">${bodyRows()}</tbody></table></div></div>`;
  wire();
}

function bodyRows() {
  let html = "";
  if (editing === "__new__") html += editRow(null);
  for (const t of trades) html += t.id === editing ? editRow(t) : displayRow(t);
  if (!trades.length && editing !== "__new__") html += `<tr><td colspan="9" class="dim-note">No trades yet — ＋ Add trade.</td></tr>`;
  return html;
}

function displayRow(t) {
  const pos = t.positions || {}, acc = pos.accounts || {};
  const valGBP = toGBP(Number(t.price), pos.currency);
  const value = valGBP != null ? valGBP * Number(t.quantity) : null;
  return (
    `<tr class="tr-row" data-id="${t.id}">` +
    `<td>${esc(t.traded_at)}</td>` +
    `<td>${esc(acc.name || "")}</td>` +
    `<td>${esc(pos.instrument || "")} <span class="dim-note">#${pos.ref}</span>${pos.name ? ` <span class="dim-note">${esc(pos.name)}</span>` : ""}</td>` +
    `<td class="${t.side === "sell" ? "down" : "up"}">${esc(t.side)}</td>` +
    `<td class="r">${fmtNum(t.quantity)}</td>` +
    `<td class="r">${fmtNum(t.price)} <span class="dim-note">${esc(pos.currency || "")}</span></td>` +
    `<td class="r">${Number(t.fees) ? fmtGBP(t.fees) : "—"}</td>` +
    `<td class="r">${value != null ? fmtGBP(value) : `<span class="dim-note">—</span>`}</td>` +
    `<td class="r te-actions"><button class="req-ic" data-edit="${t.id}" title="Edit">✎</button><button class="req-ic" data-del="${t.id}" title="Delete">✕</button></td>` +
    `</tr>`
  );
}

function editRow(t) {
  const id = t ? t.id : "__new__";
  const accId = (t && t.positions && t.positions.account_id) || accounts[0].id;
  const ccyOpts = CURRENCIES.map((c) => `<option>${c}</option>`).join("");
  return (
    `<tr class="tr-edit" data-id="${id}">` +
    `<td><input class="te-date req-in" type="date" value="${t ? t.traded_at : todayISO()}"></td>` +
    `<td><select class="te-acct req-in">${accounts.map((a) => `<option value="${a.id}"${a.id === accId ? " selected" : ""}>${esc(a.name)}</option>`).join("")}</select></td>` +
    `<td class="te-poscell"><select class="te-pos req-in"></select><div class="te-new" hidden><input class="te-instr req-in" placeholder="new ticker e.g. FWRG.L"><select class="te-ccy req-in" title="Currency (GBp = pence)">${ccyOpts}</select></div></td>` +
    `<td><select class="te-side req-in"><option value="buy"${t && t.side === "buy" ? " selected" : ""}>buy</option><option value="sell"${t && t.side === "sell" ? " selected" : ""}>sell</option></select></td>` +
    `<td><input class="te-qty req-in" type="number" step="any" min="0" value="${t ? t.quantity : ""}"></td>` +
    `<td><input class="te-price req-in" type="number" step="any" min="0" value="${t ? t.price : ""}"></td>` +
    `<td><input class="te-fees req-in" type="number" step="any" min="0" value="${t ? t.fees : "0"}"></td>` +
    `<td class="r dim-note">—</td>` +
    `<td class="r te-actions"><button class="req-ic save" data-saverow="${id}" title="Save">✓</button><button class="req-ic" data-cancel="1" title="Cancel">✕</button></td>` +
    `</tr>`
  );
}

/* ---------- wiring ---------- */

function wire() {
  document.getElementById("tr-add").onclick = () => { if (!editing) { editing = "__new__"; render(); } };
  const body = document.getElementById("tr-body");
  body.addEventListener("click", onBodyClick);

  const er = body.querySelector(".tr-edit");
  if (er) wireEditRow(er);
}

function onBodyClick(e) {
  const t = e.target;
  if (t.dataset.edit) { editing = t.dataset.edit; render(); }
  else if (t.dataset.del) delTrade(t.dataset.del);
  else if (t.dataset.cancel) { editing = null; render(); }
  else if (t.dataset.saverow) saveRow(t.dataset.saverow, t.closest(".tr-edit"));
}

function wireEditRow(er) {
  const selectedPos = editing !== "__new__" ? findTrade(editing)?.position_id : null;
  const acctSel = er.querySelector(".te-acct");
  populatePos(er, acctSel.value, selectedPos);
  acctSel.onchange = () => populatePos(er, acctSel.value, null);
  er.querySelector(".te-pos").onchange = () => toggleNew(er);
  er.querySelector(".te-instr").addEventListener("input", (ev) => { er.querySelector(".te-ccy").value = guessCurrency(ev.target.value); });
}

function populatePos(er, accountId, selectedPosId) {
  const sel = er.querySelector(".te-pos");
  const inAcct = positions.filter((p) => p.account_id === accountId);
  sel.innerHTML =
    inAcct.map((p) => `<option value="${p.id}"${p.id === selectedPosId ? " selected" : ""}>${esc(p.instrument)} #${p.ref}${p.name ? ` · ${esc(p.name)}` : ""}</option>`).join("") +
    `<option value="__new__">＋ new position…</option>`;
  if (!selectedPosId && !inAcct.length) sel.value = "__new__";
  toggleNew(er);
}

function toggleNew(er) {
  er.querySelector(".te-new").hidden = er.querySelector(".te-pos").value !== "__new__";
}

const findTrade = (id) => trades.find((t) => t.id === id);

/* ---------- persistence ---------- */

async function saveRow(id, er) {
  const v = (sel) => er.querySelector(sel).value;
  const quantity = parseFloat(v(".te-qty"));
  const price = parseFloat(v(".te-price"));
  const fees = parseFloat(v(".te-fees")) || 0;
  const side = v(".te-side");
  const traded_at = v(".te-date") || todayISO();
  const note = null; // note field removed from the compact form
  if (!(quantity > 0) || !(price >= 0)) return; // need qty + price

  const accountId = v(".te-acct");
  let position_id = v(".te-pos");
  if (position_id === "__new__") {
    const instrument = er.querySelector(".te-instr").value.trim().toUpperCase();
    if (!instrument) { er.querySelector(".te-instr").focus(); return; }
    const currency = er.querySelector(".te-ccy").value || guessCurrency(instrument);
    const pr = await db.from("positions").insert({ account_id: accountId, instrument, currency }).select();
    if (pr.error) return alert("Create position failed: " + pr.error.message);
    position_id = pr.data[0].id;
  }

  const fields = { position_id, side, quantity, price, fees, traded_at, note };
  const res = id === "__new__"
    ? await db.from("trades").insert(fields).select()
    : await db.from("trades").update(fields).eq("id", id);
  if (res.error) return alert("Save failed: " + res.error.message);
  editing = null;
  loadAll();
}

async function delTrade(id) {
  const { error } = await db.from("trades").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}
