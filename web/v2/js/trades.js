// Trades page — manual trade entry + the accounts that hold them.
// Step 1 of the trading book: create accounts, log trades against positions
// (single-instrument; positions get their own PnL view on the Positions page).
// All amounts in GBP. Backed by Neon (RLS-scoped to the signed-in user).

import "./nav.js";
import { db, esc, fmtGBP, fmtNum, todayISO, requireAuth, mountAccountBar } from "./neon.js";
import { loadPrices, guessCurrency, toGBP, CURRENCIES } from "./prices.js";

const root = document.getElementById("trade-root");
const optbar = document.getElementById("optbar");

let accounts = [];
let positions = [];
let trades = [];

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
    db.from("trades").select("*,positions(instrument,name,account_id,currency,accounts(name))").order("traded_at", { ascending: false }).order("created_at", { ascending: false }),
  ]);
  if (a.error) { root.innerHTML = `<div class="req-msg">Could not load (${esc(a.error.message)})</div>`; return; }
  accounts = a.data || [];
  positions = p.data || [];
  trades = t.data || [];
  render();
}

/* ---------- render ---------- */

function render() {
  root.innerHTML = `<div class="np-wrap">${accountsSection()}${tradeFormSection()}${tradesSection()}</div>`;
  wireAccounts();
  wireTradeForm();
  root.querySelector(".trade-tbody")?.addEventListener("click", onTradeClick);
}

function accountsSection() {
  const chips = accounts.length
    ? accounts.map((a) => `<span class="acct-chip">${esc(a.name)}${a.type ? ` <em>${esc(a.type)}</em>` : ""}<button class="acct-del" data-id="${a.id}" title="Delete account and ALL its positions/trades">✕</button></span>`).join("")
    : `<span class="dim-note">No accounts yet — add one to start logging trades.</span>`;
  return (
    `<section class="np-sec"><div class="np-h">ACCOUNTS</div>` +
    `<div class="acct-list">${chips}</div>` +
    `<div class="acct-add">` +
    `<input id="acct-name" class="req-in" placeholder="Account name (e.g. SIPP)">` +
    `<select id="acct-type" class="req-in"><option value="">type…</option><option>ISA</option><option>SIPP</option><option>GIA</option><option>CFD</option><option>Other</option></select>` +
    `<button id="acct-add" class="req-btn">Add account</button>` +
    `</div></section>`
  );
}

function tradeFormSection() {
  if (!accounts.length) return "";
  return (
    `<section class="np-sec"><div class="np-h">ADD TRADE</div>` +
    `<div class="trade-form">` +
    field("Account", `<select id="tf-acct" class="req-in">${accounts.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select>`) +
    field("Position", `<select id="tf-pos" class="req-in"></select>`) +
    `<label class="ff tf-new" hidden><span>Instrument</span><input id="tf-instr" class="req-in" placeholder="ticker e.g. 3UKS.L"></label>` +
    `<label class="ff tf-new" hidden><span>Currency</span><select id="tf-ccy" class="req-in">${CURRENCIES.map((c) => `<option>${c}</option>`).join("")}</select></label>` +
    `<label class="ff tf-new" hidden><span>Label (optional)</span><input id="tf-name" class="req-in" placeholder="e.g. FTSE short"></label>` +
    field("Side", `<select id="tf-side" class="req-in"><option value="buy">Buy</option><option value="sell">Sell</option></select>`) +
    field("Quantity", `<input id="tf-qty" class="req-in" type="number" step="any" min="0">`) +
    field("Price £", `<input id="tf-price" class="req-in" type="number" step="any" min="0">`) +
    field("Fees £", `<input id="tf-fees" class="req-in" type="number" step="any" min="0" value="0">`) +
    field("Date", `<input id="tf-date" class="req-in" type="date" value="${todayISO()}">`) +
    `<label class="ff ff-wide"><span>Note (optional)</span><input id="tf-note" class="req-in"></label>` +
    `<button id="tf-add" class="req-btn">Add trade</button>` +
    `<div id="tf-err" class="auth-err" hidden></div>` +
    `</div></section>`
  );
}

const field = (label, control) => `<label class="ff"><span>${label}</span>${control}</label>`;

function tradesSection() {
  const rows = trades.length
    ? trades.map(tradeRow).join("")
    : `<tr><td colspan="9" class="dim-note">No trades yet.</td></tr>`;
  return (
    `<section class="np-sec"><div class="np-h">TRADES <span class="dim-note">${trades.length}</span></div>` +
    `<div class="logwrap"><table class="np-tbl">` +
    `<thead><tr><th>Date</th><th>Account</th><th>Instrument</th><th>Side</th><th class="r">Qty</th><th class="r">Price</th><th class="r">Fees £</th><th class="r">Value £</th><th></th></tr></thead>` +
    `<tbody class="trade-tbody">${rows}</tbody></table></div></section>`
  );
}

function tradeRow(t) {
  const pos = t.positions || {};
  const acc = pos.accounts || {};
  const valGBP = toGBP(Number(t.price), pos.currency);
  const value = valGBP != null ? valGBP * Number(t.quantity) : null;
  return (
    `<tr>` +
    `<td>${esc(t.traded_at)}</td>` +
    `<td>${esc(acc.name || "")}</td>` +
    `<td>${esc(pos.instrument || "")}${pos.name ? ` <span class="dim-note">${esc(pos.name)}</span>` : ""}</td>` +
    `<td class="${t.side === "sell" ? "down" : "up"}">${esc(t.side)}</td>` +
    `<td class="r">${fmtNum(t.quantity)}</td>` +
    `<td class="r">${fmtNum(t.price)} <span class="dim-note">${esc(pos.currency || "")}</span></td>` +
    `<td class="r">${Number(t.fees) ? fmtGBP(t.fees) : "—"}</td>` +
    `<td class="r">${value != null ? fmtGBP(value) : `<span class="dim-note">—</span>`}</td>` +
    `<td class="r"><button class="req-ic" data-del="${t.id}" title="Delete trade">✕</button></td>` +
    `</tr>`
  );
}

/* ---------- accounts ---------- */

function wireAccounts() {
  const addBtn = document.getElementById("acct-add");
  if (addBtn) addBtn.onclick = addAccount;
  root.querySelectorAll(".acct-del").forEach((b) => { b.onclick = () => delAccount(b.dataset.id); });
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
  if (!confirm(`Delete account "${acc?.name}" and ALL its positions and trades? This cannot be undone.`)) return;
  const { error } = await db.from("accounts").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}

/* ---------- trade form ---------- */

function wireTradeForm() {
  const acctSel = document.getElementById("tf-acct");
  if (!acctSel) return;
  acctSel.onchange = populatePositions;
  populatePositions();
  document.getElementById("tf-pos").onchange = toggleNewPosition;
  document.getElementById("tf-add").onclick = addTrade;
  const instr = document.getElementById("tf-instr");
  if (instr) instr.addEventListener("input", () => { document.getElementById("tf-ccy").value = guessCurrency(instr.value); });
}

function populatePositions() {
  const accountId = document.getElementById("tf-acct").value;
  const posSel = document.getElementById("tf-pos");
  const inAcct = positions.filter((p) => p.account_id === accountId);
  posSel.innerHTML =
    inAcct.map((p) => `<option value="${p.id}">${esc(p.instrument)}${p.name ? ` · ${esc(p.name)}` : ""}</option>`).join("") +
    `<option value="__new__">➕ New position…</option>`;
  toggleNewPosition();
}

function toggleNewPosition() {
  const isNew = document.getElementById("tf-pos").value === "__new__";
  root.querySelectorAll(".tf-new").forEach((el) => { el.hidden = !isNew; });
}

function tradeErr(msg) {
  const el = document.getElementById("tf-err");
  if (!el) return;
  el.textContent = msg || "";
  el.hidden = !msg;
}

async function addTrade() {
  tradeErr("");
  const accountId = document.getElementById("tf-acct").value;
  const posVal = document.getElementById("tf-pos").value;
  const side = document.getElementById("tf-side").value;
  const quantity = parseFloat(document.getElementById("tf-qty").value);
  const price = parseFloat(document.getElementById("tf-price").value);
  const fees = parseFloat(document.getElementById("tf-fees").value) || 0;
  const traded_at = document.getElementById("tf-date").value || todayISO();
  const note = document.getElementById("tf-note").value.trim() || null;

  if (!(quantity > 0)) return tradeErr("Enter a quantity.");
  if (!(price >= 0)) return tradeErr("Enter a price (GBP per share).");

  let position_id = posVal;
  if (posVal === "__new__") {
    const instrument = document.getElementById("tf-instr").value.trim().toUpperCase();
    const name = document.getElementById("tf-name").value.trim() || null;
    const currency = document.getElementById("tf-ccy").value || guessCurrency(instrument);
    if (!instrument) return tradeErr("Enter the instrument ticker for the new position.");
    const pr = await db.from("positions").insert({ account_id: accountId, instrument, name, currency }).select();
    if (pr.error) return tradeErr("Create position failed: " + pr.error.message);
    position_id = pr.data[0].id;
  }
  const tr = await db.from("trades").insert({ position_id, side, quantity, price, fees, traded_at, note }).select();
  if (tr.error) return tradeErr("Add trade failed: " + tr.error.message);
  loadAll();
}

/* ---------- trades table ---------- */

async function onTradeClick(e) {
  const id = e.target.dataset?.del;
  if (!id) return;
  const { error } = await db.from("trades").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}
