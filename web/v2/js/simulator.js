// Swing-trading simulator — the page module.
//
// Deals you a random S&P 500 name on a random date in the last five years,
// shows 35 sessions of history with the indicators a swing trader actually
// reads, and makes you commit: set a stop by dragging it on the chart, then
// buy, short, wait or pass. The point is repetition — hundreds of reps at
// reading a chart cold — not a strategy backtest, so nothing is scored or
// stored.
//
// WAIT is the fourth answer, and the one most setups deserve: it rolls the
// decision day forward a single session and deals the same hand again, one bar
// wiser. It is not free — the chip counts the sessions you have stood aside
// and what the price did while you did — because standing aside for a
// confirmation that never comes is its own bad habit.
//
// The stop stays draggable once the trade is open, so you can trail it up
// behind a move and bank the gain — but only towards the price, never away
// from it (sim-engine.js owns that rule).
//
// A one-line MARKET strip sits under the status chips: the trend of SPY, QQQ
// and IWM (daily and weekly), where this stock's sector ETF ranks, its 20-day
// relative strength, the VIX, and the tailwind score those add up to. It reads
// as of the day on screen and never past it. Take a long into a market below
// its 50-day and the strip becomes the warning instead; in Strict Mode it
// takes the button away. The math is sim-market.js, also pure and tested.
//
// At most one chart pattern is annotated per deal — a triangle, a flag, a
// double bottom, or failing those a candlestick or a support level. It is
// found once at deal time and then plays out as the hand does. The geometry
// lives in sim-patterns.js and sim-structure.js; this module only draws what
// they hand back, and draws nothing at all when they hand back null.
//
// Everything below the app bar fits one mobile screen and never scrolls: a
// status strip, the chart, an action bar. The indicator math lives in
// sim-indicators.js and the trade accounting in sim-engine.js, both pure and
// unit-tested; this module is the DOM, the SVG and the state machine.

import "./nav.js";
import { atr, ema, macd, rsi, sma } from "./sim-indicators.js";
import {
  PATTERN_IDS,
  detectPattern,
  isPatternOver,
  lineAt,
  patternText,
  resolvePattern,
} from "./sim-patterns.js";
import {
  BENCHMARK,
  INDICES,
  STRICT_MIN,
  VIX_PENALTY,
  VIX_SPIKE,
  compositePct,
  marketStatus,
  prepareMarket,
  scoreFor,
} from "./sim-market.js";
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

// Sessions VISIBLE when you decide. This is a phone-screen budget and nothing
// more: the bars, the indicators and the pattern detector all read as far back
// as they need (sim-patterns.js DETECT_BARS), and a pattern that starts before
// the left edge is simply drawn from the edge.
const LOOKBACK = 35;
const REVIEW_DAYS = 20; // sessions revealed after a pass
// Sessions you may stand aside before the deal is called. Two trading weeks:
// long enough for a triangle to break or a base to give way, short enough that
// waiting stays a decision rather than a way of never taking one.
const MAX_WAIT = 10;
const MAX_HOLD = 60; // hard runway; the trade is closed at the last bar
const WARMUP = 200 + LOOKBACK; // bars needed before a decision day (200SMA + window)
const RUNWAY = MAX_HOLD + 2; // bars needed after it
const YEARS = 5; // decision dates come from the last N years
const STOP_ATR = 1.5; // default stop distance, in ATR(14)

const params = new URLSearchParams(location.search);

/* ---------- state ---------- */

let universe = [];
let market = null; // prepared market-context feed, or null (the feature fails open)
let rules = loadRules(); // "learn" | "strict" — see the rule modes section
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

/**
 * The market-context feed, or nothing.
 *
 * Deliberately not awaited by the deal: a missing or slow sim-market.json must
 * never stop a hand being played. The strip renders "MARKET SCORE UNAVAILABLE"
 * and every gate stands down — fail open is the rule the whole feature obeys.
 */
async function loadMarket() {
  try {
    const res = await fetch("data/sim-market.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    market = prepareMarket(await res.json());
  } catch (err) {
    market = null;
    console.warn(`simulator: no market context (${err.message})`);
  }
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

async function newSession(opts = {}) {
  setMessage("Dealing…");
  const wanted = params.get("t");
  const tries = wanted ? [wanted] : pickTickers(6);
  const hunt = opts.anyPattern ? null : wantedPattern();
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
    const ind = indicatorsFor(bars);

    let dIdx;
    const wantedDate = params.get("d");
    if (wantedDate) {
      dIdx = bars.findIndex((b) => b.d >= wantedDate);
      if (dIdx < lo || dIdx > hi) dIdx = lo + Math.floor((hi - lo) / 2);
    } else if (hunt) {
      dIdx = huntPattern(bars, ind, lo, hi, hunt);
      if (dIdx == null) continue; // this name never shows it; try the next
    } else {
      // A random deal keeps a full WAIT budget behind it, so the button is
      // never disabled just because the deal landed near the end of the
      // runway. A pinned (`?d=`) or hunted deal takes the day it asked for and
      // makes do with whatever room is left.
      const top = Math.max(lo, hi - MAX_WAIT);
      dIdx = lo + Math.floor(Math.random() * (top - lo + 1));
    }

    S = {
      ticker: data.ticker,
      name: data.name,
      sector: data.sector,
      bars,
      closes: bars.map((b) => b.c), // the RS line's numerator; kept once, not per render
      ind,
      dIdx,
      dIdx0: dIdx, // the day this hand was dealt on, so WAIT can price itself
      hiIdx: hi, // last bar that still leaves a full trade runway in front of it
      waited: 0,
      curIdx: dIdx,
      mode: "decide",
      stop: defaultStop(bars, ind, dIdx),
      stopTouched: false, // an untouched stop re-anchors when the day moves
      trade: null,
      revealed: false,
      note: "",
      mkt: null, // market status as of the day on screen; refreshed every render
      mktEntry: null, // ...frozen at the entry, so the recap grades the decision
      armed: null, // a counter-trend side whose warning has been shown once
      penalty: 0, // Learning Mode: tailwind points forgone by taking it anyway
      pattern: patternsOff() ? null : patternAt(bars, ind, dIdx),
    };
    render();
    return;
  }
  if (hunt) {
    console.warn(`simulator: no ${hunt} found in six deals — dealing normally`);
    return newSession({ anyPattern: true });
  }
  setMessage("No playable data yet — the simulator universe has not been built.");
}

/* ---------- the chart pattern ---------- */

/** `?p=0` turns the annotation off entirely — and is the kill switch. */
const patternsOff = () => params.get("p") === "0";

/** `?p=<id>` deals until a hand carries that pattern. Unknown ids are ignored. */
function wantedPattern() {
  const id = params.get("p");
  if (!id || id === "0") return null;
  if (PATTERN_IDS.includes(id)) return id;
  console.warn(`simulator: unknown pattern id "${id}" — ignoring`);
  return null;
}

/**
 * Detection over `[0..dIdx]`. Pinned to the deal: run once at deal time and,
 * once a position is open, never again — only the pattern's STATE moves, so a
 * label cannot churn as you tap `+1 DAY`. WAIT is the one exception, and a
 * narrow one: see `refreshPattern`.
 */
function patternAt(bars, ind, dIdx) {
  return detectPattern(bars, ind.atr, dIdx, {
    visibleFrom: Math.max(0, dIdx - (LOOKBACK - 1)),
  });
}

/**
 * Re-look for a pattern after WAIT has moved the decision day.
 *
 * A LIVE claim is left strictly alone — re-detecting under one is exactly the
 * churn that pinning exists to prevent, and the shape you are waiting on is
 * the one whose fate you want to watch. But once it has failed, expired or
 * been abandoned — or was never there — the next session is entitled to a
 * fresh look, because "the signal is not clear yet, but something is forming"
 * is the whole reason WAIT exists.
 *
 * A fresh look that is already spent by the time it reaches today is
 * discarded, so the annotation cannot flicker between two dead shapes.
 */
function refreshPattern() {
  if (patternsOff() || !isPatternOver(S.pattern)) return;
  const p = resolvePattern(patternAt(S.bars, S.ind, S.dIdx), S.bars, S.curIdx);
  if (!isPatternOver(p)) S.pattern = p;
}

/**
 * The first decision day on this name that shows `id`, or `null`.
 *
 * Probing is strided rather than exhaustive: the eligible range runs to a
 * thousand-odd sessions and detection is not free, so a dense walk would stall
 * the deal for seconds on a phone. A pattern spans weeks, so a stride of three
 * cannot step over one — it only ever lands on a different bar of the same
 * shape, which is exactly as good a hand.
 */
const HUNT_STRIDE = 3;
const HUNT_PROBES = 400;

function huntPattern(bars, ind, lo, hi, id) {
  const start = lo + Math.floor(Math.random() * Math.max(1, hi - lo + 1));
  for (let n = 0; n < HUNT_PROBES; n++) {
    // Wrap, so a hunt started near the end of the runway still sees the rest.
    const i = lo + (((start - lo + n * HUNT_STRIDE) % (hi - lo + 1)) + (hi - lo + 1)) % (hi - lo + 1);
    if (patternAt(bars, ind, i)?.id === id) return i;
  }
  return null;
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

/* ---------- market confluence ---------- */

// Rule modes. LEARN lets you take anything and prices the mistake afterwards;
// STRICT takes the button away below the gate. The choice is remembered per
// browser and `?rules=strict|learn` overrides it for a link you want to share.
const RULES_KEY = "mb.sim.rules";

function loadRules() {
  const q = new URLSearchParams(location.search).get("rules");
  if (q === "strict" || q === "learn") return q;
  try {
    return localStorage.getItem(RULES_KEY) === "strict" ? "strict" : "learn";
  } catch {
    return "learn"; // private mode / storage blocked — the permissive default
  }
}

function toggleRules() {
  rules = rules === "strict" ? "learn" : "strict";
  try {
    localStorage.setItem(RULES_KEY, rules);
  } catch {
    /* not persisting is fine; the session still honours the choice */
  }
  if (S) S.armed = null; // a warning acknowledged under the old rules is spent
  render();
}

/** The day the strip reports on: the decision day, or the tape once it moves. */
const shownIdx = () => (S.mode === "decide" ? S.dIdx : S.curIdx);

/**
 * Market status as of a bar. Everything it reads is dated ON OR BEFORE that
 * bar (sim-market.js `asOf`), so the strip can never leak a session the chart
 * has not shown yet.
 */
function marketAt(idx) {
  if (!market || !S) return null;
  return marketStatus(market, {
    sector: S.sector,
    date: S.bars[idx].d,
    stock: { closes: S.closes, index: idx },
  });
}

/**
 * May `side` be taken, and what should be said about it?
 *
 *   pct      the composite — today the market block alone, rescaled to a
 *            percentage of the points that were actually on offer, so a
 *            missing feed reads as `null` rather than as a failing grade
 *   counter  taking this side against the broad market's own trend
 *   blocked  Strict Mode, below the gate
 *
 * `null` pct means nothing was scoreable: nothing is blocked and nothing is
 * warned. Fail open, every time.
 */
function gateFor(side) {
  const st = S.mkt;
  const score = st?.available ? scoreFor(st, side) : null;
  const pct = compositePct([score]);
  return {
    score,
    pct,
    counter: !!st?.available && st.regime === (side === LONG ? "bear" : "bull"),
    blocked: rules === "strict" && pct != null && pct < STRICT_MIN,
  };
}

// The story's copy, verbatim for the long case and mirrored for the short —
// the button exists, so the rule has to cover it or Strict Mode is one tap
// away from being decorative.
const counterText = (side) =>
  side === LONG
    ? "Warning: Taking a long position against a broad market downtrend reduces win-rate by ~40%."
    : "Warning: Taking a short position against a broad market uptrend reduces win-rate by ~40%.";

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
  if (S.trade) {
    S.trade = moveStop(base, price, S.bars[S.curIdx].c);
  } else {
    S.stop = price;
    // A stop you chose is a level; a stop you never touched is just the ATR
    // default. WAIT re-anchors the second and respects the first.
    S.stopTouched = true;
  }
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
  const gate = gateFor(side);
  // Strict Mode: the trade simply does not happen. The button is already
  // disabled, so this only catches the keyboard — but it catches it.
  if (gate.blocked) return;
  // Counter-trend, in Learning Mode: the first tap buys the warning, the
  // second buys the stock. One acknowledgement per side per hand — the strip
  // keeps saying it, but it stops standing in the way.
  if (gate.counter && S.armed !== side) {
    S.armed = side;
    render();
    return;
  }
  // Taken below the gate anyway: log what it cost in tailwind points. Learning
  // Mode's whole claim is that it lets you make the mistake and shows you the
  // bill in the recap.
  S.penalty =
    gate.pct != null && gate.pct < STRICT_MIN && gate.score ? gate.score.max - gate.score.total : 0;
  S.mktEntry = S.mkt;
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

/**
 * Stand aside for one session: the decision day rolls forward a bar, the
 * window slides with it, and the same hand is dealt again one bar wiser. No
 * position is opened and nothing is scored — the only cost is a session off
 * the WAIT budget and whatever the price did in the meantime, both of which
 * the status strip shows.
 */
function waitDay() {
  if (!canWait()) return;
  S.dIdx += 1;
  S.curIdx = S.dIdx;
  S.waited += 1;
  // A new decision day is a new decision: the counter-trend warning has to be
  // acknowledged again, on whatever the market looks like now.
  S.armed = null;
  // Resolve the pinned pattern onto the new bar FIRST, so a claim that died on
  // it is dead before the fresh look decides whether to replace it.
  S.pattern = resolvePattern(S.pattern, S.bars, S.curIdx);
  refreshPattern();
  // An untouched stop follows the price; a dragged one stays where it was put,
  // even if the wait has left it on the wrong side (the BUY/SHORT button goes
  // dead, which is the same language every other illegal stop speaks).
  if (!S.stopTouched) S.stop = defaultStop(S.bars, S.ind, S.dIdx);
  render();
}

/** Sessions still available to stand aside: the budget, fenced by the runway. */
const waitsLeft = () => Math.min(MAX_WAIT - S.waited, S.hiIdx - S.dIdx);

const canWait = () => S.mode === "decide" && waitsLeft() > 0;

/** What standing aside has cost so far, in percent off the day you were dealt. */
const waitDrift = () =>
  ((S.bars[S.dIdx].c - S.bars[S.dIdx0].c) / S.bars[S.dIdx0].c) * 100;

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
    // The wait rides in the mode chip rather than a sixth one: the strip
    // collapses to a single row in landscape, and a chip that only sometimes
    // exists is the one that gets clipped.
    chips.push(
      chip(
        "DECIDE",
        S.waited ? `WAITED ${S.waited}D ${fmtPct(waitDrift())}` : `${LOOKBACK}D CHART`,
        "sim-chip-mode"
      )
    );
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
    // The market read at the entry is NOT a sixth chip: two rows is the whole
    // budget and RESULT is what a sixth one pushes off the bottom. The strip
    // below rewinds to the entry instead — it is the market's own line.
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

/* ---------- render: market strip ---------- */

// One glyph per trend state, used for the indices and for the sector band. The
// strip is a single line of 9px mono on a phone; a word where a glyph will do
// is a word that pushes something else off the end.
const TREND_GLYPH = { bull: "▲", neutral: "▬", bear: "▼" };
const glyph = (t) => `<i class="mk-${t || "na"}">${TREND_GLYPH[t] || "·"}</i>`;

/** A sector band drawn in the same alphabet as a trend: leading, middling, lagging. */
const bandTrend = (b) =>
  b === "top" ? "bull" : b === "bottom" ? "bear" : b === "mid" ? "neutral" : null;

/** One strip segment. `title` carries the long version — nothing here is ONLY a glyph. */
const seg = (cls, title, body) => `<span class="mk-seg ${cls}" title="${title}">${body}</span>`;

// The two fixed titles. Written out here rather than inline so the segment
// list below stays a list of what is on the strip.
const TREND_TITLE =
  "Trend on the daily and weekly: price &gt; 21EMA &gt; 50SMA is bullish, price &lt; 50SMA bearish.";
const UNMAPPED_TITLE =
  "No sector ETF for this ticker — benchmarked against SPY, and the sector points are excluded from the score.";

/** Colour band for a confluence percentage: at the gate, near it, or under. */
const scoreBand = (pct) =>
  pct == null ? "mk-na" : pct >= STRICT_MIN ? "mk-bull" : pct >= 45 ? "mk-neutral" : "mk-bear";

/**
 * The banner that REPLACES the read-out, or null to keep the read-out.
 *
 * Both cases are moments where the numbers have already made their point and
 * what is left to say is a sentence. Sharing the strip rather than opening a
 * second row is deliberate: this page has no spare vertical space, and the
 * warning is about the very market the strip was describing.
 */
function marketBanner() {
  if (S.mode !== "decide") return null;
  if (S.armed) {
    const btn = S.armed === LONG ? "BUY" : "SHORT";
    return { cls: "mk-warn", text: `⚠ ${counterText(S.armed)} TAP ${btn} AGAIN TO CONFIRM.` };
  }
  const l = gateFor(LONG);
  const sh = gateFor(SHORT);
  if (!l.blocked && !sh.blocked) return null;
  const pct = (g) => `${Math.round(g.pct)}%`;
  const text =
    l.blocked && sh.blocked
      ? `STRICT MODE — NO TRADE HERE: LONG ${pct(l)}, SHORT ${pct(sh)}, gate ${STRICT_MIN}%. WAIT or PASS.`
      : l.blocked
        ? `STRICT MODE — LONG BLOCKED: ${pct(l)} confluence is under the ${STRICT_MIN}% gate.`
        : `STRICT MODE — SHORT BLOCKED: ${pct(sh)} confluence is under the ${STRICT_MIN}% gate.`;
  return { cls: "mk-block", text };
}

/** The rule-mode toggle: the one control on the strip, and the last thing on it. */
const modeButton = () =>
  `<button type="button" id="mk-mode" class="mk-mode ${rules === "strict" ? "mk-strict" : ""}" title="${
    rules === "strict"
      ? `Strict Mode: trades under ${STRICT_MIN}% confluence are blocked. Tap for Learning Mode.`
      : "Learning Mode: the trade is allowed and the forgone points are shown in the recap. Tap for Strict Mode."
  }">${rules === "strict" ? "STRICT" : "LEARN"}</button>`;

function renderMarket() {
  const el = document.getElementById("sim-market");
  if (!el || !S) return;
  // In the recap the strip rewinds to the day you committed: the tape has moved
  // on by then, and what is worth grading is the market you actually bought
  // into. Every other mode reads the day on screen.
  const recap = S.mode === "recap" && !!S.mktEntry?.available;
  const st = recap ? S.mktEntry : S.mkt;
  let cls = "sim-market";
  let html;

  if (!st?.available) {
    // Fail open, and say so. The points drop out of the composite entirely
    // (sim-market.js `compositePct` rescales), so no gate can fire.
    cls += " mk-off";
    html = `<span class="mk-seg">MARKET SCORE UNAVAILABLE — CONFLUENCE RESCALED</span>`;
  } else {
    const banner = marketBanner();
    if (banner) {
      cls += ` ${banner.cls}`;
      html = `<span class="mk-seg mk-msg">${esc(banner.text)}</span>`;
    } else {
      // The score is always FOR A SIDE — the arrow says which — because a bear
      // tape is a tailwind to a short and reading one number two ways is how a
      // trader talks themselves into anything.
      const side = S.trade ? S.trade.side : LONG;
      const sc = scoreFor(st, side);
      const pct = compositePct([sc]);
      const sec = st.sector;
      const idx = (sym) => `${sym} ${glyph(st.indices[sym]?.d)}${glyph(st.indices[sym]?.w)}`;
      html =
        seg(
          `mk-score ${scoreBand(pct)}`,
          `Market tailwinds for a ${side}: ${sc.trend ?? "–"} trend + ${sc.sector ?? "–"} sector` +
            `${sc.vix ? ` ${sc.vix} VIX` : ""} = ${sc.total}/${sc.max}` +
            `${pct == null ? "" : ` (${Math.round(pct)}%)`}`,
          `MKT ${recap ? "@ENTRY " : ""}${side === SHORT ? "▼" : "▲"}${sc.total}/${sc.max}` +
            `${recap && S.penalty ? ` −${S.penalty}` : ""}`
        ) +
        // SPY is never the segment that gets dropped: it is the one the score
        // reads, so QQQ and IWM travel in their own, droppable, segment.
        seg("", TREND_TITLE, idx(BENCHMARK)) +
        seg("mk-opt", TREND_TITLE, INDICES.filter((sym) => sym !== BENCHMARK).map(idx).join(" ")) +
        (sec.unmapped
          ? seg("mk-unmapped", UNMAPPED_TITLE, "⚠ SECTOR ? · BENCH SPY")
          : seg(
              "",
              `${sec.name} over 20 sessions: rank ${sec.rank}/${sec.of} ` +
                `(${fmtPct(sec.ret ?? 0)}). 5-day rank ${sec.rank5 ?? "–"}, ` +
                `1-day rank ${sec.rank1 ?? "–"}.`,
              `${sec.etf} #${sec.rank ?? "?"}/${sec.of} ${glyph(bandTrend(sec.band))}`
            )) +
        (st.rs == null
          ? ""
          : seg(
              st.rs >= 0 ? "mk-bull" : "mk-bear",
              `20-day relative strength against SPY: the stock's RS line, ` +
                `${st.rs >= 0 ? "up" : "down"} ${Math.abs(st.rs).toFixed(2)}% over the window.`,
              `RS ${st.rs >= 0 ? "+" : ""}${st.rs.toFixed(1)}%`
            )) +
        (st.vix == null
          ? ""
          : seg(
              `mk-opt2 ${st.vix > VIX_SPIKE ? "mk-bear" : ""}`,
              `CBOE volatility index. Above ${VIX_SPIKE} the score takes a ` +
                `${VIX_PENALTY}-point systemic-risk haircut.`,
              `VIX ${st.vix.toFixed(1)}${st.vix > VIX_SPIKE ? ` −${VIX_PENALTY}` : ""}`
            ));
    }
  }

  el.className = cls;
  el.innerHTML = html + modeButton();
  wire("mk-mode", toggleRules);
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
    // Strict Mode speaks the same language an illegal stop does: the button
    // goes dead and the strip says why.
    const gl = gateFor(LONG);
    const gs = gateFor(SHORT);
    html =
      button(
        "act-buy",
        S.armed === LONG ? "BUY ANYWAY" : "BUY",
        "sim-btn-buy",
        !stopAllows(LONG, S.stop, close) || gl.blocked
      ) +
      // Between the two entries and the discard, because that is what it is:
      // not taking the trade, but not throwing the hand away either.
      button("act-wait", "WAIT 1D", "sim-btn-wait", !canWait()) +
      button("act-pass", "PASS", "sim-btn-pass") +
      button(
        "act-short",
        S.armed === SHORT ? "SHORT ANYWAY" : "SHORT",
        "sim-btn-short",
        !stopAllows(SHORT, S.stop, close) || gs.blocked
      );
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
  wire("act-wait", waitDay);
  wire("act-pass", pass);
  wire("act-next", advanceDay);
  wire("act-be", stopToBreakeven);
  wire("act-half", () => takeExit(0.5));
  wire("act-all", () => takeExit(1));
  wire("act-new", () => newSession());
}

function wire(id, fn) {
  const b = document.getElementById(id);
  if (b) b.addEventListener("click", fn);
}

/* ---------- render: chart ---------- */

const PAD = { l: 2, r: 46, t: 4, b: 2 };
const GAP = 5;
const FORWARD_SLOTS = 8; // empty slots kept to the right of the last bar
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

// Pattern labels carry an ampersand ("H&S"), and the chart is assembled as a
// string and assigned to innerHTML, so text content has to be escaped.
const esc = (str) => String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const text = (x, y, str, cls, anchor = "start") =>
  `<text class="${cls}" x="${x.toFixed(1)}" y="${y.toFixed(
    1
  )}" text-anchor="${anchor}">${esc(str)}</text>`;

function polyline(pts, cls, clip) {
  if (pts.length < 2) return "";
  return `<polyline class="${cls}" ${clip ? `clip-path="url(#${clip})" ` : ""}points="${pts
    .map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ")}"/>`;
}

/**
 * Is the pattern's claim still live? A failed, expired or abandoned pattern
 * draws no zone and no target: the claim is dead, and a band still hanging
 * there would be a lie. A confirmed one keeps its zone, dimmed by the CSS —
 * the expectation was met and the reader should see where.
 */
const zoneLive = (p) =>
  p.zoneNear != null &&
  ["forming", "broken-out", "throwback", "confirmed"].includes(p.state);

/**
 * The pattern's shape, fill, forecast zone and breakout mark, as SVG.
 *
 * The page module knows nothing about what any pattern MEANS: `p.shape` is a
 * drawing instruction and `p.bias` and `p.state` are class names. Adding a
 * pattern to the catalogue never touches this function.
 */
function patternArt(p, g) {
  const { W, from, to, cx, yPrice, slot, bodyW, P, lo, hi } = g;
  const bias = `sim-pat-${p.bias}`;
  const state = `sim-pat-${p.state}`;
  const clip = ` clip-path="url(#sim-clip-pat)"`;
  const sh = p.shape;
  let out = "";

  // A shape may begin off the left of the window; the clip cuts it there.
  const i0 = Math.max(sh.x0, from - 1);
  const i1 = Math.min(sh.x1 ?? to, to);

  if (sh.kind === "level") {
    const y0 = yPrice(sh.level + sh.band);
    const y1 = yPrice(sh.level - sh.band);
    out += `<rect class="sim-pat-band ${bias} ${state}"${clip} x="${PAD.l}" y="${y0.toFixed(
      1
    )}" width="${(W - PAD.r - PAD.l).toFixed(1)}" height="${Math.max(2, y1 - y0).toFixed(1)}"/>`;
    out += line(PAD.l, yPrice(sh.level), W - PAD.r, yPrice(sh.level), `sim-pat-line ${bias} ${state}`);
  } else if (sh.kind === "box") {
    // A tier-2 candlestick: a bracket round the candles, never a fill. On this
    // dark ground a filled box would muddy the very bars it is pointing at.
    const x0 = cx(sh.x0) - bodyW / 2 - 3;
    const x1 = cx(sh.x1) + bodyW / 2 + 3;
    const y0 = yPrice(sh.hi) - 4;
    const y1 = yPrice(sh.lo) + 4;
    out += `<rect class="sim-pat-box ${bias} ${state}"${clip} x="${x0.toFixed(1)}" y="${y0.toFixed(
      1
    )}" width="${Math.max(3, x1 - x0).toFixed(1)}" height="${Math.max(3, y1 - y0).toFixed(
      1
    )}" rx="2"/>`;
  } else if (i1 > i0) {
    const xs = [cx(i0), cx(i1)];
    const ys = sh.lines.map((ln) => [yPrice(lineAt(ln, i0)), yPrice(lineAt(ln, i1))]);
    if (ys.length === 2) {
      out += `<polygon class="sim-pat-fill ${bias} ${state}"${clip} points="${xs[0].toFixed(
        1
      )},${ys[0][0].toFixed(1)} ${xs[1].toFixed(1)},${ys[0][1].toFixed(1)} ${xs[1].toFixed(
        1
      )},${ys[1][1].toFixed(1)} ${xs[0].toFixed(1)},${ys[1][0].toFixed(1)}"/>`;
    }
    for (const y of ys) {
      out += polyline(
        [
          [xs[0], y[0]],
          [xs[1], y[1]],
        ],
        `sim-pat-line ${bias} ${state}`,
        "sim-clip-pat"
      );
    }
  }

  // The defining pivots, so a head-and-shoulders reads as a shape and not as
  // two stray lines, and a flag reads as sitting on top of a pole.
  if (sh.path) {
    out += polyline(
      sh.path.map(([i, v]) => [cx(i), yPrice(v)]),
      `sim-pat-path ${bias} ${state}`,
      "sim-clip-pat"
    );
  }

  // The forecast zone, bounded by Bulkowski's statistical target and the
  // textbook measured move, and time-boxed to the pattern's own length. This
  // is what the forward gutter exists for.
  if (zoneLive(p) && p.zoneUntil != null) {
    const zx0 = cx(p.endIdx) + slot / 2;
    const zx1 = Math.min(W - PAD.r, cx(p.zoneUntil));
    const zy0 = yPrice(Math.max(p.zoneNear, p.zoneFar));
    const zy1 = yPrice(Math.min(p.zoneNear, p.zoneFar));
    if (zx1 > zx0) {
      out += `<rect class="sim-pat-zone ${bias} ${state}"${clip} x="${zx0.toFixed(
        1
      )}" y="${zy0.toFixed(1)}" width="${(zx1 - zx0).toFixed(1)}" height="${Math.max(
        2,
        zy1 - zy0
      ).toFixed(1)}" rx="2"/>`;
    }
  }

  // One tick on the trigger, at the bar that took it out.
  if (p.breakoutIdx != null && p.breakoutIdx >= from && p.breakoutIdx <= to) {
    const bx = cx(p.breakoutIdx);
    const by = yPrice(p.trigger);
    out += line(bx, by - 5, bx, by + 5, `sim-pat-brk ${bias} ${state}`);
  }

  return out;
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
  // Reserved future space. A forecast zone projects forward in time and in
  // `decide` mode the last bar IS the right edge, so without a gutter there is
  // nowhere to draw one. It is unconditional — applied whether or not this
  // deal has a pattern — because a candle width that jumped between deals
  // would be a worse tell than the gutter costs. Candles narrow by ~18%, which
  // bodyW's existing clamp absorbs.
  const slot = plotW / (n + FORWARD_SLOTS);
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
  )}" width="${W}" height="${P.h.toFixed(1)}"/></clipPath>`;
  // A second clip for the pattern art. A shape may start before the visible
  // window — detection reads further back than the chart shows — so unlike the
  // price clip this one has to cut horizontally too, at the plot's own edges.
  out += `<clipPath id="sim-clip-pat"><rect x="${PAD.l}" y="${P.top.toFixed(
    1
  )}" width="${plotW.toFixed(1)}" height="${P.h.toFixed(1)}"/></clipPath></defs>`;

  // ---- price grid + right-hand axis ----
  const stopY0 = yPrice(liveStop());
  for (let g = 0; g <= 3; g++) {
    const v = lo + ((hi - lo) * g) / 3;
    const gy = yPrice(v);
    out += line(PAD.l, gy, W - PAD.r, gy, "sim-grid");
    // The stop's own tag wins the gutter where the two would collide.
    if (Math.abs(gy - stopY0) > 9) out += text(W - PAD.r + 4, gy + 3, fmtPx(v), "sim-axis");
  }

  // ---- chart pattern: the shape, its zone and the breakout mark ----
  // Emitted after the grid and before the averages, so candles and lines draw
  // on top of it. Everything here is guarded on S.pattern: null renders as
  // nothing at all, which is the common case.
  if (S.pattern) {
    out += patternArt(S.pattern, { W, from, to, cx, yPrice, slot, bodyW, P, lo, hi });
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
  // of letting the clip hide it silently. Right-anchored at the top, beside
  // the price axis where the other numbers live — on the left it overprinted
  // the 9EMA/22EMA/200SMA legend whenever the average sat above the window.
  const s200 = S.ind.s200[to];
  if (s200 != null && (s200 > hi || s200 < lo)) {
    const away = ((s200 - bars[to].c) / bars[to].c) * 100;
    out += text(
      W - PAD.r - 3,
      P.top + 9,
      `200SMA ${s200 > hi ? "▲" : "▼"} ${fmtPx(s200)} (${fmtPct(away)})`,
      "sim-ma-off",
      "end"
    );
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
    // At the FOOT of the price panel. The divider used to sit hard against the
    // right edge, where a label at the top was out of everything's way; the
    // forward gutter moved it inboard, into the corner the pattern's target
    // readout now uses.
    out += text(dx - 3, P.bot - 3, "DECISION", "sim-dlabel", "end");
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

  // ---- chart pattern: the label ----
  // Second row of the top-left corner, under the MA legend. The top-RIGHT
  // corner cannot hold it: the forward gutter moved the decision divider eight
  // slots in from the right edge, so its label now sits in the middle of that
  // corner and a right-anchored pattern name would run straight through it.
  if (S.pattern) {
    const p = S.pattern;
    out += text(
      PAD.l + 3,
      P.top + 20,
      patternText(p, W < 340),
      `sim-pat-label sim-pat-${p.bias} sim-pat-${p.state}`
    );
    // A measured move often lands outside the visible range. The zone bounds
    // are deliberately NOT in consider() — squashing every candle to fit a
    // hypothesis is the wrong trade — so say where the target is instead, the
    // same way the off-scale 200SMA does.
    if (zoneLive(p) && p.zoneFar != null && (p.zoneFar > hi || p.zoneFar < lo)) {
      const up = p.zoneFar > hi;
      out += text(
        W - PAD.r - 3,
        P.top + 20,
        `TGT ${up ? "▲" : "▼"} ${fmtPx(p.zoneNear)}–${fmtPx(p.zoneFar)}`,
        `sim-pat-tgt-text sim-pat-${p.bias}`,
        "end"
      );
    }
  }

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
  // One hook covers every way the tape moves — taking a position, +1 DAY, and
  // PASS's twenty-session jump. resolvePattern is idempotent and terminal
  // states short-circuit, so calling it on every render costs nothing.
  // paintStop() deliberately does NOT call render(), which is what keeps
  // dragging the stop from disturbing the annotation.
  S.pattern = resolvePattern(S.pattern, S.bars, S.curIdx);
  // One read of the market per render, shared by the strip, the gate on the
  // buttons and the recap chip. Cheap (two array lookups and eleven returns)
  // but not free, and paintStop() re-renders the chips on every drag frame.
  S.mkt = marketAt(shownIdx());
  // Every band is laid out before the chart measures itself: the chart takes
  // the height they leave over, so drawing it first would size it against a
  // stale (taller) box and push the RSI panel under the action bar.
  renderStatus();
  renderMarket();
  renderActions();
  renderChart();
}

/* ---------- keyboard (desktop convenience) ---------- */

document.addEventListener("keydown", (ev) => {
  if (!S) return;
  const key = ev.key.toLowerCase();
  const hit = {
    decide: {
      b: () => takePosition(LONG),
      s: () => takePosition(SHORT),
      w: waitDay,
      p: pass,
    },
    trade: {
      n: advanceDay,
      e: stopToBreakeven,
      h: () => takeExit(0.5),
      x: () => takeExit(1),
    },
    // Deliberately NOT "n": holding the advance key through a close would
    // skip straight past the recap, which is the part worth reading.
    review: { enter: () => newSession(), d: () => newSession() },
    recap: { enter: () => newSession(), d: () => newSession() },
  }[S.mode];
  const fn = hit && hit[key];
  if (!fn) return;
  // A disabled button means an illegal move; the keyboard must respect it too.
  if (S.mode === "decide" && key === "b" && !stopAllows(LONG, S.stop, S.bars[S.dIdx].c)) return;
  if (S.mode === "decide" && key === "s" && !stopAllows(SHORT, S.stop, S.bars[S.dIdx].c)) return;
  if (S.mode === "decide" && key === "w" && !canWait()) return;
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
// The market feed is fetched alongside the universe, never in front of it: it
// resolves either way (loadMarket swallows its own errors) so a dead
// sim-market.json costs the strip, not the hand.
Promise.all([loadUniverse(), loadMarket()])
  .then(() => newSession())
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
  wait: waitDay,
  pattern: () => S && S.pattern,
  market: () => S && S.mkt,
  rules: () => rules,
  setRules: (v) => {
    if (v !== rules) toggleRules();
  },
};
