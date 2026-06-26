// Requests page — a personal wishlist tracker backed by Neon Postgres.
// Auth + CRUD via the shared neon.js client; Row-Level Security ties every row
// to the signed-in user.

import "./nav.js";
import { db, esc, requireAuth, mountAccountBar } from "./neon.js";

const root = document.getElementById("req-root");
const optbar = document.getElementById("optbar");

let items = [];
let editingId = null;

(async function boot() {
  const session = await requireAuth(root);
  mountAccountBar(optbar, session);
  load();
})();

async function load() {
  root.innerHTML = `<div class="req-msg">Loading wishlist…</div>`;
  const { data, error } = await db.from("wishlist").select("*").order("created_at", { ascending: true });
  if (error) { root.innerHTML = `<div class="req-msg">Could not load wishlist (${esc(error.message)})</div>`; return; }
  items = data || [];
  render();
}

function render() {
  root.innerHTML =
    `<section class="req-add">` +
    `<input id="req-new" class="req-in" type="text" placeholder="Add a wishlist item…" autocomplete="off">` +
    `<button id="req-add-btn" class="req-btn">Add</button>` +
    `</section>` +
    `<ul class="req-list">${items.map(rowHtml).join("") || `<li class="req-empty">Nothing yet — add your first item above.</li>`}</ul>`;

  const newInput = document.getElementById("req-new");
  document.getElementById("req-add-btn").onclick = addItem;
  newInput.addEventListener("keydown", (e) => { if (e.key === "Enter") addItem(); });
  if (editingId === null) newInput.focus();
  root.querySelector(".req-list").addEventListener("click", onListClick);
}

function rowHtml(it) {
  if (it.id === editingId) {
    return (
      `<li class="req-item editing" data-id="${it.id}">` +
      `<div class="req-body">` +
      `<input class="req-in edit-title" value="${esc(it.title)}">` +
      `<input class="req-in edit-note" placeholder="note (optional)" value="${esc(it.note)}">` +
      `</div>` +
      `<button class="req-ic save" data-act="save" title="Save">Save</button>` +
      `<button class="req-ic" data-act="cancel" title="Cancel">Cancel</button>` +
      `</li>`
    );
  }
  return (
    `<li class="req-item${it.done ? " done" : ""}" data-id="${it.id}">` +
    `<button class="req-check" data-act="toggle" title="Toggle done">${it.done ? "✓" : ""}</button>` +
    `<div class="req-body">` +
    `<div class="req-title">${esc(it.title)}</div>` +
    (it.note ? `<div class="req-note">${esc(it.note)}</div>` : "") +
    `</div>` +
    `<button class="req-ic" data-act="edit" title="Edit">✎</button>` +
    `<button class="req-ic" data-act="del" title="Remove">✕</button>` +
    `</li>`
  );
}

function onListClick(e) {
  const li = e.target.closest(".req-item");
  if (!li) return;
  const id = li.dataset.id;
  const act = e.target.dataset.act;
  if (act === "toggle") toggle(id);
  else if (act === "del") del(id);
  else if (act === "edit") { editingId = id; render(); }
  else if (act === "cancel") { editingId = null; render(); }
  else if (act === "save") save(id, li.querySelector(".edit-title").value.trim(), li.querySelector(".edit-note").value.trim());
}

async function addItem() {
  const inp = document.getElementById("req-new");
  const title = inp.value.trim();
  if (!title) return;
  inp.value = "";
  const { data, error } = await db.from("wishlist").insert({ title }).select();
  if (error) return load();
  items.push(...(data || []));
  render();
}

async function toggle(id) {
  const it = items.find((x) => x.id === id);
  if (!it) return;
  const { error } = await db.from("wishlist").update({ done: !it.done, updated_at: new Date().toISOString() }).eq("id", id);
  if (error) return load();
  it.done = !it.done;
  render();
}

async function save(id, title, note) {
  if (!title) return;
  const { error } = await db.from("wishlist").update({ title, note: note || null, updated_at: new Date().toISOString() }).eq("id", id);
  editingId = null;
  if (error) return load();
  const it = items.find((x) => x.id === id);
  if (it) { it.title = title; it.note = note || null; }
  render();
}

async function del(id) {
  const { error } = await db.from("wishlist").delete().eq("id", id);
  if (error) return load();
  items = items.filter((x) => x.id !== id);
  render();
}
