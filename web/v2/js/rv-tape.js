// Weekly review · step 1 — MARKET (the "tape"): is this a good week to buy,
// and how much risk does it allow? Reads the build's TAPE read (tape.js `tapeRead`, published
// in scorecards.json) and draws it: the risk budget, index trends, breadth
// against its own history, and all eleven sectors ranked.

import "./nav.js";
import { loadScorecards, stepStrip, infoBar, esc, pct, trendChip, levelClass, failInto, SAY } from "./review.js";
import { BREADTH_FULL, BREADTH_DEFENSIVE } from "./tape.js";

const root = document.getElementById("tape-root");
infoBar("WEEKLY ROUTINE", "5 steps, about 20 minutes, once a week at the weekend. Place your orders for Monday's open.");

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
    root.innerHTML = `<div class="rv-empty">No market data this week, so we treat it as an amber week: buy less than usual.</div>`;
    return;
  }
  const b = t.budget;
  const counts = { BUY: 0, WATCH: 0 };
  for (const r of sc.rows) if (r.status in counts) counts[r.status]++;
  const nNew = `${b.maxNew} new ${b.maxNew === 1 ? "stock" : "stocks"}`;

  root.innerHTML =
    `<div class="rv-page">` +
    `<div class="rv-banner ${levelClass(b.level)}">` +
    `<span class="rv-banner-lv">${SAY.level[b.level]}</span>` +
    `<span class="rv-banner-kv"><b>${SAY.levelLong[b.level]}.</b></span>` +
    `<span class="rv-banner-why">Why: ${b.why.map(esc).join(", ")}.</span>` +
    `</div>` +
    `<section class="rv-sec"><div class="rv-h"><span>What this means for you this week</span></div>` +
    `<ul class="rv-list">` +
    `<li>Buy <b>at most ${nNew}</b> this week.</li>` +
    `<li>On each one, put no more than <b>${b.riskPct}%</b> of your account at risk. That's how much you'd lose if it fell to its stop-loss (the price where you sell to cut the loss). Step 5 works out the number of shares for you.</li>` +
    `<li>Across everything you own, keep the total at risk under <b>${b.heatMax}%</b> of your account.</li>` +
    `</ul>` +
    `<p class="rv-note">This week's scan found <b>${counts.BUY}</b> ${counts.BUY === 1 ? "stock" : "stocks"} worth buying and <b>${counts.WATCH}</b> close to it. ` +
    `<a href="shortlist.html" style="color:var(--cyan)">See them in step 2 →</a> ` +
    `${counts.BUY > b.maxNew ? `There are more ideas than you can take. Step 5 picks the best ${b.maxNew}.` : ""}</p>` +
    `</section>` +
    `<div class="rv-grid2">` +
    indices(t) +
    breadth(sc) +
    `</div>` +
    sectors(t) +
    `<p class="rv-note">Based on prices up to Friday ${esc(sc.week)} (updated ${esc(sc.built_at)}). ` +
    `Want the detail behind the rules? Read <a href="reports.html?r=scorecard-weekly_strategy_backtest" style="color:var(--cyan)">how this strategy has done in the past</a>.</p>` +
    `</div>`;
}

function indices(t) {
  const rows = Object.entries(t.indices)
    .map(([sym, x]) => `<tr><td>${esc(SAY.index[sym] || sym)} <span class="dim-note">${sym}</span></td><td>${trendChip(x.w)}</td><td>${trendChip(x.d)}</td></tr>`)
    .join("");
  const vix = t.vix == null ? "—" : t.vix.toFixed(0);
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Which way is the market heading?</span></div>` +
    `<table class="rv-tbl"><thead><tr><th>market</th><th>past months</th><th>past weeks</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class="rv-kv" style="margin-top:8px"><dt>fear gauge (VIX)</dt><dd>${vix} ` +
    (t.vix == null ? "" : t.vix > 30 ? '<span class="down">high: investors are nervous</span>' : t.vix > 20 ? '<span class="dim-note">a little nervous</span>' : '<span class="dim-note">calm</span>') +
    `</dd></div>` +
    `<p class="rv-note">It's easier to make money buying stocks when the whole market is going up. The "past months" column counts most.</p>` +
    `</section>`
  );
}

function breadth(sc) {
  const B = sc.breadth;
  const now = sc.tape.breadth;
  return (
    `<section class="rv-sec"><div class="rv-h"><span>How many stocks are rising?</span><span class="rv-h-r">${B.dates[0].slice(0, 4)} to now</span></div>` +
    `<div><span class="tp-big">${now ? now.stage2.toFixed(0) : "—"}%</span> ` +
    `<span class="dim-note">of S&amp;P 500 stocks are in a rising trend</span></div>` +
    spark(B.dates, B.stage2) +
    `<p class="rv-note">${BREADTH_FULL}% or more is healthy and needed for a green light. Under ${BREADTH_DEFENSIVE}% is weak (red light). ` +
    `If the index is up but only a few stocks are rising, a handful of giant companies are doing all the work, and picking winners is harder.</p>` +
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
    `<svg class="tp-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Share of stocks in a rising trend over time">` +
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
        `<tr><td class="r">${s.rank13}</td><td>${esc(s.name)} <span class="dim-note">${esc(s.etf)}</span></td>` +
        `<td class="r ${s.ret13 >= 0 ? "up" : "down"}">${pct(s.ret13)}</td>` +
        `<td><span class="tp-bar ${s.ret13 < 0 ? "neg" : ""}" style="width:${w}px"></span></td>` +
        `<td class="${band}">${s.band === "top" ? "STRONG" : s.band === "bottom" ? "WEAK" : ""}</td></tr>`
      );
    })
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Which industries are doing best?</span><span class="rv-h-r">price change, last 3 months</span></div>` +
    `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th class="r">#</th><th>industry</th><th class="r">3 months</th><th></th><th></th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>` +
    `<p class="rv-note">Stocks in the strongest industries get a better score in step 2, and stocks in the weakest get a worse one.</p>` +
    `</section>`
  );
}
