// Weekly review · step 3 — CARD (shown as CHECK): should I buy this one?
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
  SAY,
  setupName,
  xRisk,
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
    { type: "search", id: "cd-t", label: "STOCK", value: ticker, placeholder: "e.g. AAPL" },
    { type: "date", id: "cd-d", label: "LOOK BACK TO", value: asOfParam },
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
  root.innerHTML = `<div class="rv-empty">Checking ${esc(ticker)}…</div>`;
  let series, market, fund, earnings;
  try {
    [series, market, fund, earnings] = await Promise.all([
      loadSeries(ticker, sc.data_as_of),
      loadMarketFeed(),
      loadFundamentals(),
      loadEarnings(),
    ]);
  } catch (e) {
    return failInto(root, `${ticker}. We only cover S&P 500 stocks: is the ticker right?`, e);
  }
  const { s, name, sector } = series;
  const last = s.bars.length - 1;
  let w = asOfParam ? weekAsOf(s, asOfParam) : last;
  if (w < 60) {
    root.innerHTML = `<div class="rv-empty">Not enough price history for ${esc(ticker)} before ${esc(asOfParam)}.</div>`;
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
    `<div class="rv-page"><div class="rv-empty">Type a stock's ticker above (for example AAPL for Apple), or pick one of this week's buys:<br><br>` +
    (buys.length
      ? buys.map((r) => `<a href="card.html?t=${esc(r.t)}" style="color:var(--cyan);margin-right:14px">${esc(r.t)} <span class="dim-note">${esc(setupName(r.setup))} · score ${r.total.toFixed(0)}</span></a>`).join("")
      : `nothing is a buy this week. The <a href="shortlist.html" style="color:var(--cyan)">Ideas</a> page shows the ones that are close.`) +
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
    `<span class="dim-note">price ${px(b.c)} at the close on ${esc(b.d)}${live ? "" : ` · <b style="color:var(--gold)">LOOKING BACK: this is how it stood that week</b>`}</span>` +
    `<span class="cd-score" title="How well it scores across the checks below, out of 100">${card.total == null ? "—" : card.total.toFixed(0)}<span class="dim-note" style="font-size:11px">/100</span></span></div>` +
    verdict(card) +
    chart(s, w, card) +
    `<div class="rv-grid2" style="margin-top:14px">` +
    `<div>` +
    plan(card) +
    likeWeek(card, s, events, w) +
    `</div>` +
    `<section class="rv-sec"><div class="rv-h"><span>How the score is made</span><span class="rv-h-r">points</span></div>` +
    blocks(card, prof) +
    `<p class="rv-note">Each check gets a grade from A (good) to F (poor). "Points" is how much each check counts for this type of buy. A check with no data (·) is left out rather than counted against the stock.</p></section>` +
    `</div>` +
    `<div class="rv-grid2">` +
    fundamentals(grade, info, fund, live) +
    historyTable(history, card) +
    `</div>` +
    (!live ? outcome(s, w, card) : "") +
    `<div class="cd-links">` +
    `<a href="simulator.html?t=${encodeURIComponent(ticker)}&d=${encodeURIComponent(b.d)}&tf=w">▶ practise this chart in the simulator</a>` +
    `<a href="shortlist.html">← back to Ideas</a>` +
    (live && card.status === "BUY" ? `<a href="orders.html">→ see how many shares to buy (To do)</a>` : "") +
    `</div>` +
    `</div>`;
}

function verdict(card) {
  const alts = (card.alternatives || []).map((a) => `${setupName(a.setup)}: ${SAY.status[a.status] ?? a.status}`);
  return (
    `<div class="cd-verdict">${statusChip(card.status)}` +
    `<b>${card.status ? SAY.statusLong[card.status] : "No buy signal this week"}</b>` +
    (card.setup ? `<span class="rv-setup" title="${esc(SAY.setupLong[card.setup])}">${setupName(card.setup)}</span><span class="dim-note">${esc(SAY.setupLong[card.setup])}</span>` : "") +
    `</div>` +
    `<div class="cd-verdict" style="margin-top:-8px">` +
    (card.status === "PASS" && card.vetoes?.length
      ? `<span class="cd-why">It looks promising (${esc(card.why || "")}), but:</span>`
      : `<span class="cd-why">Why: ${esc(card.why || "")}</span>`) +
    (card.vetoes || []).map((v) => `<span class="cd-veto">✕ ${esc(v)}</span>`).join("") +
    (card.flags || []).map((f) => `<span class="cd-flag">⚑ ${esc(f)}</span>`).join("") +
    (alts.length ? `<span class="dim-note">also looks like: ${esc(alts.join(" · "))}</span>` : "") +
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
      `<span class="cd-bx">${esc(bl.text)}</span>` +
      `<span class="cd-bw">${wt == null ? "" : wt}</span>` +
      `</div>`
    );
  }).join("");
}

function plan(card) {
  const p = card.plan;
  if (!p) {
    const st = card.stage ? ` Its price trend is ${SAY.stage[card.stage]}.` : "";
    return `<section class="rv-sec"><div class="rv-h"><span>If you buy</span></div><div class="dim-note">Nothing to buy this week: the price chart doesn't show one of the three buying patterns.${st}</div></section>`;
  }
  const upside = p.blueSky ? null : (p.resistance.price / p.entry - 1) * 100;
  return (
    `<section class="rv-sec"><div class="rv-h"><span>If you buy</span><span class="rv-h-r">order for Monday's open</span></div>` +
    `<dl class="rv-kv">` +
    `<dt>buy at about</dt><dd>${px(p.entry)} <span class="dim-note">(Friday's closing price)</span></dd>` +
    `<dt>stop-loss</dt><dd class="down">${px(p.stop)} <span class="dim-note">sell automatically if it falls here: −${num(p.riskPct, 1)}%</span></dd>` +
    `<dt>could rise to</dt><dd>${p.blueSky ? `<span class="up">no past high in the way: the price is in clear air</span>` : `${px(p.resistance.price)} <span class="dim-note">+${num(upside, 1)}%, a price it stalled at ${p.resistance.touches} times before</span>`}</dd>` +
    `<dt>upside vs downside</dt><dd>${p.rr == null ? "—" : `could gain ${num(p.rr, 1)}× what it risks`}${p.rr != null && p.rr < 1.5 ? ' <span class="down">(under 1.5×: not enough room)</span>' : ""}</dd>` +
    `</dl>` +
    `<p class="rv-note">Set the stop-loss when you buy and leave it. The plan for selling is fixed in advance: once the stock is up by as much as you risked, the stop-loss moves up to your buy price so you can't lose, then keeps rising behind the price. You also sell if it closes a week below its 30-week average (the gold line), or after 26 weeks. The To do page works out how many shares.</p>` +
    `</section>`
  );
}

function likeWeek(card, s, events, w) {
  const a = card.analogue;
  if (!card.setup) return "";
  const kind = setupName(card.setup);
  const done = events.filter((e) => e.setup === card.setup && !e.trade.open && e.trade.exitIdx <= w);
  const rows = done
    .slice(-8)
    .reverse()
    .map((e) => {
      const r = e.trade.r;
      return `<tr><td>${esc(s.bars[e.w].d)}</td><td class="r ${r > 0 ? "up" : "down"}">${xRisk(r)}</td><td>${esc(SAY.exit[e.trade.reason] ?? e.trade.reason)}</td><td class="r">${e.trade.weeks} wk</td></tr>`;
    })
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>Track record: past ${esc(kind)} buys on ${esc(ticker)}</span></div>` +
    (a && a.n
      ? `<dl class="rv-kv"><dt>past trades</dt><dd>${a.n} · ${num(a.win * 100, 0)}% made money</dd>` +
        `<dt>typical result</dt><dd>${xRisk(a.medianR)} the risk <span class="dim-note">(average ${xRisk(a.meanR)})</span></dd>` +
        `<dt>worst</dt><dd class="down">${xRisk(a.worstR)} the risk</dd>` +
        `</dl>` +
        `<div class="rv-tbl-wrap" style="margin-top:6px"><table class="rv-tbl"><thead><tr><th>bought</th><th class="r">result</th><th>why it was sold</th><th class="r">held</th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="dim-note">No finished ${esc(kind)} trades on this stock before this week.</div>`) +
    `<p class="rv-note">Results are shown as a multiple of the money risked: +2× means it made twice what you stood to lose, −1× means it hit the stop-loss. Only finished trades count. One stock has few trades, so this is a rough guide.</p>` +
    `</section>`
  );
}

// Plain names for the fundamentals measures (fundamental-score.js keys).
const MEASURE = {
  revenueGrowth: "sales growth",
  earningsGrowth: "profit growth",
  operatingMargins: "profit margin",
  returnOnAssets: "return on assets",
  returnOnEquity: "return on shareholders' money",
  fcfMargin: "cash generated",
  lowLeverage: "low debt",
  earningsYield: "cheap vs profits",
  ebitdaYield: "cheap vs earnings",
  bookYield: "cheap vs assets",
};

function fundamentals(grade, info, fund, live) {
  if (!grade || grade.quality == null) {
    return `<section class="rv-sec"><div class="rv-h"><span>The business</span></div><div class="dim-note">No company data for this stock.</div></section>`;
  }
  const row = (m) => {
    const p = grade.detail?.[m.key];
    return p == null ? "" : `<tr><td>${esc(MEASURE[m.key] ?? m.label)}</td><td class="r">${p}%</td><td><span class="tp-bar" style="width:${Math.round(p * 0.6)}px"></span></td></tr>`;
  };
  const raw = [
    ["price / expected profit (P/E)", info.forwardPE],
    ["sales growth", info.revenueGrowth != null ? `${(info.revenueGrowth * 100).toFixed(1)}%` : null],
    ["profit margin", info.operatingMargins != null ? `${(info.operatingMargins * 100).toFixed(1)}%` : null],
  ].filter(([, v]) => v != null);
  return (
    `<section class="rv-sec"><div class="rv-h"><span>The business, vs others in its industry</span><span class="rv-h-r">data from ${esc(fund.as_of)}${live ? "" : " (not used when looking back)"}</span></div>` +
    `<dl class="rv-kv"><dt>strength</dt><dd>better than <b>${grade.quality}%</b> of its industry</dd><dt>price</dt><dd>${grade.value == null ? "—" : `cheaper than <b>${grade.value}%</b> of its industry`}</dd></dl>` +
    `<div class="rv-tbl-wrap" style="margin-top:6px"><table class="rv-tbl"><thead><tr><th>measure</th><th class="r">beats</th><th></th></tr></thead><tbody>${[...QUALITY, ...VALUE].map(row).join("")}</tbody></table></div>` +
    (raw.length ? `<p class="rv-note">${raw.map(([k, v]) => `${k} ${esc(typeof v === "number" ? v.toFixed(1) : v)}`).join(" · ")}</p>` : "") +
    `</section>`
  );
}

function historyTable(history, card) {
  const rows = [card, ...history]
    .map(
      (c) =>
        `<tr><td>${esc(c.date)}</td><td>${statusChip(c.status)}</td><td class="rv-setup">${esc(setupName(c.setup))}</td>` +
        `<td class="r">${c.total == null ? "—" : c.total.toFixed(0)}</td><td>${c.stage ? SAY.stage[c.stage] : "—"}</td></tr>`
    )
    .join("");
  return (
    `<section class="rv-sec"><div class="rv-h"><span>The last few weeks on ${esc(ticker)}</span><span class="rv-h-r">"not yet" turning "buy" is normal</span></div>` +
    `<div class="rv-tbl-wrap"><table class="rv-tbl"><thead><tr><th>week</th><th>verdict</th><th>type</th><th class="r">score</th><th>trend</th></tr></thead><tbody>${rows}</tbody></table></div>` +
    `</section>`
  );
}

/** Looking back can show what happened next, under the strategy's own selling rules. */
function outcome(s, w, card) {
  if (card.status !== "BUY" && card.status !== "WATCH") return "";
  const t = runTrade(s, w);
  if (!t) return `<section class="rv-sec"><div class="rv-h"><span>What happened next</span></div><div class="dim-note">On Monday it opened below the stop-loss, so you would not have bought.</div></section>`;
  return (
    `<section class="rv-sec"><div class="rv-h"><span>What happened next, if you had bought</span></div>` +
    `<div>${t.open ? "still held today" : `sold in the week of ${esc(s.bars[t.exitIdx].d)} (${esc(SAY.exit[t.reason] ?? t.reason)})`} after ${t.weeks} weeks: ` +
    `<b class="${t.r > 0 ? "up" : "down"}">${pct(t.pct)}</b> <span class="dim-note">(${xRisk(t.r)} the risk)</span></div>` +
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
    levels.push({ v: p.stop, cls: "stop", lbl: `STOP-LOSS ${px(p.stop)}` });
    if (p.resistance) levels.push({ v: p.resistance.price, cls: "res", lbl: `PAST HIGH ${px(p.resistance.price)}` });
    if (p.support) levels.push({ v: p.support.price, cls: "sup", lbl: `FLOOR ${px(p.support.price)}` });
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
    `<div class="cd-legend"><span><i style="border-color:var(--cyan)"></i>10-week average</span><span><i style="border-color:var(--gold)"></i>30-week average (the main trend)</span>` +
    (p ? `<span><i style="border-color:var(--loss);border-top-style:dashed"></i>stop-loss</span>` : "") +
    (AFTER ? `<span>faded: what happened afterwards</span>` : "") +
    `<span>one candle per week, ${n} weeks${logScale ? " · log scale" : ""}</span></div>`
  );
}

const after = (i, w) => i > w;
