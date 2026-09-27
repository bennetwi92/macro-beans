// Unit tests for the weekly review's book-level modules: fundamental grades
// (fundamental-score.js), the TAPE's risk budget (tape.js), and portfolio
// construction (construct.js).
//
// The load-bearing ones:
//   * sizing is risk-first — size falls out of the stop distance, and no
//     order may take the book past its heat cap, its cash, or a concentration
//     cap;
//   * exits free cash BEFORE anything is bought;
//   * the fundamentals are ranked WITHIN sector, and a loss-maker's P/E is
//     the worst value, not the cheapest.

import assert from "node:assert/strict";
import test from "node:test";

import { percentiles, gradeFundamentals } from "../../web/v2/js/fundamental-score.js";
import { budgetFor, breadthSeries, breadthAt, BUDGETS, BREADTH_FULL, BREADTH_DEFENSIVE } from "../../web/v2/js/tape.js";
import { construct, riskShare, openRiskGBP, correlation, manageHolding, CAPS } from "../../web/v2/js/construct.js";
import { prepareSeries } from "../../web/v2/js/strategy.js";
import { barsFromCloses, ramp } from "./_weekly-bars.js";

/* ---------- fundamentals ---------- */

test("percentiles: 0..100, ties averaged, nulls skipped", () => {
  assert.deepEqual(percentiles([10, null, 30, 20]), [0, null, 100, 50]);
  assert.deepEqual(percentiles([5, 5, 9]), [25, 25, 100]);
});

test("fundamentals: ranked within sector, so a bank is compared with banks", () => {
  const rows = {};
  const sector = {};
  for (let i = 0; i < 6; i++) {
    rows[`B${i}`] = { forwardPE: 8 + i, priceToBook: 1 + i / 10, returnOnAssets: 0.01 + i / 1000, operatingMargins: 0.3, revenueGrowth: 0.05 };
    sector[`B${i}`] = "Financials";
    rows[`T${i}`] = { forwardPE: 30 + i, priceToBook: 10 + i, returnOnAssets: 0.1 + i / 100, operatingMargins: 0.3, revenueGrowth: 0.2 };
    sector[`T${i}`] = "Information Technology";
  }
  const g = gradeFundamentals(rows, (t) => sector[t]);
  // The cheapest tech name is as "cheap" within tech as the cheapest bank is within banks.
  assert.equal(g.T0.value, g.B0.value);
  assert.ok(g.T0.value > g.T5.value);
});

test("fundamentals: a negative P/E is the worst value, not the cheapest", () => {
  const rows = {};
  for (let i = 0; i < 6; i++) rows[`X${i}`] = { forwardPE: 10 + i, priceToBook: 2, enterpriseToEbitda: 8 };
  rows.LOSS = { forwardPE: -5, priceToBook: 2, enterpriseToEbitda: 8 };
  const g = gradeFundamentals(rows, () => "S");
  const loss = g.LOSS.detail.earningsYield;
  assert.equal(loss, 0, "lowest earnings yield in the sector");
});

test("fundamentals: too few metrics is no grade, not a grade built from one number", () => {
  const rows = { A: { revenueGrowth: 0.1 }, B: { revenueGrowth: 0.2 }, C: { revenueGrowth: 0.3 }, D: { revenueGrowth: 0 }, E: { revenueGrowth: 0.4 } };
  const g = gradeFundamentals(rows, () => "S");
  assert.equal(g.A.quality, null);
});

/* ---------- the tape ---------- */

test("budget: FULL needs a bull tape AND breadth; DEFENSIVE on a bear tape OR thin breadth", () => {
  assert.equal(budgetFor({ regime: "bull", stage2: BREADTH_FULL + 1, vix: 15 }).level, "FULL");
  assert.equal(budgetFor({ regime: "bull", stage2: BREADTH_DEFENSIVE - 1, vix: 15 }).level, "DEFENSIVE", "a narrow market led by a few names");
  assert.equal(budgetFor({ regime: "bear", stage2: 60, vix: 15 }).level, "DEFENSIVE");
  assert.equal(budgetFor({ regime: "neutral", stage2: 50, vix: 15 }).level, "HALF");
});

test("budget: a VIX spike steps it down one level; no reading at all is the middle", () => {
  assert.equal(budgetFor({ regime: "bull", stage2: 60, vix: 35 }).level, "HALF");
  assert.equal(budgetFor({}).level, "HALF");
  assert.ok(BUDGETS.FULL.riskPct > BUDGETS.HALF.riskPct && BUDGETS.HALF.riskPct > BUDGETS.DEFENSIVE.riskPct);
});

test("breadth: share of names in Stage 2 per week, read as of", () => {
  const up = prepareSeries(barsFromCloses(ramp(500, 50, 0.002)));
  const dn = prepareSeries(barsFromCloses(ramp(500, 200, -0.002)));
  const many = [...Array(30).fill(up), ...Array(30).fill(dn)];
  const b = breadthSeries(many);
  const last = b.stage2[b.stage2.length - 1];
  assert.equal(last, 50);
  assert.equal(breadthAt(b, "1990-01-01"), null);
  assert.equal(breadthAt(b, "2099-01-01").stage2, last);
});

/* ---------- construction ---------- */

const FULL = { ...BUDGETS.FULL };

test("sizing is risk-first: qty = risk ÷ (entry − stop)", () => {
  const { orders } = construct({
    equityGBP: 10000,
    cashGBP: 10000,
    candidates: [{ t: "A", total: 85, setup: "PULLBACK", sector: "X", entry: 100, stop: 95 }],
    budget: FULL,
  });
  const o = orders[0];
  assert.equal(o.action, "BUY");
  // 1% of 10k at full conviction = £100 at risk; £5 a share of risk.
  assert.ok(Math.abs(o.qty - 20) < 1e-9);
  assert.ok(Math.abs(o.riskGBP - 100) < 1e-9);
});

test("riskShare: conviction scales the bet within a band", () => {
  assert.equal(riskShare(55), 0.6);
  assert.equal(riskShare(85), 1);
  assert.equal(riskShare(100), 1);
});

test("caps: position size, cash, heat, weekly count, sector count", () => {
  // A tight stop would size past 20% of equity: capped.
  const big = construct({ equityGBP: 10000, cashGBP: 10000, candidates: [{ t: "A", total: 90, sector: "X", entry: 100, stop: 99.5 }], budget: FULL });
  assert.ok(big.orders[0].valueGBP <= 0.2 * 10000 + 1e-6);
  // Not enough cash: capped at what is spendable.
  const poor = construct({ equityGBP: 10000, cashGBP: 500, candidates: [{ t: "A", total: 90, sector: "X", entry: 100, stop: 95 }], budget: FULL });
  assert.ok(poor.orders[0].valueGBP <= 500);
  // DEFENSIVE allows one new position a week.
  const cands = ["A", "B", "C"].map((t, i) => ({ t, total: 80 - i, sector: `S${i}`, entry: 100, stop: 90 }));
  const def = construct({ equityGBP: 10000, cashGBP: 10000, candidates: cands, budget: BUDGETS.DEFENSIVE });
  assert.equal(def.orders.filter((o) => o.action === "BUY").length, 1);
  assert.match(def.skipped[0].reason, /DEFENSIVE/);
  // Three of a sector already held: the fourth is skipped.
  const holdings = ["H1", "H2", "H3"].map((t) => ({ t, qty: 1, entryGBP: 100, stopGBP: 100, priceGBP: 100, sector: "X", action: "HOLD" }));
  const sec = construct({ equityGBP: 10000, cashGBP: 9700, holdings, candidates: [{ t: "A", total: 90, sector: "X", entry: 100, stop: 95 }], budget: FULL });
  assert.equal(sec.orders.length, 0);
  assert.match(sec.skipped[0].reason, /X names already/);
});

test("heat: no order takes open risk past the budget's cap", () => {
  const holdings = [{ t: "H", qty: 20, entryGBP: 100, stopGBP: 65, priceGBP: 100, sector: "Y", action: "HOLD" }]; // £700 at risk, 20% of equity
  const r = construct({ equityGBP: 10000, cashGBP: 8000, holdings, candidates: [{ t: "A", total: 90, sector: "X", entry: 100, stop: 95 }], budget: FULL });
  assert.ok(r.heatAfter <= (FULL.heatMax / 100) * 10000 + 1e-6);
  assert.ok(Math.abs(r.orders[0].riskGBP - 100) < 1e-6, "£800 cap − £700 held leaves £100 of room");
  assert.equal(openRiskGBP({ qty: 10, entryGBP: 100, stopGBP: 105 }), 0, "a stop past entry risks nothing");
});

test("order of work: exits free cash before anything is bought", () => {
  const holdings = [{ t: "H", qty: 50, entryGBP: 100, stopGBP: 90, priceGBP: 100, sector: "Y", action: "EXIT", reason: "thesis" }];
  const r = construct({ equityGBP: 10000, cashGBP: 0, holdings, candidates: [{ t: "A", total: 90, sector: "X", entry: 100, stop: 95 }], budget: FULL });
  assert.equal(r.orders[0].action, "EXIT");
  assert.equal(r.orders[1].action, "BUY", "funded by the exit");
});

test("RESET: an exit signal on a name that is a fresh BUY this week keeps the shares under the new stop", () => {
  const holdings = [{ t: "A", qty: 10, entryGBP: 80, stopGBP: 80, priceGBP: 100, sector: "X", action: "EXIT", reason: "trailing stop breached" }];
  const cands = [{ t: "A", total: 85, setup: "BREAKOUT", sector: "X", entry: 100, stop: 90 }];
  const r = construct({ equityGBP: 10000, cashGBP: 9000, holdings, candidates: cands, budget: FULL });
  assert.equal(r.orders[0].action, "RESET");
  assert.equal(r.orders[0].stopGBP, 90);
  assert.ok(!r.orders.some((o) => o.action === "EXIT" || o.action === "BUY"), "no sell-and-buy-back round trip");
  assert.equal(r.skipped.length, 0);
  assert.ok(Math.abs(r.heatAfter - 100) < 1e-9, "risk now measured from the price to the new stop");
  // Held far larger than the new trade's risk allows: trimmed back to it.
  const big = construct({ equityGBP: 10000, cashGBP: 5000, holdings: [{ ...holdings[0], qty: 50 }], candidates: cands, budget: FULL });
  const trim = big.orders.find((o) => o.action === "TRIM");
  assert.ok(trim && Math.abs(50 - trim.qty - 10) < 1e-9, "£100 of risk at £10 a share is 10 shares");
});

test("the trim band: only a position past trimPct is cut, and only back to maxPositionPct", () => {
  const holdings = [{ t: "H", qty: 30, entryGBP: 50, stopGBP: 60, priceGBP: 100, sector: "Y", action: "HOLD" }];
  const r = construct({ equityGBP: 10000, cashGBP: 7000, holdings, candidates: [], budget: FULL });
  const trim = r.orders.find((o) => o.action === "TRIM");
  assert.ok(trim, "30% of equity > 25% band");
  assert.ok(Math.abs((30 - trim.qty) * 100 - CAPS.maxPositionPct * 100) < 1e-6);
  const fine = construct({ equityGBP: 10000, cashGBP: 7700, holdings: [{ ...holdings[0], qty: 23 }], candidates: [], budget: FULL });
  assert.equal(fine.orders.length, 0, "23% is inside the band: winners are left alone");
});

test("correlation cap: a near-twin of a holding is skipped", () => {
  const base = Array.from({ length: 52 }, (_, i) => Math.sin(i) * 0.02);
  assert.ok(correlation(base, base) > 0.999);
  const holdings = [{ t: "H", qty: 1, entryGBP: 100, stopGBP: 100, priceGBP: 100, sector: "Y", action: "HOLD", returns: base }];
  const r = construct({ equityGBP: 10000, cashGBP: 9900, holdings, candidates: [{ t: "A", total: 90, sector: "X", entry: 100, stop: 95, returns: base }], budget: FULL });
  assert.equal(r.orders.length, 0);
  assert.match(r.skipped[0].reason, /correlated with H/);
});

test("manageHolding: derives the stop by replaying the strategy from the entry week", () => {
  const s = prepareSeries(barsFromCloses(ramp(600, 50, 0.002)));
  const at = s.bars.length - 12;
  const m = manageHolding(s, s.bars[at].d, s.bars[at].o);
  assert.equal(m.action, "HOLD");
  assert.ok(m.stop > m.initialStop, "a winner's stop has trailed up");
  assert.equal(m.entryWeek, s.bars[at - 1].d, "the decision week is the one BEFORE the first buy");
});

test("manageHolding: a holding past its time limit is an EXIT, with the reason", () => {
  const s = prepareSeries(barsFromCloses(ramp(600, 50, 0.002)));
  const m = manageHolding(s, s.bars[40].d, s.bars[40].o);
  assert.equal(m.action, "EXIT");
  assert.match(m.reason, /time exit/);
});

test("manageHolding: a holding bought under the strategy's stop is managed under the 30-week rule", () => {
  const s = prepareSeries(barsFromCloses(ramp(600, 50, 0.002)));
  const m = manageHolding(s, s.bars[40].d, 1);
  assert.equal(m.legacy, true);
});
