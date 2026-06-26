// Requests page — a personal wishlist tracker backed by Neon Postgres.
// Auth (email/password) + CRUD go through the Neon Data API (PostgREST) via the
// vanilla @neondatabase/neon-js client; Row-Level Security ties every row to the
// signed-in user, so it's safe on a public page and syncs across devices.

import "./nav.js";
import { createClient } from "https://esm.sh/@neondatabase/neon-js";
import { AUTH_URL, DATA_API_URL } from "./neon-config.js";

const client = createClient({ auth: { url: AUTH_URL }, dataApi: { url: DATA_API_URL } });

const root = document.getElementById("req-root");
const optbar = document.getElementById("optbar");
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let items = [];
let session = null;
let editingId = null;

/* ---------- boot ---------- */

(async function boot() {
  try {
    const { data } = await client.auth.getSession();
    session = data?.session || null;
  } catch (_) { session = null; }
  if (session) showApp();
  else showAuth();
})();

/* ---------- auth ---------- */

function showAuth(msg) {
  optbar.className = "";
  optbar.innerHTML = "";
  root.innerHTML = `
    <section class="auth-card">
      <h1 class="auth-h">SIGN IN</h1>
      <p class="auth-sub">Your wishlist is private to you and syncs across your devices.</p>
      ${msg ? `<div class="auth-err">${esc(msg)}</div>` : ""}
      <input id="auth-email" class="req-in" type="email" placeholder="email" autocomplete="email">
      <input id="auth-pass" class="req-in" type="password" placeholder="password" autocomplete="current-password">
      <div class="auth-row">
        <button id="auth-signin" class="req-btn">Sign in</button>
        <button id="auth-signup" class="req-btn ghost">Create account</button>
      </div>
    </section>`;
  document.getElementById("auth-signin").onclick = () => doAuth("in");
  document.getElementById("auth-signup").onclick = () => doAuth("up");
  document.getElementById("auth-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") doAuth("in"); });
}

async function doAuth(kind) {
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-pass").value;
  if (!email || !password) return showAuth("Enter an email and password.");
  try {
    const res = kind === "up"
      ? await client.auth.signUp.email({ email, password, name: email.split("@")[0] })
      : await client.auth.signIn.email({ email, password });
    if (res.error) return showAuth(res.error.message);
    const { data } = await client.auth.getSession();
    session = data?.session || null;
    if (session) showApp();
    else showAuth("Signed in, but no session started — try again.");
  } catch (err) {
    showAuth(err.message || "Authentication failed.");
  }
}

/* ---------- app ---------- */

function showApp() {
  optbar.className = "optbar";
  optbar.innerHTML =
    `<div class="optbar-row">` +
    `<label class="opt-field"><span class="opt-label">SIGNED IN</span><span class="req-user"></span></label>` +
    `<button id="req-signout" class="opt-expand" type="button">Sign out</button>` +
    `</div>`;
  optbar.querySelector(".req-user").textContent = session?.user?.email || "";
  document.getElementById("req-signout").onclick = async () => {
    try { await client.auth.signOut(); } catch (_) { /* ignore */ }
    session = null; items = []; editingId = null; showAuth();
  };
  load();
}

async function load() {
  root.innerHTML = `<div class="req-msg">Loading wishlist…</div>`;
  const { data, error } = await client.from("wishlist").select("*").order("created_at", { ascending: true });
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
  else if (act === "save") {
    save(id, li.querySelector(".edit-title").value.trim(), li.querySelector(".edit-note").value.trim());
  }
}

/* ---------- mutations ---------- */

async function addItem() {
  const inp = document.getElementById("req-new");
  const title = inp.value.trim();
  if (!title) return;
  inp.value = "";
  const { data, error } = await client.from("wishlist").insert({ title }).select();
  if (error) return load(); // re-sync on failure
  items.push(...(data || []));
  render();
}

async function toggle(id) {
  const it = items.find((x) => x.id === id);
  if (!it) return;
  const { error } = await client.from("wishlist").update({ done: !it.done, updated_at: new Date().toISOString() }).eq("id", id);
  if (error) return load();
  it.done = !it.done;
  render();
}

async function save(id, title, note) {
  if (!title) return; // title is required
  const { error } = await client.from("wishlist").update({ title, note: note || null, updated_at: new Date().toISOString() }).eq("id", id);
  editingId = null;
  if (error) return load();
  const it = items.find((x) => x.id === id);
  if (it) { it.title = title; it.note = note || null; }
  render();
}

async function del(id) {
  const { error } = await client.from("wishlist").delete().eq("id", id);
  if (error) return load();
  items = items.filter((x) => x.id !== id);
  render();
}
