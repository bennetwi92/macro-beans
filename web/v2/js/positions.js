// Positions page — average-cost PnL per position, with multi-leg grouping that
// shows the per-leg breakdown. Single-instrument positions are the atomic unit;
// a group rolls several of them up. Marks are manual for now (editable per
// position); currency-aware auto-marks from the cockpit prices come next.
// Everything GBP.

import "./nav.js";
import { db, esc, fmtGBP, fmtNum, requireAuth, mountAccountBar } from "./neon.js";
import { gbpPositionMetrics } from "./book.js";
import { loadPrices } from "./prices.js";

const root = document.getElementById("pos-root");
const optbar = document.getElementById("optbar");

let accounts = [], groups = [], positions = [], trades = [];

(async function boot() {
  const session = await requireAuth(root);
  mountAccountBar(optbar, session);
  await loadPrices();
  loadAll();
})();

async function loadAll() {
  root.innerHTML = `<div class="req-msg">Loading positions…</div>`;
  const [a, g, p, t] = await Promise.all([
    db.from("accounts").select("*").order("name"),
    db.from("position_groups").select("*").order("created_at"),
    db.from("positions").select("*").order("created_at"),
    db.from("trades").select("*"),
  ]);
  if (a.error) { root.innerHTML = `<div class="req-msg">Could not load (${esc(a.error.message)})</div>`; return; }
  accounts = a.data || []; groups = g.data || []; positions = p.data || []; trades = t.data || [];
  positions.forEach((pos) => { pos._m = computePosition(pos); });
  render();
}

/* ---------- accounting (shared) ---------- */

const computePosition = (pos) => gbpPositionMetrics(pos, trades.filter((t) => t.position_id === pos.id));

function rollup(metrics) {
  let realized = 0, unreal = 0, mktVal = 0, cost = 0, open = false, hasMark = true;
  for (const m of metrics) {
    realized += m.realized;
    if (m.open) {
      open = true; cost += m.costBasis;
      if (m.mark != null) { mktVal += m.mktVal; unreal += m.unreal; } else hasMark = false;
    }
  }
  return { realized, unreal: hasMark ? unreal : null, mktVal: hasMark ? mktVal : null, cost, open, total: realized + (hasMark ? unreal : 0) };
}

/* ---------- render ---------- */

const pnl = (v) => (v == null ? `<span class="dim-note">—</span>` : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${fmtGBP(v)}</span>`);
const pnlTd = (v) => (v == null ? `<td class="r dim-note">—</td>` : `<td class="r ${v > 0 ? "up" : v < 0 ? "down" : ""}">${fmtGBP(v)}</td>`);
const totLabel = (r) => `Total ${pnl(r.total)} · Real ${pnl(r.realized)}${r.unreal != null ? ` · Unreal ${pnl(r.unreal)}` : ""}`;

function render() {
  if (!accounts.length) {
    root.innerHTML = `<div class="np-wrap"><div class="req-msg">No accounts yet — add one and log trades on the <a href="trades.html">Trades</a> page.</div></div>`;
    return;
  }
  root.innerHTML =
    `<div class="np-wrap">` +
    `<div class="dim-note pos-hint">Marks are entered manually (GBP per share). Auto-pricing from the cockpit is coming next.</div>` +
    accounts.map(accountBlock).join("") +
    `</div>`;
  wire();
}

function accountBlock(acc) {
  const accPos = positions.filter((p) => p.account_id === acc.id);
  const accGroups = groups.filter((g) => g.account_id === acc.id);
  const accRoll = rollup(accPos.map((p) => p._m));

  let html = `<section class="np-sec"><div class="pos-acct-h"><div class="np-h">${esc(acc.name)}${acc.type ? ` · ${esc(acc.type)}` : ""}</div><div class="pos-acct-tot">${totLabel(accRoll)}</div></div>`;

  for (const g of accGroups) {
    const legs = accPos.filter((p) => p.group_id === g.id);
    const gr = rollup(legs.map((p) => p._m));
    html +=
      `<div class="grp-card"><div class="grp-h">` +
      `<span class="grp-name">▣ ${esc(g.name)}</span>` +
      (g.thesis ? `<span class="dim-note">${esc(g.thesis)}</span>` : "") +
      `<span class="grp-tot">${totLabel(gr)}</span>` +
      `<button class="req-ic" data-delgrp="${g.id}" title="Delete group (its positions become standalone)">✕</button>` +
      `</div>` +
      (legs.length ? tableHtml(legs, acc.id) : `<div class="dim-note grp-empty">No positions yet — assign with the Group dropdown.</div>`) +
      `</div>`;
  }

  const standalone = accPos.filter((p) => !p.group_id);
  html += standalone.length ? tableHtml(standalone, acc.id) : (accGroups.length ? "" : `<div class="dim-note grp-empty">No positions yet — log a trade on the Trades page.</div>`);

  html += `<div class="grp-new"><input class="req-in grp-new-name" data-acct="${acc.id}" placeholder="New group name (e.g. Oil pair)"><button class="req-btn ghost" data-newgrp="${acc.id}">Add group</button></div>`;
  return html + `</section>`;
}

function tableHtml(posList, accountId) {
  const accGroups = groups.filter((g) => g.account_id === accountId);
  return (
    `<div class="logwrap"><table class="np-tbl pos-tbl">` +
    `<thead><tr><th>Instrument</th><th class="r">Qty</th><th class="r">Avg</th><th class="r">Mark</th><th class="r">Mkt Val</th><th class="r">Unreal</th><th class="r">Real</th><th class="r">Total</th><th>Status</th><th>Group</th><th></th></tr></thead><tbody>` +
    posList.map((p) => rowHtml(p, accGroups)).join("") +
    `</tbody></table></div>`
  );
}

function rowHtml(pos, accGroups) {
  const m = pos._m;
  const markCell = m.open
    ? `<td class="r mark-cell"><input class="mark-in" type="number" step="any" data-id="${pos.id}" value="${m.manualMark ?? ""}" placeholder="${m.markGBP != null ? m.markGBP.toFixed(4) : "£"}">${m.markAuto ? `<span class="mk-auto" title="auto from latest cockpit close">auto</span>` : ""}</td>`
    : `<td class="r dim-note">—</td>`;
  const grpOpts = `<option value="">— none —</option>` + accGroups.map((g) => `<option value="${g.id}"${pos.group_id === g.id ? " selected" : ""}>${esc(g.name)}</option>`).join("");
  return (
    `<tr>` +
    `<td>${esc(pos.instrument)} <span class="dim-note">${m.cur}</span>${pos.name ? ` <span class="dim-note">${esc(pos.name)}</span>` : ""}</td>` +
    `<td class="r">${m.open ? fmtNum(m.qty) : `<span class="dim-note">—</span>`}</td>` +
    `<td class="r">${m.open ? fmtGBP(m.avg) : `<span class="dim-note">—</span>`}</td>` +
    markCell +
    `<td class="r">${m.mktVal != null ? fmtGBP(m.mktVal) : `<span class="dim-note">—</span>`}</td>` +
    pnlTd(m.open ? m.unreal : null) +
    pnlTd(m.realized) +
    pnlTd(m.total) +
    `<td><span class="badge ${m.open ? "open" : "closed"}">${m.open ? "open" : "closed"}</span></td>` +
    `<td><select class="grp-sel" data-id="${pos.id}">${grpOpts}</select></td>` +
    `<td class="r"><button class="req-ic" data-delpos="${pos.id}" title="Delete position + its trades">✕</button></td>` +
    `</tr>`
  );
}

/* ---------- wiring ---------- */

function wire() {
  root.addEventListener("change", onChange);
  root.addEventListener("click", onClick);
}

function onChange(e) {
  const t = e.target;
  if (t.classList.contains("mark-in")) saveMark(t.dataset.id, t.value);
  else if (t.classList.contains("grp-sel")) saveGroup(t.dataset.id, t.value || null);
}

function onClick(e) {
  const t = e.target;
  if (t.dataset.delpos) delPosition(t.dataset.delpos);
  else if (t.dataset.delgrp) delGroup(t.dataset.delgrp);
  else if (t.dataset.newgrp) addGroup(t.dataset.newgrp);
}

async function saveMark(id, val) {
  const mark = val === "" ? null : Number(val);
  const { error } = await db.from("positions").update({ mark, mark_source: "manual", mark_at: new Date().toISOString() }).eq("id", id);
  if (error) return loadAll();
  const pos = positions.find((p) => p.id === id);
  if (pos) { pos.mark = mark; pos._m = computePosition(pos); }
  render();
}

async function saveGroup(id, groupId) {
  const { error } = await db.from("positions").update({ group_id: groupId }).eq("id", id);
  if (error) return loadAll();
  const pos = positions.find((p) => p.id === id);
  if (pos) pos.group_id = groupId;
  render();
}

async function addGroup(accountId) {
  const input = root.querySelector(`.grp-new-name[data-acct="${accountId}"]`);
  const name = input?.value.trim();
  if (!name) return;
  const { error } = await db.from("position_groups").insert({ account_id: accountId, name }).select();
  if (error) return alert("Add group failed: " + error.message);
  loadAll();
}

async function delGroup(id) {
  if (!confirm("Delete this group? Its positions become standalone (trades are kept).")) return;
  const { error } = await db.from("position_groups").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}

async function delPosition(id) {
  const pos = positions.find((p) => p.id === id);
  if (!confirm(`Delete position "${pos?.instrument}" and ALL its trades? This cannot be undone.`)) return;
  const { error } = await db.from("positions").delete().eq("id", id);
  if (error) return alert("Delete failed: " + error.message);
  loadAll();
}
