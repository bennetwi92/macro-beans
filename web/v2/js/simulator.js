// Swing-trading simulator — the page module.
//
// Deals you a random S&P 500 name on a random date in the last five years,
// shows 35 sessions of history with the indicators a swing trader actually
// reads, and makes you commit: set a stop by dragging it on the chart, then
// buy, short or pass. The point is repetition — hundreds of reps at reading a
// chart cold — not a strategy backtest, so nothing is scored or stored.
//
// The stop stays draggable once the trade is open, so you can trail it up
// behind a move and bank the gain — but only towards the price, never away
// from it (sim-engine.js owns that rule).
//
// Everything below the app bar fits one mobile screen and never scrolls: a
// status strip, the chart, an action bar. The indicator math lives in
// sim-indicators.js and the trade accounting in sim-engine.js, both pure and
// unit-tested; this module is the DOM, the SVG and the state machine.

import "./nav.js";
import { atr, ema, macd, rsi, sma } from "./sim-indicators.js";
import {
  LONG,
  SHORT,
  dirOf,
  exitTrade,
  isOpen,
  moveStop,
  openTrade,
  stepTrade,
  stopAllows,
  stopMoveAllows,
  stopOutStats,
  tradeStats,
} from "./sim-engine.js";

/* ---------- rules of the game ---------- */

const LOOKBACK = 35; // sessions visible when you decide
const REVIEW_DAYS = 20; // sessions revealed after a pass
const MAX_HOLD = 60; // hard runway; the trade is closed at the last bar
const WARMUP = 200 + LOOKBACK; // bars needed before a decision day (200SMA + window)
const RUNWAY = MAX_HOLD + 2; // bars needed after it
const YEARS = 5; // decision dates come from the last N years
const STOP_ATR = 1.5; // default stop distance, in ATR(14)

const params = new URLSearchParams(location.search);

/* ---------- state ---------- */

let universe = [];
let S = null; // the live session (see newSession)
let scale = null; // chart geometry from the last render, for the stop drag
let dragging = false;
let dragBase = null; // the open trade as it was when this drag started

/* ---------- data ---------- */

const toBar = (r) => ({ d: r[0], o: r[1], h: r[2], l: r[3], c: r[4], v: r[5] });

async function loadUniverse() {
  const res = await fetch("data/sim-universe.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const d = await res.json();
  universe = (d.tickers || []).filter((t) => t.b >= WARMUP + RUNWAY);
  if (!universe.length) throw new Error("universe is empty");
}

async function loadTicker(ticker) {
  const res = await fetch(`data/sim/${encodeURIComponent(ticker)}.json`, {
    cache: "no-cache",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Indicator set drawn on every chart, aligned bar-for-bar with `bars`. */
function indicatorsFor(bars) {
  const closes = bars.map((b) => b.c);
  return {
    e9: ema(closes, 9),
    e22: ema(closes, 22),
    s200: sma(closes, 200),
    hist: macd(closes).hist,
    rsi: rsi(closes, 14),
    atr: atr(bars, 14),
  };
}

/**
 * Every bar that can serve as a decision day: late enough to have a 200-day
 * average behind it, early enough to run a trade out in front of it, and
 * inside the last five years.
 */
function eligibleRange(bars) {
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - YEARS);
  const iso = cutoff.toISOString().slice(0, 10);
  let lo = WARMUP;
  while (lo < bars.length && bars[lo].d < iso) lo++;
  const hi = bars.length - 1 - RUNWAY;
  return [lo, hi];
}

/* ---------- session lifecycle ---------- */

async function newSession() {
  setMessage("Dealing…");
  const wanted = params.get("t");
  const tries = wanted ? [wanted] : pickTickers(6);
  for (const ticker of tries) {
    let data;
    try {
      data = await loadTicker(ticker);
    } catch {
      continue; // a missing file just means the next deal
    }
    const bars = (data.bars || []).map(toBar);
    const [lo, hi] = eligibleRange(bars);
    if (hi < lo) continue;

    let dIdx;
    const wantedDate = params.get("d");
    if (wantedDate) {
      dIdx = bars.findIndex((b) => b.d >= wantedDate);
      if (dIdx < lo || dIdx > hi) dIdx = lo + Math.floor((hi - lo) / 2);
    } else {
      dIdx = lo + Math.floor(Math.random() * (hi - lo + 1));
    }

    const ind = indicatorsFor(bars);
    S = {
      ticker: data.ticker,
      name: data.name,
      sector: data.sector,
      bars,
      ind,
      dIdx,
      curIdx: dIdx,
      mode: "decide",
      stop: defaultStop(bars, ind, dIdx),
      trade: null,
      revealed: false,
      note: "",
    };
    render();
    return;
  }
  setMessage("No playable data yet — the simulator universe has not been built.");
}

/** A few candidate tickers, so one missing file does not end the session. */
function pickTickers(n) {
  const out = [];
  for (let i = 0; i < n && universe.length; i++) {
    out.push(universe[Math.floor(Math.random() * universe.length)].t);
  }
  return out;
}

/** Default stop: 1.5 ATR below the decision close — a starting point to drag. */
function defaultStop(bars, ind, dIdx) {
  const close = bars[dIdx].c;
  const a = ind.atr[dIdx] || close * 0.02;
  return round2(close - STOP_ATR * a);
}

/* ---------- the stop, before and after the entry ---------- */

/** The stop on screen: the trade owns it once there is one, `S.stop` until then. */
const liveStop = () => (S.trade ? S.trade.stop : S.stop);

/** Can the stop still be dragged? Yes while deciding, and while the trade runs. */
const stopIsLive = () => S.mode === "decide" || (S.mode === "trade" && isOpen(S.trade));

/**
 * Has the stop been trailed to the entry or past it? This is what the stop's
 * colour means — the LINE no longer sits on the losing side of the entry —
 * which is a narrower claim than the STOP chip's R, since that also counts
 * profit already banked by a partial exit.
 */
const stopIsFree = () => !!S.trade && dirOf(S.trade) * (S.trade.stop - S.trade.entryPrice) >= 0;

/**
 * Move the stop to `price`. Before the entry that is a free choice; after it,
 * `base` (the trade as it was when the drag began) is what the ratchet is
 * measured against, so a single drag can wander up and back down to where it
 * started — but never below.
 */
function setStop(price, base = S.trade) {
  if (S.trade) S.trade = moveStop(base, price, S.bars[S.curIdx].c);
  else S.stop = price;
}

/** Trail the stop to the entry price: the one-tap "make it free" move. */
function stopToBreakeven() {
  if (!canBreakeven()) return;
  setStop(round2(S.trade.entryPrice));
  render();
}

const canBreakeven = () =>
  S.mode === "trade" &&
  stopMoveAllows(S.trade, round2(S.trade.entryPrice), S.bars[S.curIdx].c);

/* ---------- actions ---------- */

function takePosition(side) {
  const entryIdx = S.dIdx + 1;
  const bar = S.bars[entryIdx];
  S.curIdx = entryIdx;
  S.trade = openTrade({
    side,
    stop: S.stop,
    entryIndex: entryIdx,
    entryPrice: bar.o,
  });
  // The stop is live from the entry bar: a gap through it fills at the open.
  const stepped = stepTrade(S.trade, bar, entryIdx);
  S.trade = stepped.trade;
  if (stepped.stopped) {
    S.note = stopNote(bar, "STOPPED DAY 1");
    S.mode = "recap";
  } else {
    S.mode = "trade";
  }
  render();
}

/**
 * How the stop actually filled. A bar whose OPEN was already through the stop
 * gapped past it — the loss is bigger than 1R and the recap should say why.
 */
function stopNote(bar, plain) {
  const gapped = S.trade.side === SHORT ? bar.o >= S.trade.stop : bar.o <= S.trade.stop;
  return gapped ? "GAPPED THROUGH STOP" : plain;
}

function advanceDay() {
  if (S.curIdx >= S.bars.length - 1) return;
  S.curIdx += 1;
  const bar = S.bars[S.curIdx];
  const stepped = stepTrade(S.trade, bar, S.curIdx);
  S.trade = stepped.trade;
  if (stepped.stopped) {
    S.note = stopNote(bar, "STOPPED OUT");
    S.mode = "recap";
  } else if (S.curIdx - S.trade.entryIndex >= MAX_HOLD) {
    // The runway ends; whatever is left is closed on this close.
    S.trade = exitTrade(S.trade, {
      index: S.curIdx,
      price: bar.c,
      fraction: S.trade.open,
      reason: "time",
    });
    S.note = `TIME EXIT ${MAX_HOLD}D`;
    S.mode = "recap";
  }
  render();
}

function takeExit(fraction) {
  const bar = S.bars[S.curIdx];
  S.trade = exitTrade(S.trade, {
    index: S.curIdx,
    price: bar.c,
    fraction,
    reason: "manual",
  });
  if (!isOpen(S.trade)) {
    S.note = "CLOSED";
    S.mode = "recap";
  }
  render();
}

function pass() {
  S.mode = "review";
  S.curIdx = Math.min(S.bars.length - 1, S.dIdx + REVIEW_DAYS);
  render();
}

/* ---------- view helpers ---------- */

const round2 = (v) => Math.round(v * 100) / 100;
const fmtPx = (v) => v.toFixed(2);
const fmtPct = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
const fmtR = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`;
const sign = (v) => (v >= 0 ? "up" : "down");

function fmtVol(v) {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return String(v);
}

/** The bar range the chart draws for the current mode. */
function viewRange() {
  const to = S.mode === "review" ? Math.min(S.bars.length - 1, S.dIdx + REVIEW_DAYS) : S.curIdx;
  const from = Math.max(0, S.dIdx - (LOOKBACK - 1));
  return [from, to];
}

function setMessage(msg) {
  const el = document.getElementById("sim-chart");
  if (el) el.innerHTML = `<div class="sim-msg">${msg}</div>`;
}

/* ---------- render: status strip ---------- */

function chip(label, value, cls = "") {
  return `<span class="sim-chip ${cls}"><b>${label}</b>${value}</span>`;
}

function identityChip() {
  if (S.mode === "recap" || S.mode === "review" || S.revealed) {
    return chip("", `${S.ticker} · ${S.bars[S.dIdx].d}`, "sim-chip-id");
  }
  return `<button type="button" class="sim-chip sim-chip-id sim-reveal" id="sim-reveal">TAP TO REVEAL</button>`;
}

function renderStatus() {
  const el = document.getElementById("sim-status");
  const bar = S.bars[S.dIdx];
  const stopPct = ((S.stop - bar.c) / bar.c) * 100;
  const chips = [identityChip()];

  if (S.mode === "decide") {
    chips.push(chip("DECIDE", `${LOOKBACK}D CHART`, "sim-chip-mode"));
    chips.push(chip("CLOSE", fmtPx(bar.c)));
    chips.push(
      chip("STOP", `${fmtPx(S.stop)} (${fmtPct(stopPct)})`, "sim-chip-stop")
    );
    chips.push(chip("RSI", (S.ind.rsi[S.dIdx] ?? 0).toFixed(0)));
  } else if (S.mode === "trade") {
    const t = S.trade;
    const st = tradeStats(t, S.bars[S.curIdx].c);
    chips.push(
      chip(t.side === SHORT ? "SHORT" : "LONG", `${S.curIdx - t.entryIndex}D HELD`, "sim-chip-mode")
    );
    chips.push(chip("ENTRY", fmtPx(t.entryPrice)));
    chips.push(chip("OPEN", `${Math.round(t.open * 100)}%`));
    // What the stop is worth, not where it is: negative while it still sits
    // behind the entry, positive once it has been trailed past it.
    const atStop = stopOutStats(t).r;
    chips.push(
      chip("STOP", `${fmtPx(t.stop)} (${fmtR(atStop)})`, `sim-chip-stop ${sign(atStop)}`)
    );
    chips.push(chip("P&L", `${fmtPct(st.total)} · ${fmtR(st.r)}`, sign(st.total)));
  } else if (S.mode === "review") {
    const from = S.bars[S.dIdx].c;
    const seen = S.bars.slice(S.dIdx + 1, S.curIdx + 1);
    const fwd = seen.length ? ((seen[seen.length - 1].c - from) / from) * 100 : 0;
    const best = seen.length ? ((Math.max(...seen.map((b) => b.h)) - from) / from) * 100 : 0;
    const worst = seen.length ? ((Math.min(...seen.map((b) => b.l)) - from) / from) * 100 : 0;
    chips.push(chip("PASSED", `NEXT ${seen.length}D`, "sim-chip-mode"));
    chips.push(chip("CLOSE", fmtPct(fwd), sign(fwd)));
    chips.push(chip("HIGH", fmtPct(best), "up"));
    chips.push(chip("LOW", fmtPct(worst), "down"));
  } else if (S.mode === "recap") {
    const t = S.trade;
    const st = tradeStats(t, S.bars[S.curIdx].c);
    chips.push(chip(t.side === SHORT ? "SHORT" : "LONG", S.note || "CLOSED", "sim-chip-mode"));
    chips.push(chip("ENTRY", fmtPx(t.entryPrice)));
    chips.push(
      chip(
        "EXITS",
        t.exits
          .map((e) => `${Math.round(e.fraction * 100)}% @ ${fmtPx(e.price)}`)
          .join(" · ")
      )
    );
    chips.push(chip("RESULT", `${fmtPct(st.total)} · ${fmtR(st.r)}`, sign(st.total)));
  }

  el.innerHTML = chips.join("");
  const reveal = document.getElementById("sim-reveal");
  if (reveal) {
    reveal.addEventListener("click", () => {
      S.revealed = true;
      renderStatus();
    });
  }
}

/* ---------- render: action bar ---------- */

function button(id, label, cls = "", disabled = false) {
  return `<button type="button" id="${id}" class="sim-btn ${cls}"${
    disabled ? " disabled" : ""
  }>${label}</button>`;
}

function renderActions() {
  const el = document.getElementById("sim-actions");
  const close = S.bars[S.dIdx].c;
  let html = "";

  if (S.mode === "decide") {
    html =
      button("act-buy", "BUY", "sim-btn-buy", !stopAllows(LONG, S.stop, close)) +
      button("act-pass", "PASS", "sim-btn-pass") +
      button("act-short", "SHORT", "sim-btn-short", !stopAllows(SHORT, S.stop, close));
  } else if (S.mode === "trade") {
    const half = S.trade.open > 0.5 + 1e-9;
    html =
      button("act-next", "+1 DAY", "sim-btn-next") +
      // Dragging sets any stop; this hits the entry exactly, which is the one
      // level worth a button — the trade stops costing anything.
      button("act-be", "B/E", "sim-btn-stop", !canBreakeven()) +
      (half ? button("act-half", "EXIT 50%", "sim-btn-exit") : "") +
      button("act-all", half ? "EXIT ALL" : "EXIT REST", "sim-btn-exit");
  } else {
    html = button("act-new", "NEXT OPPORTUNITY ▸", "sim-btn-new");
  }

  el.innerHTML = html;
  wire("act-buy", () => takePosition(LONG));
  wire("act-short", () => takePosition(SHORT));
  wire("act-pass", pass);
  wire("act-next", advanceDay);
  wire("act-be", stopToBreakeven);
  wire("act-half", () => takeExit(0.5));
  wire("act-all", () => takeExit(1));
  wire("act-new", newSession);
}

function wire(id, fn) {
  const b = document.getElementById(id);
  if (b) b.addEventListener("click", fn);
}

/* ---------- render: chart ---------- */

const PAD = { l: 2, r: 46, t: 4, b: 2 };
const GAP = 5;
const WEIGHTS = [
  ["price", 0.555],
  ["vol", 0.1],
  ["macd", 0.17],
  ["rsi", 0.175],
];

const svgEl = (tag, attrs, inner = "") =>
  `<${tag} ${Object.entries(attrs)
    .map(([k, v]) => `${k}="${v}"`)
    .join(" ")}>${inner}</${tag}>`;

const line = (x1, y1, x2, y2, cls) =>
  `<line class="${cls}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(
    1
  )}" y2="${y2.toFixed(1)}"/>`;

const text = (x, y, str, cls, anchor = "start") =>
  `<text class="${cls}" x="${x.toFixed(1)}" y="${y.toFixed(
    1
  )}" text-anchor="${anchor}">${str}</text>`;

function polyline(pts, cls, clip) {
  if (pts.length < 2) return "";
  return `<polyline class="${cls}" ${clip ? `clip-path="url(#${clip})" ` : ""}points="${pts
    .map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ")}"/>`;
}

function renderChart() {
  const wrap = document.getElementById("sim-chart");
  if (!wrap || !S) return;
  const W = Math.max(280, wrap.clientWidth);
  const H = Math.max(240, wrap.clientHeight);
  const [from, to] = viewRange();
  const bars = S.bars;
  const n = to - from + 1;

  // Vertical split into the four stacked panels.
  const plotH = H - PAD.t - PAD.b - GAP * (WEIGHTS.length - 1);
  const panels = {};
  let y = PAD.t;
  for (const [key, w] of WEIGHTS) {
    const h = plotH * w;
    panels[key] = { top: y, bot: y + h, h };
    y += h + GAP;
  }

  const plotW = W - PAD.l - PAD.r;
  const slot = plotW / n;
  const cx = (i) => PAD.l + slot * (i - from + 0.5);
  const bodyW = Math.max(1.4, Math.min(slot * 0.62, 9));

  // ---- price scale: candles, the fast averages, the stop and every fill ----
  let lo = Infinity;
  let hi = -Infinity;
  const consider = (v) => {
    if (v == null || !Number.isFinite(v)) return;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  };
  for (let i = from; i <= to; i++) {
    consider(bars[i].l);
    consider(bars[i].h);
    consider(S.ind.e9[i]);
    consider(S.ind.e22[i]);
  }
  consider(liveStop());
  if (S.trade) {
    consider(S.trade.entryPrice);
    for (const e of S.trade.exits) consider(e.price);
  }
  // Keep a stop's worth of air above and below the decision close whatever the
  // bars did: a short's stop goes ABOVE the price, and in a tight range there
  // is nowhere to drag it to. One default stop distance is enough to grab —
  // drag further and the release re-renders around the new level. Once the
  // trade is open the drag is fenced between the stop and the current close,
  // both already in range, so the air would only flatten the candles.
  if (S.mode === "decide") {
    const air = (S.ind.atr[S.dIdx] || S.bars[S.dIdx].c * 0.02) * STOP_ATR;
    consider(S.bars[S.dIdx].c + air);
    consider(S.bars[S.dIdx].c - air);
  }
  const span = hi - lo || hi * 0.02 || 1;
  lo -= span * 0.06;
  hi += span * 0.06;

  const P = panels.price;
  const yPrice = (v) => P.bot - ((v - lo) / (hi - lo)) * P.h;
  const priceAt = (py) => lo + ((P.bot - py) / P.h) * (hi - lo);

  let out = "";
  out += `<defs><clipPath id="sim-clip-price"><rect x="0" y="${P.top.toFixed(
    1
  )}" width="${W}" height="${P.h.toFixed(1)}"/></clipPath></defs>`;

  // ---- price grid + right-hand axis ----
  const stopY0 = yPrice(liveStop());
  for (let g = 0; g <= 3; g++) {
    const v = lo + ((hi - lo) * g) / 3;
    const gy = yPrice(v);
    out += line(PAD.l, gy, W - PAD.r, gy, "sim-grid");
    // The stop's own tag wins the gutter where the two would collide.
    if (Math.abs(gy - stopY0) > 9) out += text(W - PAD.r + 4, gy + 3, fmtPx(v), "sim-axis");
  }

  // ---- moving averages ----
  const maPts = (series) => {
    const pts = [];
    for (let i = from; i <= to; i++) {
      const v = series[i];
      if (v != null) pts.push([cx(i), yPrice(v)]);
    }
    return pts;
  };
  out += polyline(maPts(S.ind.s200), "sim-ma sim-ma200", "sim-clip-price");
  out += polyline(maPts(S.ind.e22), "sim-ma sim-ma22");
  out += polyline(maPts(S.ind.e9), "sim-ma sim-ma9");

  // The 200SMA is often far outside a 35-day window; say where it is instead
  // of letting the clip hide it silently.
  const s200 = S.ind.s200[to];
  if (s200 != null && (s200 > hi || s200 < lo)) {
    const away = ((s200 - bars[to].c) / bars[to].c) * 100;
    const ly = s200 > hi ? P.top + 9 : P.bot - 3;
    out += text(PAD.l + 3, ly, `200SMA ${s200 > hi ? "▲" : "▼"} ${fmtPx(s200)} (${fmtPct(away)})`, "sim-ma-off");
  }

  // ---- candles ----
  for (let i = from; i <= to; i++) {
    const b = bars[i];
    const up = b.c >= b.o;
    const x = cx(i);
    const cls = up ? "sim-c-up" : "sim-c-dn";
    const yO = yPrice(b.o);
    const yC = yPrice(b.c);
    out += line(x, yPrice(b.h), x, yPrice(b.l), `sim-wick ${cls}`);
    out += `<rect class="sim-body ${cls}" x="${(x - bodyW / 2).toFixed(1)}" y="${Math.min(
      yO,
      yC
    ).toFixed(1)}" width="${bodyW.toFixed(1)}" height="${Math.max(
      1,
      Math.abs(yC - yO)
    ).toFixed(1)}"/>`;
  }

  // ---- decision-day divider ----
  const dx = cx(S.dIdx) + slot / 2;
  if (S.dIdx >= from && S.dIdx <= to) {
    out += line(dx, PAD.t, dx, panels.rsi.bot, "sim-dline");
    out += text(dx - 3, P.top + 9, "DECISION", "sim-dlabel", "end");
  }

  // ---- entry / exit markers ----
  if (S.trade) {
    const t = S.trade;
    const ex = cx(t.entryIndex);
    const ey = yPrice(t.entryPrice);
    const dirCls = t.side === SHORT ? "sim-mark-short" : "sim-mark-long";
    const up = t.side !== SHORT;
    out += `<polygon class="sim-mark ${dirCls}" points="${ex.toFixed(1)},${(
      ey + (up ? -7 : 7)
    ).toFixed(1)} ${(ex - 4.5).toFixed(1)},${(ey + (up ? -0.5 : 0.5)).toFixed(1)} ${(
      ex + 4.5
    ).toFixed(1)},${(ey + (up ? -0.5 : 0.5)).toFixed(1)}"/>`;
    out += line(ex, ey, cx(S.curIdx), ey, "sim-entry-line");
    for (const e of t.exits) {
      const x = cx(e.index);
      const yv = yPrice(e.price);
      const cls = e.reason === "stop" ? "sim-mark-stopped" : "sim-mark-exit";
      out += `<rect class="sim-mark ${cls}" x="${(x - 3.5).toFixed(1)}" y="${(
        yv - 3.5
      ).toFixed(1)}" width="7" height="7" transform="rotate(45 ${x.toFixed(1)} ${yv.toFixed(
        1
      )})"/>`;
      // Labels flip to the left half of the plot's right edge so they never
      // run under the price axis or the stop tag.
      const right = x > PAD.l + plotW * 0.72;
      out += text(
        x + (right ? -6 : 6),
        yv - 5,
        e.reason === "stop" ? "STOP" : `${Math.round(e.fraction * 100)}%`,
        "sim-mark-label",
        right ? "end" : "start"
      );
    }
  }

  // ---- stop line (draggable while deciding AND while the trade runs) ----
  const stop = liveStop();
  const stopY = yPrice(stop);
  const live = stopIsLive();
  // Past the entry the stop is no longer a loss — colour says which it is.
  const free = stopIsFree();
  out += line(
    PAD.l,
    stopY,
    W - PAD.r,
    stopY,
    `sim-stop ${live ? "sim-stop-live" : ""} ${free ? "sim-stop-free" : ""}`
  );
  out += `<rect class="sim-stop-tag ${free ? "sim-stop-free" : ""}" x="${(
    W - PAD.r + 1
  ).toFixed(1)}" y="${(stopY - 7).toFixed(1)}" width="${PAD.r - 2}" height="14" rx="2"/>`;
  out += text(W - PAD.r + 4, stopY + 4, fmtPx(stop), "sim-stop-text");
  if (live) {
    out += text(
      PAD.l + 3,
      stopY - 4,
      S.trade ? "STOP — DRAG TO TRAIL" : "STOP — DRAG TO SET",
      `sim-stop-hint ${free ? "sim-stop-free" : ""}`
    );
  }

  // ---- volume ----
  const V = panels.vol;
  let vMax = 0;
  for (let i = from; i <= to; i++) vMax = Math.max(vMax, bars[i].v);
  for (let i = from; i <= to; i++) {
    const b = bars[i];
    const h = vMax ? (b.v / vMax) * V.h : 0;
    out += `<rect class="sim-vol ${b.c >= b.o ? "sim-c-up" : "sim-c-dn"}" x="${(
      cx(i) - bodyW / 2
    ).toFixed(1)}" y="${(V.bot - h).toFixed(1)}" width="${bodyW.toFixed(1)}" height="${h.toFixed(
      1
    )}"/>`;
  }
  out += text(PAD.l + 3, V.top + 8, `VOL ${fmtVol(bars[to].v)}`, "sim-plabel");
  out += line(PAD.l, V.bot, W - PAD.r, V.bot, "sim-grid");

  // ---- MACD histogram ----
  const M = panels.macd;
  let mMax = 1e-9;
  for (let i = from; i <= to; i++) {
    const v = S.ind.hist[i];
    if (v != null) mMax = Math.max(mMax, Math.abs(v));
  }
  const mZero = M.top + M.h / 2;
  const yMacd = (v) => mZero - (v / mMax) * (M.h / 2 - 3);
  for (let i = from; i <= to; i++) {
    const v = S.ind.hist[i];
    if (v == null) continue;
    const yv = yMacd(v);
    out += `<rect class="sim-macd ${v >= 0 ? "sim-c-up" : "sim-c-dn"}" x="${(
      cx(i) - bodyW / 2
    ).toFixed(1)}" y="${Math.min(yv, mZero).toFixed(1)}" width="${bodyW.toFixed(
      1
    )}" height="${Math.max(0.8, Math.abs(yv - mZero)).toFixed(1)}"/>`;
  }
  out += line(PAD.l, mZero, W - PAD.r, mZero, "sim-grid");
  const lastHist = S.ind.hist[to];
  out += text(
    PAD.l + 3,
    M.top + 8,
    `MACD 12/26/9 ${lastHist == null ? "" : lastHist.toFixed(2)}`,
    "sim-plabel"
  );

  // ---- RSI ----
  const R = panels.rsi;
  const yRsi = (v) => R.bot - (v / 100) * R.h;
  for (const [level, cls] of [
    [30, "sim-grid sim-grid-dash"],
    [50, "sim-grid sim-rsi-mid"],
    [70, "sim-grid sim-grid-dash"],
  ]) {
    out += line(PAD.l, yRsi(level), W - PAD.r, yRsi(level), cls);
    out += text(W - PAD.r + 4, yRsi(level) + 3, String(level), "sim-axis");
  }
  const rsiPts = [];
  for (let i = from; i <= to; i++) {
    const v = S.ind.rsi[i];
    if (v != null) rsiPts.push([cx(i), yRsi(v)]);
  }
  out += polyline(rsiPts, "sim-rsi");
  const lastRsi = S.ind.rsi[to];
  out += text(
    PAD.l + 3,
    R.top + 8,
    `RSI 14 ${lastRsi == null ? "" : lastRsi.toFixed(0)}`,
    "sim-plabel"
  );

  // ---- legend ----
  out += text(PAD.l + 3, P.top + 9, "9EMA", "sim-plabel sim-lg9");
  out += text(PAD.l + 38, P.top + 9, "22EMA", "sim-plabel sim-lg22");
  out += text(PAD.l + 80, P.top + 9, "200SMA", "sim-plabel sim-lg200");

  wrap.innerHTML = `<svg class="sim-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out}</svg>`;
  scale = { W, H, panel: P, yPrice, priceAt, lo, hi };
}

/* ---------- stop dragging ---------- */

const TICK = 0.01; // prices are quoted to the cent, so the fence is one cent wide

function stopFromEvent(ev) {
  const svg = document.querySelector("#sim-chart .sim-svg");
  if (!svg || !scale) return null;
  const rect = svg.getBoundingClientRect();
  const py = ev.clientY - rect.top;
  const clamped = Math.max(scale.panel.top, Math.min(scale.panel.bot, py));
  return fenceStop(round2(scale.priceAt(clamped)));
}

/**
 * Hold a dragged price inside the levels the stop is allowed to occupy, so the
 * line parks against the fence instead of snapping back when the engine
 * refuses the move. Free while deciding; between the trade's stop and today's
 * close once it is open.
 */
function fenceStop(price) {
  const base = dragBase || S.trade;
  if (!base) return price;
  const close = S.bars[S.curIdx].c;
  return base.side === SHORT
    ? Math.min(base.stop, Math.max(round2(close + TICK), price))
    : Math.max(base.stop, Math.min(round2(close - TICK), price));
}

/** Live feedback while dragging — moving attributes, not a full re-render. */
function paintStop() {
  const svg = document.querySelector("#sim-chart .sim-svg");
  if (!svg || !scale) return;
  const stop = liveStop();
  const y = scale.yPrice(stop);
  const l = svg.querySelector(".sim-stop");
  const tag = svg.querySelector(".sim-stop-tag");
  const txt = svg.querySelector(".sim-stop-text");
  const hint = svg.querySelector(".sim-stop-hint");
  // Trailing past the entry flips the stop from red to green mid-drag.
  const free = stopIsFree();
  if (l) {
    l.setAttribute("y1", y.toFixed(1));
    l.setAttribute("y2", y.toFixed(1));
    l.classList.toggle("sim-stop-free", free);
  }
  if (tag) {
    tag.setAttribute("y", (y - 7).toFixed(1));
    tag.classList.toggle("sim-stop-free", free);
  }
  if (txt) {
    txt.setAttribute("y", (y + 4).toFixed(1));
    txt.textContent = fmtPx(stop);
  }
  if (hint) {
    hint.setAttribute("y", (y - 4).toFixed(1));
    hint.classList.toggle("sim-stop-free", free);
  }
  renderStatus();
  renderActions();
}

function initDrag() {
  const wrap = document.getElementById("sim-chart");
  const begin = (ev) => {
    if (!S || !stopIsLive() || !scale) return;
    const svg = wrap.querySelector(".sim-svg");
    if (!svg) return;
    const py = ev.clientY - svg.getBoundingClientRect().top;
    // Only the price panel grabs the stop; the indicator panels stay inert.
    if (py < scale.panel.top - 10 || py > scale.panel.bot + 10) return;
    dragging = true;
    // Every move in this gesture is measured against where the stop started,
    // so an overshoot can be walked back to it — but no further.
    dragBase = S.trade;
    wrap.setPointerCapture?.(ev.pointerId);
    drag(ev);
  };
  const drag = (ev) => {
    const v = stopFromEvent(ev);
    if (v != null) {
      setStop(v, dragBase);
      paintStop();
    }
    ev.preventDefault();
  };
  const move = (ev) => {
    if (!dragging) return;
    drag(ev);
  };
  const end = (ev) => {
    if (!dragging) return;
    dragging = false;
    dragBase = null;
    wrap.releasePointerCapture?.(ev.pointerId);
    render(); // re-render once, so the price scale can grow to fit the new stop
  };
  wrap.addEventListener("pointerdown", begin);
  wrap.addEventListener("pointermove", move);
  wrap.addEventListener("pointerup", end);
  wrap.addEventListener("pointercancel", end);
}

/* ---------- render ---------- */

function render() {
  if (!S) return;
  // Both bars are laid out before the chart measures itself: the chart takes
  // the height they leave over, so drawing it first would size it against a
  // stale (taller) box and push the RSI panel under the action bar.
  renderStatus();
  renderActions();
  renderChart();
}

/* ---------- keyboard (desktop convenience) ---------- */

document.addEventListener("keydown", (ev) => {
  if (!S) return;
  const key = ev.key.toLowerCase();
  const hit = {
    decide: { b: () => takePosition(LONG), s: () => takePosition(SHORT), p: pass },
    trade: {
      n: advanceDay,
      e: stopToBreakeven,
      h: () => takeExit(0.5),
      x: () => takeExit(1),
    },
    // Deliberately NOT "n": holding the advance key through a close would
    // skip straight past the recap, which is the part worth reading.
    review: { enter: newSession, d: newSession },
    recap: { enter: newSession, d: newSession },
  }[S.mode];
  const fn = hit && hit[key];
  if (!fn) return;
  // A disabled button means an illegal move; the keyboard must respect it too.
  if (S.mode === "decide" && key === "b" && !stopAllows(LONG, S.stop, S.bars[S.dIdx].c)) return;
  if (S.mode === "decide" && key === "s" && !stopAllows(SHORT, S.stop, S.bars[S.dIdx].c)) return;
  ev.preventDefault();
  fn();
});

/* ---------- boot ---------- */

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => S && renderChart(), 120);
});

initDrag();
loadUniverse()
  .then(newSession)
  .catch((err) => setMessage(`Could not load the simulator universe (${err.message})`));

// Debug hook: inspect or drive a deal from the console (or a headless browser)
// without clicking. Pairs with the ?t=<ticker>&d=<date> params, which deal a
// fixed hand. Not part of the page's own API — nothing in the app reads it.
window.__sim = {
  state: () => S,
  setStop: (v) => {
    setStop(round2(v));
    render();
  },
  breakeven: stopToBreakeven,
};
