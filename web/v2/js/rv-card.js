// Weekly review · step 3 — CARD: is this one a trade?
//
// The card is RECOMPUTED here, in the browser, by the same scorecard.js
// `scoreCard` over the same files the build read (the name's sim/<T>.json,
// sim-market.json, the earnings calendar, the fundamentals grades). For the
// live week it therefore matches the shortlist exactly; with ?d=<date> it
// replays any past week — what did the card say then, and what happened next?
//
//   card.html?t=AAPL             this week
//   card.html?t=AAPL&d=2024-03-08  the card as of that week
//
// Two things are only true of the live week and are left out of a replay:
// the universe prior the like-week block shrinks towards (it is published
// once, as of this week) and the fundamentals (a snapshot never grades a week
// before it was taken).

import "./nav.js";
import { createOptionsBar } from "./options-bar.js";
import {
  loadScorecards,
  loadMarketFeed,
  loadFundamentals,
  loadEarnings,
  loadUniverse,
  loadSeries,
  earningsFor,
  stepStrip,
  esc,
  pct,
  px,
  num,
  statusChip,
  failInto,
} from "./review.js";
import { eventTable, weekAsOf, runTrade } from "./strategy.js";
import { scoreCard, BLOCKS, BLOCK_LABELS, PROFILES } from "./scorecard.js";
import { QUALITY, VALUE } from "./fundamental-score.js";

const root = document.getElementById("card-root");
const params = new URLSearchParams(location.search);
let ticker = (params.get("t") || "").toUpperCase();
let asOfParam = params.get("d") || "";

const bar = createOptionsBar("optbar", {
  primary: [
    { type: "search", id: "cd-t", label: "TICKER", value: ticker, placeholder: "e.g. AAPL" },
    { type: "date", id: "cd-d", label: "AS OF", value: asOfParam },
  ],
  onChange: (id, v) => {
    if (id === "cd-t") ticker = String(v || "").trim().toUpperCase().split(/\s/)[0];
    if (id === "cd-d") asOfParam = v || "";
    const q = new URLSearchParams();
    if (ticker) q.set("t", ticker);
    if (asOfParam) q.set("d", asOfParam);
    history.replaceState(null, "", `?${q}`);
    show();
  },
});

(async function boot() {
  try {
    const [sc, un] = await Promise.all([loadScorecards(), loadUniverse()]);
    document.getElementById("steps").innerHTML = stepStrip("card", { week: sc.week });
    const dl = document.createElement("datalist");
    dl.id = "cd-list";
    dl.innerHTML = un.tickers.map((x) => `<option value="${esc(x.t)}">${esc(x.n)}</option>`).join("");
    document.body.appendChild(dl);
    bar.fields["cd-t"].setAttribute("list", "cd-list");
  } catch (e) {
    return failInto(root, "the weekly scorecards", e);
  }
  show();
})();

async function show() {
  const sc = await loadScorecards();
  if (!ticker) return pickOne(sc);
  root.innerHTML = `<div class="rv-empty">Scoring ${esc(ticker)}…</div>`;
  let series, market, fund, earnings;
  try {
    [series, market, fund, earnings] = await Promise.all([
      loadSeries(ticker, sc.data_as_of),
      loadMarketFeed(),
      loadFundamentals(),
      loadEarnings(),
    ]);
  } catch (e) {
    return failInto(root, `${ticker} (is it in the S&P 500 universe?)`, e);
  }
  const { s, name, sector } = series;
  const last = s.bars.length - 1;
  let w = asOfParam ? weekAsOf(s, asOfParam) : last;
  if (w < 60) {
    root.innerHTML = `<div class="rv-empty">Not enough history for ${esc(ticker)} as of ${esc(asOfParam)}.</div>`;
    return;
  }
  const live = w === last && s.bars[w].d === sc.week;
  const events = eventTable(s);
  const grade = fund?.grades?.[ticker];
  const ctxBase = {
    t: ticker,
    s,
    sector,
    market,
    events,
    priors: live ? sc.priors : null,
    earnings: earningsFor(earnings, ticker),
  };
  const fundamentals = grade && grade.quality != null ? { quality: grade.quality, value: grade.value, asOf: fund.as_of } : null;
  const card = scoreCard({ ...ctxBase, w, fundamentals });
  const history = [];
  for (let k = w - 1; k >= Math.max(60, w - 8); k--) history.push(scoreCard({ ...ctxBase, w: k, fundamentals: null }));
  render({ sc, s, w, live, card, name, sector, fund, grade, history, events });
}

function pickOne(sc) {
  const buys = sc.rows.filter((r) => r.status === "BUY").sort((a, b) => b.total - a.total);
  root.innerHTML =
    `<div class="rv-page"><div class="rv-empty">Pick a name above, or one of this week's BUYs:<br><br>` +
    (buys.length
      ? buys.map((r) => `<a href="card.html?t=${esc(r.t)}" style="color:var(--cyan);margin-right:14px">${esc(r.t)} <span class="dim-note">${esc(r.setup)} ${r.total.toFixed(0)}</span></a>`).join("")
      : "none this week — try the WATCH list on the shortlist.") +
    `</div></div>`;
}

function render({ sc, s, w, live, card, name, sector, fund, grade, history, events }) {
  const b = s.bars[w];
  const prof = card.setup ? PROFILES[card.setup] : null;
  const info = fund?.raw?.[ticker] || {};
  root.innerHTML =
    `<div class="rv-page">` +
    `<div class="cd-head"><span class="cd-tkr">${esc(ticker)}</span><span class="cd-name">${esc(name)}</span>` +
    `<span class="dim-note">${esc(sector || "")}${info.industry ? ` · ${esc(info.industry)}` : ""}</span>` +
    `<span class="dim-note">close ${px(b.c)} · week to ${esc(b.d)}${live ? "" : " · <b style=\"color:var(--gold)\">REPLAY</b>"}</span>` +
    `<span class="cd-score">${card.total == null ? "—" : card.total.toFixed(0)}<span class="dim-note" style="font-size:11px">/100</span></span></div>` +
    verdict(card) +
    chart(s, w, card) +
    `<div class="rv-grid2" style="margin-top:14px">` +
    `<section class="rv-sec"><div class="rv-h"><span>The blocks${card.setup ? ` · weighted for a ${card.setup}` : ""}</span><span class="rv-h-r">weight</span></div>` +
    blocks(card, prof) +
    `<p class="rv-note">Unavailable blocks leave the headline, which rescales over the rest. A missing feed never counts against a name. The weights are priors, not fitted (see the backtest).</p></section>` +
    `<div>` +
    plan(card) +
    likeWeek(card, s, events, w) +
    `</div></div>` +
    `<div class="rv-grid2">` +
    fundamentals(grade, info, fund, live) +
    historyTable(history, card) +
    `</div>` +
    (!live ? outcome(s, w, card) : "") +
    `<div class="cd-links">` +
    `<a href="simulator.html?t=${encodeURIComponent(ticker)}&d=${encodeURIComponent(b.d)}&tf=w">▶ practise this hand in the simulator (weekly)</a>` +
    `<a href="shortlist.html">← back to the shortlist</a>` +
    (live && card.status === "BUY" ? `<a href="orders.html">→ size it on ORDERS</a>` : "") +
    `</div>` +
    `</div>`;
}

function verdict(card) {
  const alts = (card.alternatives || []).map((a) => `${a.setup} ${a.status}${a.total != null ? ` ${a.total.toFixed(0)}` : ""}`);
  return (
    `<div class="cd-verdict">${statusChip(card.status)}` +
    (card.setup ? `<span class="rv-setup">${card.setup}</span>` : "") +
    `<span class="cd-why">${esc(card.why || "")}</span>` +
    (card.vetoes || []).map((v) => `<span class="cd-veto">✕ ${esc(v)}</span>`).join("") +
    (card.flags || []).map((f) => `<span class="cd-flag">⚑ ${esc(f)}</span>`).join("") +
    (alts.length ? `<span class="dim-note">also: ${esc(alts.join(" · "))}</span>` : "") +
    `</div>`
  );
}

function blocks(card, prof) {
  return BLOCKS.map((k) => {
    const bl = card.blocks?.[k];
    if (!bl) return "";
    const wt = prof ? prof.weights[k] : null;
    const na = !bl.available;
    const width = na ? 0 : Math.round(bl.score * 100);
    return (
      `<div class="cd-block${na ? " na" : ""}">` +
      `<span class="cd-bl">${BLOCK_LABELS[k]}</span>` +
      `<span class="rv-grade rv-g-${na ? "na" : bl.grade}">${na ? "·" : bl.grade}</span>` +
      `<span class="cd-bar"><i style="width:${width}%"></i></span>` +
      `<span class="cd-bx" title="${esc(bl.text)}">${esc(bl.text)}</span>` +
      `<span class="cd-bw">${wt == null ? "" : wt}</span>` +
      `</div>`
    );
  }).join("");
}

function plan(card) {
  const p = card.plan;
  if (!p) {
    return `<section class="rv-sec"><div class="rv-h"><span>Trade plan</span></div><div class="dim-note">No setup this week, so no trade. Stage ${card.stage ?? "—"} (${card.stageAge ?? 0} weeks).</div></section>`;
  }
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Trade plan</span><span class="rv-h-r">enter at Monday's open</span></div>` +
    `<dl class="rv-kv">` +
    `<dt>entry ≈</dt><dd>${px(p.entry)} <span class="dim-note">(Friday's close stands in for Monday's open)</span></dd>` +
    `<dt>stop</dt><dd class="down">${px(p.stop)} <span class="dim-note">−${num(p.riskPct, 1)}% · under the week's low, at least 1 ATR</span></dd>` +
    `<dt>risk / share</dt><dd>${px(p.risk)}</dd>` +
    `<dt>resistance</dt><dd>${p.blueSky ? `<span class="up">none within two years (blue sky)</span>` : `${px(p.resistance.price)} <span class="dim-note">×${p.resistance.touches} · +${num((p.resistance.price / p.entry - 1) * 100, 1)}%</span>`}</dd>` +
    `<dt>support</dt><dd>${p.support ? `${px(p.support.price)} <span class="dim-note">×${p.support.touches}</span>` : "—"}</dd>` +
    `<dt>R:R</dt><dd>${num(p.rr, 1)}${p.rr != null && p.rr < 1.5 ? ' <span class="down">under 1.5 — no room</span>' : ""}</dd>` +
    `</dl>` +
    `<p class="rv-note">Exits are fixed in advance. The stop rests all week. At +1R it moves to break-even, then trails 1 ATR under the 10-week. A weekly close under the 30-week ends the trade, and so does 26 weeks without one. Size comes from the stop, on ORDERS.</p>` +
    `</section>`
  );
}

function likeWeek(card, s, events, w) {
  const a = card.analogue;
  if (!card.setup) return "";
  const done = events.filter((e) => e.setup === card.setup && !e.trade.open && e.trade.exitIdx <= w);
  const rows = done
    .slice(-8)
    .reverse()
    .map((e) => {
      const r = e.trade.r;
      return `<tr><td>${esc(s.bars[e.w].d)}</td><td class="r ${r > 0 ? "up" : "down"}">${r >= 0 ? "+" : ""}${r.toFixed(2)}R</td><td>${esc(e.trade.reason)}</td><td class="r">${e.trade.weeks}w</td></tr>`;
    })
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Like-week · this strategy's ${card.setup} trades on ${esc(ticker)}</span></div>` +
    (a && a.n
      ? `<dl class="rv-kv"><dt>trades</dt><dd>${a.n} · ${num(a.win * 100, 0)}% won</dd>` +
        `<dt>mean / median</dt><dd>${a.meanR >= 0 ? "+" : ""}${num(a.meanR)}R / ${a.medianR >= 0 ? "+" : ""}${num(a.medianR)}R</dd>` +
        `<dt>worst</dt><dd class="down">${num(a.worstR)}R</dd>` +
        `<dt>13w vs drift</dt><dd>${a.edge == null ? "—" : pct(a.edge * 100)}</dd>` +
        (a.prior != null ? `<dt>universe</dt><dd>${a.prior >= 0 ? "+" : ""}${num(a.prior)}R per ${card.setup}</dd>` : "") +
        `</dl>` +
        `<div class="rv-tbl-wrap" style="margin-top:6px"><table class="rv-tbl"><thead><tr><th>decided</th><th class="r">R</th><th>exit</th><th class="r">held</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="dim-note">No completed ${card.setup} trades on this name before this week.</div>`) +
    `<p class="rv-note">Only trades that had already exited count, because those are the outcomes you could have known. Samples on one name are small, so the block scores this name against the universe's expectancy, shrunk by sample size.</p>` +
    `</section>`
  );
}

function fundamentals(grade, info, fund, live) {
  if (!grade || grade.quality == null) {
    return `<section class="rv-sec"><div class="rv-h"><span>Fundamentals</span></div><div class="dim-note">No graded snapshot for this name.</div></section>`;
  }
  const row = (m) => {
    const p = grade.detail?.[m.key];
    return p == null ? "" : `<tr><td>${esc(m.label)}</td><td class="r">${p}</td><td><span class="tp-bar" style="width:${Math.round(p * 0.6)}px"></span></td></tr>`;
  };
  const raw = [
    ["fwd P/E", info.forwardPE],
    ["EV/EBITDA", info.enterpriseToEbitda],
    ["rev growth", info.revenueGrowth != null ? `${(info.revenueGrowth * 100).toFixed(1)}%` : null],
    ["op margin", info.operatingMargins != null ? `${(info.operatingMargins * 100).toFixed(1)}%` : null],
    ["debt/equity", info.debtToEquity],
  ].filter(([, v]) => v != null);
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Fundamentals · sector percentiles</span><span class="rv-h-r">snapshot ${esc(fund.as_of)}${live ? "" : " (not used in a replay)"}</span></div>` +
    `<dl class="rv-kv"><dt>quality</dt><dd><b>${grade.quality}</b>th pct</dd><dt>value</dt><dd><b>${grade.value ?? "—"}</b>th pct</dd></dl>` +
    `<div class="rv-tbl-wrap" style="margin-top:6px"><table class="rv-tbl"><tbody>${[...QUALITY, ...VALUE].map(row).join("")}</tbody></table></div>` +
    (raw.length ? `<p class="rv-note">${raw.map(([k, v]) => `${k} ${esc(typeof v === "number" ? v.toFixed(1) : v)}`).join(" · ")}</p>` : "") +
    `</section>`
  );
}

function historyTable(history, card) {
  const rows = [card, ...history]
    .map(
      (c) =>
        `<tr><td>${esc(c.date)}</td><td>${statusChip(c.status)}</td><td class="rv-setup">${esc(c.setup || "")}</td>` +
        `<td class="r">${c.total == null ? "—" : c.total.toFixed(0)}</td><td class="r">${c.stage ?? "—"}</td></tr>`
    )
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>The last weeks on ${esc(ticker)}</span><span class="rv-h-r">WATCH turning BUY is the routine working</span></div>` +
    `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th>week</th><th>status</th><th>setup</th><th class="r">score</th><th class="r">stage</th></tr></thead><tbody>${rows}</tbody></table></div>` +
    `</section>`
  );
}

/** A replay can show what happened next — under the strategy's own exits. */
function outcome(s, w, card) {
  if (card.status !== "BUY" && card.status !== "WATCH") return "";
  const t = runTrade(s, w);
  if (!t) return `<section class="rv-sec"><div class="rv-h"><span>What happened next</span></div><div class="dim-note">Monday opened through the stop, so the order would have been cancelled.</div></section>`;
  return (
    `<section class="rv-sec"><div class="rv-h"><span>What happened next · had it been bought</span></div>` +
    `<div>${t.open ? "still running" : `${esc(t.reason)} exit ${esc(s.bars[t.exitIdx].d)}`} after ${t.weeks} weeks: ` +
    `<b class="${t.r > 0 ? "up" : "down"}">${t.r >= 0 ? "+" : ""}${t.r.toFixed(2)}R</b> (${pct(t.pct)})</div>` +
    `</section>`
  );
}

/* ---------- the weekly chart ---------- */

function chart(s, w, card) {
  const LOOK = 78; // a year and a half of weeks
  const AFTER = w < s.bars.length - 1 ? Math.min(13, s.bars.length - 1 - w) : 0;
  const from = Math.max(0, w - LOOK + 1);
  const to = w + AFTER;
  const bars = s.bars.slice(from, to + 1);
  const W = 900;
  const H = 300;
  const pad = { l: 6, r: 58, t: 10, b: 18 };
  const p = card.plan;
  const levels = [];
  if (p) {
    levels.push({ v: p.stop, cls: "stop", lbl: `STOP ${px(p.stop)}` });
    if (p.resistance) levels.push({ v: p.resistance.price, cls: "res", lbl: `RES ${px(p.resistance.price)}` });
    if (p.support) levels.push({ v: p.support.price, cls: "sup", lbl: `SUP ${px(p.support.price)}` });
  }
  let lo = Infinity;
  let hi = -Infinity;
  for (const b of bars) {
    lo = Math.min(lo, b.l);
    hi = Math.max(hi, b.h);
  }
  for (const L of levels) {
    lo = Math.min(lo, L.v);
    hi = Math.max(hi, L.v);
  }
  // A log axis when the window spans more than a 2.5x move: a stock that ran
  // tenfold would otherwise flatten its first year into a line along the
  // floor. Equal distances are then equal percentage moves.
  const logScale = lo > 0 && hi / lo > 2.5;
  const f = logScale ? Math.log : (v) => v;
  const inv = logScale ? Math.exp : (v) => v;
  let fl = f(lo);
  let fh = f(hi);
  const span = fh - fl || 1;
  fl -= span * 0.04;
  fh += span * 0.04;
  const n = bars.length;
  const cw = (W - pad.l - pad.r) / n;
  const x = (i) => pad.l + (i + 0.5) * cw;
  const y = (v) => pad.t + ((fh - f(v)) / (fh - fl)) * (H - pad.t - pad.b);
  let g = "";
  for (let k = 0; k <= 4; k++) {
    const v = inv(fl + ((fh - fl) * k) / 4);
    g += `<line class="cd-grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="cd-axis" x="${W - pad.r + 4}" y="${y(v) + 3}">${px(v)}</text>`;
  }
  let candles = "";
  bars.forEach((b, i) => {
    const up = b.c >= b.o;
    const cls = up ? "cd-up" : "cd-dn";
    const bw = Math.max(1, cw * 0.62);
    const top = y(Math.max(b.o, b.c));
    const bh = Math.max(1, Math.abs(y(b.o) - y(b.c)));
    candles +=
      `<line class="cd-wick ${cls}" x1="${x(i)}" x2="${x(i)}" y1="${y(b.h)}" y2="${y(b.l)}"/>` +
      `<rect class="${cls}" x="${x(i) - bw / 2}" y="${top}" width="${bw}" height="${bh}"${after(from + i, w) ? ' opacity="0.35"' : ""}/>`;
  });
  const line = (arr, cls) => {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const v = arr[from + i];
      if (v != null) pts.push(`${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    }
    return pts.length ? `<polyline class="${cls}" points="${pts.join(" ")}"/>` : "";
  };
  const decX = x(w - from) + cw / 2;
  const lv = levels
    .map(
      (L) =>
        `<line class="cd-${L.cls}" x1="${pad.l}" x2="${W - pad.r}" y1="${y(L.v)}" y2="${y(L.v)}"/>` +
        `<text class="cd-lbl cd-lbl-${L.cls}" x="${W - pad.r - 4}" y="${y(L.v) - 3}" text-anchor="end">${L.lbl}</text>`
    )
    .join("");
  const years = [];
  let lastY = null;
  bars.forEach((b, i) => {
    const m = b.d.slice(0, 7);
    if (m.slice(5) === "01" && m.slice(0, 4) !== lastY) {
      years.push(`<text class="cd-axis" x="${x(i)}" y="${H - 4}" text-anchor="middle">${m.slice(0, 4)}</text>`);
      lastY = m.slice(0, 4);
    }
  });
  return (
    `<svg class="cd-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Weekly chart of ${esc(ticker)}">` +
    g +
    line(s.sma30, "cd-ma30") +
    line(s.sma10, "cd-ma10") +
    candles +
    lv +
    (AFTER ? `<line class="cd-dec" x1="${decX}" x2="${decX}" y1="${pad.t}" y2="${H - pad.b}"/>` : "") +
    years.join("") +
    `</svg>` +
    `<div class="cd-legend"><span><i style="border-color:var(--cyan)"></i>10-week</span><span><i style="border-color:var(--gold)"></i>30-week</span>` +
    (p ? `<span><i style="border-color:var(--loss);border-top-style:dashed"></i>stop</span>` : "") +
    (AFTER ? `<span>faded: the weeks after the decision</span>` : "") +
    `<span>weekly bars, ${n} weeks${logScale ? " · log scale" : ""}</span></div>`
  );
}

const after = (i, w) => i > w;
