// Weekly review · step 1 — TAPE: what is the tide, and how much risk does it
// allow this week? Reads the build's TAPE read (tape.js `tapeRead`, published
// in scorecards.json) and draws it: the risk budget, index trends, breadth
// against its own history, and all eleven sectors ranked.

import "./nav.js";
import { loadScorecards, stepStrip, infoBar, esc, pct, trendChip, levelClass, failInto } from "./review.js";
import { BREADTH_FULL, BREADTH_DEFENSIVE } from "./tape.js";

const root = document.getElementById("tape-root");
infoBar("WEEKLY REVIEW", "decide on Friday's close · fill at Monday's open");

(async function boot() {
  let sc;
  try {
    sc = await loadScorecards();
  } catch (e) {
    return failInto(root, "the weekly scorecards", e);
  }
  document.getElementById("steps").innerHTML = stepStrip("tape", { week: sc.week });
  render(sc);
})();

function render(sc) {
  const t = sc.tape;
  if (!t?.available) {
    root.innerHTML = `<div class="rv-empty">No market feed this week — the budget falls back to HALF.</div>`;
    return;
  }
  const b = t.budget;
  const counts = { BUY: {}, WATCH: {} };
  for (const r of sc.rows) if (counts[r.status]) counts[r.status][r.setup] = (counts[r.status][r.setup] || 0) + 1;
  const nBuy = Object.values(counts.BUY).reduce((a, x) => a + x, 0);
  const nWatch = Object.values(counts.WATCH).reduce((a, x) => a + x, 0);

  root.innerHTML =
    `<div class="rv-page">` +
    `<div class="rv-banner ${levelClass(b.level)}">` +
    `<span class="rv-banner-lv">${b.level}</span>` +
    `<span class="rv-banner-kv">risk / new position <b>${b.riskPct}%</b></span>` +
    `<span class="rv-banner-kv">heat cap <b>${b.heatMax}%</b></span>` +
    `<span class="rv-banner-kv">new positions this week <b>≤ ${b.maxNew}</b></span>` +
    `<span class="rv-banner-why">${b.why.map(esc).join(" · ")}</span>` +
    `</div>` +
    `<div class="rv-grid2">` +
    indices(t) +
    breadth(sc) +
    `</div>` +
    sectors(t) +
    `<section class="rv-sec"><div class="rv-h"><span>This week's candidates</span>` +
    `<a class="rv-h-r" href="shortlist.html" style="color:var(--cyan)">→ shortlist</a></div>` +
    `<div class="rv-kv">` +
    `<dt>BUY</dt><dd>${nBuy ? Object.entries(counts.BUY).map(([k, n]) => `${n} ${k}`).join(" · ") : "none"}</dd>` +
    `<dt>WATCH</dt><dd>${nWatch ? Object.entries(counts.WATCH).map(([k, n]) => `${n} ${k}`).join(" · ") : "none"}</dd>` +
    `</div>` +
    `<p class="rv-note">The budget is set by the tape, not by how many candidates there are. A ${b.level} week takes at most ${b.maxNew} new ${b.maxNew === 1 ? "position" : "positions"}, however long the list.</p>` +
    `</section>` +
    `<p class="rv-note">Built ${esc(sc.built_at)} from prices through the week to ${esc(sc.week)}. ` +
    `Breadth is measured on today's S&P 500 constituents, so read it against its own history rather than as an absolute level. ` +
    `Evidence: <a href="reports.html?r=scorecard-weekly_strategy_backtest" style="color:var(--cyan)">the backtest</a>.</p>` +
    `</div>`;
}

function indices(t) {
  const rows = Object.entries(t.indices)
    .map(([sym, x]) => `<tr><td>${sym}</td><td>${trendChip(x.d)}</td><td>${trendChip(x.w)}</td></tr>`)
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Index trends</span><span class="rv-h-r">weekly is the one scored</span></div>` +
    `<table class="rv-tbl"><thead><tr><th>index</th><th>daily</th><th>weekly</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class="rv-kv" style="margin-top:8px"><dt>VIX</dt><dd>${t.vix == null ? "—" : t.vix.toFixed(1)}${t.vix > 30 ? ' <span class="down">spike — one budget level down</span>' : ""}</dd></div>` +
    `<p class="rv-note">BULL: price above a 21-week EMA above a 50-week SMA. BEAR: below the 50-week. NEUTRAL is anything in between.</p>` +
    `</section>`
  );
}

function breadth(sc) {
  const B = sc.breadth;
  const now = sc.tape.breadth;
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Breadth: stocks in Stage 2</span><span class="rv-h-r">${B.dates[0].slice(0, 4)}–now</span></div>` +
    `<div><span class="tp-big">${now ? now.stage2.toFixed(0) : "—"}%</span> ` +
    `<span class="dim-note">in Stage 2 · ${now ? now.above30.toFixed(0) : "—"}% above their 30-week</span></div>` +
    spark(B.dates, B.stage2) +
    `<p class="rv-note">FULL needs ${BREADTH_FULL}% (the long-run median) or more, and under ${BREADTH_DEFENSIVE}% (the bottom fifth) is DEFENSIVE. When the index trends up but few stocks do, the market is being carried by a handful of names, and a stock-picking book is fighting the tape.</p>` +
    `</section>`
  );
}

function spark(dates, vals) {
  const W = 600;
  const H = 120;
  const pad = { l: 26, r: 6, t: 6, b: 16 };
  const n = vals.length;
  const x = (i) => pad.l + (i / (n - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / 100) * (H - pad.t - pad.b);
  const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const years = [];
  let last = null;
  dates.forEach((d, i) => {
    const yr = d.slice(0, 4);
    if (yr !== last && Number(yr) % 5 === 0) years.push([i, yr]);
    last = yr;
  });
  const thr = (v, lbl) =>
    `<line class="tp-thr" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tp-thr-lbl" x="2" y="${y(v) + 3}">${lbl}</text>`;
  return (
    `<svg class="tp-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Share of stocks in Stage 2 over time">` +
    thr(BREADTH_FULL, BREADTH_FULL) +
    thr(BREADTH_DEFENSIVE, BREADTH_DEFENSIVE) +
    `<polyline class="tp-line" points="${pts}"/>` +
    `<circle class="tp-now" cx="${x(n - 1)}" cy="${y(vals[n - 1])}" r="3"/>` +
    years.map(([i, yr]) => `<text class="tp-axis" x="${x(i)}" y="${H - 3}" text-anchor="middle">${yr}</text>`).join("") +
    `</svg>`
  );
}

function sectors(t) {
  const maxAbs = Math.max(1, ...t.sectors.map((s) => Math.abs(s.ret13)));
  const rows = t.sectors
    .map((s) => {
      const w = Math.round((Math.abs(s.ret13) / maxAbs) * 80);
      const band = s.band === "top" ? "up" : s.band === "bottom" ? "down" : "";
      return (
        `<tr><td class="r">${s.rank13}</td><td>${esc(s.etf)}</td><td>${esc(s.name)}</td>` +
        `<td class="r ${s.ret13 >= 0 ? "up" : "down"}">${pct(s.ret13)}</td>` +
        `<td><span class="tp-bar ${s.ret13 < 0 ? "neg" : ""}" style="width:${w}px"></span></td>` +
        `<td class="r">${s.rank4 ?? "—"}</td><td class="r">${s.rank1 ?? "—"}</td>` +
        `<td class="${band}">${s.band === "top" ? "TAILWIND" : s.band === "bottom" ? "HEADWIND" : ""}</td></tr>`
      );
    })
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Sectors ranked by 13-week return</span><span class="rv-h-r">4w / 1w ranks show who is rolling over</span></div>` +
    `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th class="r">#</th><th>ETF</th><th>sector</th><th class="r">13w</th><th></th><th class="r">4w #</th><th class="r">1w #</th><th></th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>` +
    `<p class="rv-note">The top three sectors score the full 15 market points for a long, and the bottom three score none. The scorecard's MARKET &amp; SECTOR block uses these ranks.</p>` +
    `</section>`
  );
}
