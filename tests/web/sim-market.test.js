// Unit tests for the simulator's market-context math (web/v2/js/sim-market.js).
//
// Two of these tests are load-bearing rather than merely useful:
//
//   * "no look-ahead" — the market read on a date must be identical whether or
//     not the future exists in the feed. A simulator that quietly consults
//     tomorrow's SPY to grade today's setup is worse than one with no market
//     context at all, because nothing on screen would say so.
//   * "fail open" — a missing feed, a missing sector, a date before the history
//     starts: each has to come back unscored, never scored zero. The gate can
//     block a trade, so the cost of getting this wrong is a rule that fires on
//     the build's own failures.

import assert from "node:assert/strict";
import test from "node:test";

import {
  BENCHMARK,
  MARKET_MAX,
  SECTOR_PTS,
  STRICT_MIN,
  TREND_PTS,
  VIX_PENALTY,
  VIX_SPIKE,
  asOf,
  compositePct,
  marketStatus,
  pctOver,
  prepareMarket,
  rankSectors,
  relStrength,
  scoreFor,
  trendAt,
} from "../../web/v2/js/sim-market.js";

/* ---------- fixtures ---------- */

// 400 consecutive weekdays from 2020-01-01: enough for a 50-week average.
function weekdays(n, start = "2020-01-01") {
  const out = [];
  const d = new Date(`${start}T00:00:00Z`);
  while (out.length < n) {
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

const N = 400;
const DATES = weekdays(N);

/** A series that rises `pctPerBar` a bar off `base`, optionally rolling over at `turn`. */
const ramp = (base, pctPerBar, turn = null) =>
  Array.from({ length: N }, (_, i) =>
    Number(
      (turn == null || i <= turn
        ? base * (1 + pctPerBar) ** i
        : base * (1 + pctPerBar) ** turn * (1 - pctPerBar * 3) ** (i - turn)
      ).toFixed(2)
    )
  );

const SECTORS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"];

/** A feed where SPY/QQQ/IWM rise and the eleven sectors fan out by rank. */
function feed(overrides = {}) {
  const close = {
    SPY: ramp(300, 0.001),
    QQQ: ramp(200, 0.0012),
    IWM: ramp(150, 0.0008),
    VIX: Array.from({ length: N }, () => 15),
  };
  // XLB is the fastest, XLY the slowest — so the 20-day ranking is stable and
  // known: rank 1 = XLB, rank 11 = XLY.
  SECTORS.forEach((etf, k) => {
    close[etf] = ramp(100, 0.002 - k * 0.0003);
  });
  return prepareMarket({
    built_at: "2026-01-01T00:00:00Z",
    dates: DATES,
    close: { ...close, ...(overrides.close || {}) },
    sectors: Object.fromEntries(
      SECTORS.map((etf, k) => [`Sector ${k}`, etf])
    ),
    ...overrides.top,
  });
}

const M = feed();
const LAST = N - 1;
const SECTOR_OF = Object.fromEntries(SECTORS.map((etf, k) => [etf, `Sector ${k}`]));

/* ---------- date resolution ---------- */

test("asOf: resolves backwards to the last session, never forwards", () => {
  assert.equal(asOf(DATES, DATES[10]), 10);
  // A Sunday resolves to the Friday before it, not the Monday after.
  const sunday = "2020-01-12";
  assert.equal(DATES[asOf(DATES, sunday)], "2020-01-10");
  // Before the history there is nothing to report.
  assert.equal(asOf(DATES, "2019-06-01"), -1);
  // After it, the last session — the feed simply has not caught up.
  assert.equal(asOf(DATES, "2099-01-01"), N - 1);
});

/* ---------- trend states ---------- */

test("trendAt: the three states, daily and weekly", () => {
  const rising = ramp(100, 0.002);
  const t = feed({ close: { SPY: rising } }).trend.SPY;
  assert.equal(trendAt(t, rising, LAST, "d"), "bull");
  assert.equal(trendAt(t, rising, LAST, "w"), "bull");

  // A hard roll-over: price ends far under the 50-day.
  const falling = ramp(100, 0.002, 300);
  const tf = feed({ close: { SPY: falling } }).trend.SPY;
  assert.equal(trendAt(tf, falling, LAST, "d"), "bear");

  // Undefined before the averages exist, whatever the shape.
  assert.equal(trendAt(t, rising, 5, "d"), null);
  assert.equal(trendAt(t, rising, 5, "w"), null);
});

test("trendAt: above the 50SMA but with the averages crossed is neutral, not bull", () => {
  // Rise, roll over enough to pull the 21EMA under the 50SMA, then pop back up
  // above both. Price > both averages, but 21EMA < 50SMA — not an uptrend.
  const closes = Array.from({ length: N }, (_, i) => (i < 300 ? 100 + i * 0.2 : 160 - (i - 300) * 0.5));
  closes[LAST] = 200; // one spike above everything
  const t = feed({ close: { SPY: closes } }).trend.SPY;
  const state = trendAt(t, closes, LAST, "d");
  assert.ok(closes[LAST] > t.sma[LAST], "the spike is above the 50SMA");
  assert.ok(t.ema[LAST] < t.sma[LAST], "but the averages are crossed the wrong way");
  assert.equal(state, "neutral");
});

test("trendAt: the running week closes on today, not on Friday", () => {
  // Two feeds identical up to a Wednesday; one continues into a crash. The
  // weekly read on that Wednesday must be the same in both.
  const base = ramp(100, 0.002);
  const crashed = base.slice();
  for (let i = 350; i < N; i++) crashed[i] = 10;
  const wed = 349;
  const a = feed({ close: { SPY: base } });
  const b = feed({ close: { SPY: crashed } });
  assert.equal(trendAt(a.trend.SPY, base, wed, "w"), trendAt(b.trend.SPY, crashed, wed, "w"));
});

/* ---------- relative strength + sector ranking ---------- */

test("pctOver / relStrength: RS is the stock's edge over the benchmark", () => {
  const bench = Array.from({ length: 30 }, (_, i) => 100 * 1.01 ** i);
  const leader = Array.from({ length: 30 }, (_, i) => 50 * 1.02 ** i);
  const clone = bench.map((v) => v * 3);

  assert.ok(Math.abs(pctOver(bench, 29, 20) - (1.01 ** 20 - 1) * 100) < 1e-9);
  // A stock that moves exactly with the market has zero relative strength,
  // whatever its price level.
  assert.ok(Math.abs(relStrength(clone, 29, bench, 29, 20)) < 1e-9);
  // A stock compounding faster leads.
  assert.ok(relStrength(leader, 29, bench, 29, 20) > 0);
  // Not enough history is a null, not a zero.
  assert.equal(relStrength(leader, 5, bench, 5, 20), null);
});

test("rankSectors: best first, banded top 3 / middle / bottom 3", () => {
  const rows = rankSectors(M, LAST, 20);
  assert.equal(rows.length, 11);
  assert.equal(rows[0].etf, "XLB");
  assert.equal(rows[10].etf, "XLY");
  assert.deepEqual(rows.map((r) => r.rank), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
  assert.deepEqual(
    rows.filter((r) => r.band === "top").map((r) => r.etf),
    ["XLB", "XLC", "XLE"]
  );
  assert.equal(rows.filter((r) => r.band === "mid").length, 5);
  assert.deepEqual(
    rows.filter((r) => r.band === "bottom").map((r) => r.etf),
    ["XLU", "XLV", "XLY"]
  );
  // Returns are monotonically non-increasing down the table.
  for (let i = 1; i < rows.length; i++) assert.ok(rows[i - 1].ret >= rows[i].ret);
});

/* ---------- scoring ---------- */

test("scoreFor: the 35-point allocation, for a long", () => {
  const top = marketStatus(M, { sector: SECTOR_OF.XLB, date: DATES[LAST] });
  assert.equal(top.regime, "bull");
  assert.equal(top.sector.band, "top");
  assert.equal(top.score.trend, TREND_PTS.bull);
  assert.equal(top.score.sector, SECTOR_PTS.top);
  assert.equal(top.score.total, MARKET_MAX);
  assert.equal(compositePct([top.score]), 100);

  const mid = marketStatus(M, { sector: SECTOR_OF.XLI, date: DATES[LAST] });
  assert.equal(mid.sector.band, "mid");
  assert.equal(mid.score.total, TREND_PTS.bull + SECTOR_PTS.mid);

  const bottom = marketStatus(M, { sector: SECTOR_OF.XLY, date: DATES[LAST] });
  assert.equal(bottom.score.total, TREND_PTS.bull + SECTOR_PTS.bottom);
});

test("scoreFor: the short side is the mirror, and the VIX haircut is not", () => {
  const st = marketStatus(M, { sector: SECTOR_OF.XLB, date: DATES[LAST] });
  // Bull tape + leading sector: everything a long wants and a short does not.
  assert.equal(scoreFor(st, "long").total, MARKET_MAX);
  assert.equal(scoreFor(st, "short").total, 0);

  const spike = feed({ close: { VIX: Array.from({ length: N }, () => VIX_SPIKE + 5) } });
  const hot = marketStatus(spike, { sector: SECTOR_OF.XLB, date: DATES[LAST] });
  assert.equal(hot.vix, VIX_SPIKE + 5);
  // The penalty lands on both sides — a volatility spike is nobody's tailwind.
  assert.equal(scoreFor(hot, "long").total, MARKET_MAX - VIX_PENALTY);
  assert.equal(scoreFor(hot, "short").vix, -VIX_PENALTY);
  // ...and never drags a score below zero.
  assert.equal(scoreFor(hot, "short").total, 0);
});

test("compositePct: an unavailable block leaves the fraction, it does not fail it", () => {
  assert.equal(compositePct([{ total: 20, max: 35, available: true }]), (20 / 35) * 100);
  assert.equal(compositePct([{ available: false, total: 0, max: 35 }]), null);
  // A second block slots in without touching the gate: 35 of 70 is 50%.
  assert.equal(
    compositePct([
      { total: 35, max: 35, available: true },
      { total: 0, max: 35, available: true },
    ]),
    50
  );
});

/* ---------- the edge cases the story names ---------- */

test("fail open: no feed, no date, no sector — unscored, never zero", () => {
  assert.equal(prepareMarket(null), null);
  assert.equal(prepareMarket({ dates: [], close: {} }), null);
  assert.equal(prepareMarket({ dates: DATES, close: { QQQ: [] } }), null); // no benchmark

  assert.equal(marketStatus(null, { sector: "x", date: DATES[LAST] }).available, false);
  assert.equal(marketStatus(M, { sector: "x", date: "2019-01-01" }).available, false);
  assert.equal(compositePct([scoreFor({ available: false }, "long")]), null);

  // An unmapped ticker benchmarks against SPY, is flagged, and its sector
  // points drop out of BOTH sides of the composite rather than scoring zero.
  const un = marketStatus(M, { sector: "Cryptocurrency Mining", date: DATES[LAST] });
  assert.equal(un.available, true);
  assert.equal(un.sector.unmapped, true);
  assert.equal(un.sector.etf, BENCHMARK);
  assert.equal(un.score.sector, null);
  assert.equal(un.score.max, TREND_PTS.bull);
  assert.equal(un.score.total, TREND_PTS.bull);
  assert.equal(compositePct([un.score]), 100);
});

test("no look-ahead: the read on a date cannot depend on what came after it", () => {
  const cut = 320;
  const full = feed();
  // The same feed with everything after `cut` deleted.
  const truncated = prepareMarket({
    built_at: "x",
    dates: DATES.slice(0, cut + 1),
    close: Object.fromEntries(
      Object.entries(full.close).map(([k, v]) => [k, v.slice(0, cut + 1)])
    ),
    sectors: Object.fromEntries(SECTORS.map((etf, k) => [`Sector ${k}`, etf])),
  });
  const stock = { closes: ramp(50, 0.0015), index: cut };

  for (const etf of ["XLB", "XLI", "XLY"]) {
    const a = marketStatus(full, { sector: SECTOR_OF[etf], date: DATES[cut], stock });
    const b = marketStatus(truncated, {
      sector: SECTOR_OF[etf],
      date: DATES[cut],
      stock: { closes: stock.closes.slice(0, cut + 1), index: cut },
    });
    assert.deepEqual(b, a, `${etf}: the market read leaked a future session`);
  }
});

test("the gate: a counter-trend long lands under the strict threshold", () => {
  // A bear tape is the case the warning exists for. Even a top-ranked sector
  // (15 of 35 = 43%) cannot carry a long over the 75% gate on its own.
  const falling = ramp(300, 0.002, 250);
  const bear = feed({ close: { SPY: falling } });
  const st = marketStatus(bear, { sector: SECTOR_OF.XLB, date: DATES[LAST] });
  assert.equal(st.regime, "bear");
  const long = scoreFor(st, "long");
  assert.equal(long.trend, TREND_PTS.bear);
  assert.ok(compositePct([long]) < STRICT_MIN, "a counter-trend long is under the gate");
  // The same tape is a tailwind to a short.
  assert.equal(scoreFor(st, "short").trend, TREND_PTS.bull);
});

test("a leading gap is no reading at all, not a quiet neutral", () => {
  // An index that listed after the window starts arrives with leading nulls
  // (build_sim_market.py reindexes onto SPY's calendar). Every comparison
  // against null is false, so an unguarded implementation returns "neutral" —
  // a reading, on a day there was no price.
  const late = ramp(100, 0.001);
  for (let i = 0; i < 200; i++) late[i] = null;
  const t = feed({ close: { QQQ: late } }).trend.QQQ;
  assert.equal(trendAt(t, late, 100, "d"), null);
  assert.equal(trendAt(t, late, 100, "w"), null);
  assert.ok(trendAt(t, late, N - 1, "d") !== null, "and it reads normally once it has history");

  // The same holds through marketStatus: a sector ETF with no return at this
  // bar simply drops out of the ranking rather than ranking last.
  const holed = feed({ close: { XLB: late } });
  const rows = rankSectors(holed, 100, 20);
  assert.ok(!rows.some((r) => r.etf === "XLB"));
  assert.equal(rows.length, 10);
  // ...and the bands still split 3 / 4 / 3 over the ten that remain.
  assert.equal(rows.filter((r) => r.band === "top").length, 3);
  assert.equal(rows.filter((r) => r.band === "bottom").length, 3);
});
