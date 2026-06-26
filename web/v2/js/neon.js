// Shared Neon client + auth gate for the cockpit's personal-data pages
// (Requests, Trades, Positions, Portfolio). One login covers them all — the
// session persists in localStorage, so signing in on any page signs you in
// everywhere. Security is Neon Auth (JWT) + Postgres Row-Level Security.

import { createClient } from "https://esm.sh/@neondatabase/neon-js";
import { AUTH_URL, DATA_API_URL } from "./neon-config.js";

export const db = createClient({ auth: { url: AUTH_URL }, dataApi: { url: DATA_API_URL } });

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const fmtGBP = (n) => {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return (v < 0 ? "−£" : "£") + Math.abs(v).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export const fmtNum = (n) => {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("en-GB", { maximumFractionDigits: 4 });
};

export const todayISO = () => {
  const d = new Date();
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

// Render a sign-in gate into `root`; resolves with the session once signed in.
export function requireAuth(root) {
  return new Promise((resolve) => {
    db.auth.getSession()
      .then(({ data }) => (data?.session ? resolve(data.session) : renderAuth()))
      .catch(() => renderAuth());

    function renderAuth(msg) {
      root.innerHTML =
        `<section class="auth-card">` +
        `<h1 class="auth-h">SIGN IN</h1>` +
        `<p class="auth-sub">Your trading book is private to you and syncs across your devices.</p>` +
        (msg ? `<div class="auth-err">${esc(msg)}</div>` : "") +
        `<input id="auth-email" class="req-in" type="email" placeholder="email" autocomplete="email">` +
        `<input id="auth-pass" class="req-in" type="password" placeholder="password" autocomplete="current-password">` +
        `<div class="auth-row"><button id="auth-signin" class="req-btn">Sign in</button>` +
        `<button id="auth-signup" class="req-btn ghost">Create account</button></div>` +
        `</section>`;
      document.getElementById("auth-signin").onclick = () => doAuth("in");
      document.getElementById("auth-signup").onclick = () => doAuth("up");
      document.getElementById("auth-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") doAuth("in"); });

      async function doAuth(kind) {
        const email = document.getElementById("auth-email").value.trim();
        const password = document.getElementById("auth-pass").value;
        if (!email || !password) return renderAuth("Enter an email and password.");
        try {
          const res = kind === "up"
            ? await db.auth.signUp.email({ email, password, name: email.split("@")[0] })
            : await db.auth.signIn.email({ email, password });
          if (res.error) return renderAuth(res.error.message);
          const { data } = await db.auth.getSession();
          if (data?.session) resolve(data.session);
          else renderAuth("Signed in, but no session started — try again.");
        } catch (err) { renderAuth(err.message || "Authentication failed."); }
      }
    }
  });
}

// "Signed in as … · Sign out" strip in the options bar.
export function mountAccountBar(optbar, session) {
  optbar.className = "optbar";
  optbar.innerHTML =
    `<div class="optbar-row"><label class="opt-field"><span class="opt-label">SIGNED IN</span>` +
    `<span class="req-user">${esc(session?.user?.email || "")}</span></label>` +
    `<button id="np-signout" class="opt-expand" type="button">Sign out</button></div>`;
  document.getElementById("np-signout").onclick = async () => {
    try { await db.auth.signOut(); } catch (_) { /* ignore */ }
    location.reload();
  };
}
