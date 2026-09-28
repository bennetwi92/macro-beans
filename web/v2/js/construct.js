// Portfolio construction: from this week's scorecards and the real book to a
// list of ORDERS. Pure functions: no DOM, no fetch. Covered by
// tests/web/weekly-book.test.js.
//
// Spec: docs/web_v2/scorecard_strategy_spec.md §5. The book is a small cash
// ISA: long-only, no margin, fractional shares, GBP base, US names bought in
// USD. The order of a week's work is fixed, because the order is the policy:
//
//   1. EXIT what the rules say is over (stop breached, thesis broken, time).
//      This frees cash and heat before anything is bought. A name the rules
//      say to exit that is ALSO a fresh BUY this week is a RESET instead:
//      kept, and re-underwritten under the new trade's stop.
//   2. TRAIL the stops the rules have ratcheted up.
//   3. TRIM a position that has grown past TRIM_PCT of equity back to
//      MAX_POSITION_PCT. That is the ONLY rebalancing: winners are otherwise
//      left alone. The repo's own rebalancing study (docs/rebalancing/report.md)
//      found that trading more often does not pay and a threshold band beats a
//      calendar; a concentration band is that finding applied to a stock book.
//   4. BUY in score order, each position sized from its stop — risk first:
//      size = (equity × risk%) ÷ (entry − stop) — until the week's budget, the
//      heat cap, cash, or a concentration cap says stop.
//
// Cash is a position. A week in which nothing qualifies produces no BUYs and
// that is a result, not a failure.

import { runTrade, weekAsOf } from "./strategy.js";

/** Structural caps. Assumptions for a ~£10k ISA; see the spec §5. */
export const CAPS = Object.freeze({
  maxPositions: 10,
  maxPositionPct: 20, // entry value, % of equity
  trimPct: 25, // a holding above this is trimmed back to maxPositionPct
  maxPerSector: 3,
  maxCorr: 0.85, // 52-week weekly-return correlation with any holding
  minOrderGBP: 100,
});

/** Trading 212 ISA: no commission; 0.15% FX conversion each way on USD names. */
export const COSTS = Object.freeze({ fxPct: 0.15 });

/**
 * Score → share of the budget's per-trade risk. The headline only modulates
 * size within a band: 55 (the minimum for a BUY) risks 60% of a full unit,
 * 85 and above the full unit. Conviction scales the bet; it never replaces the
 * stop as the thing that sizes it.
 */
export function riskShare(score) {
  if (score == null) return 0.6;
  return Math.max(0.6, Math.min(1, 0.6 + ((score - 55) / 30) * 0.4));
}

/** Capital at risk in a holding, GBP: entry to stop, floored at zero once the stop is past entry. */
export function openRiskGBP(h) {
  return Math.max(0, (h.entryGBP - h.stopGBP) * h.qty);
}

/** Pearson correlation of two equal-length arrays (null if degenerate). */
export function correlation(a, b) {
  const n = Math.min(a?.length ?? 0, b?.length ?? 0);
  if (n < 20) return null;
  let sa = 0;
  let sb = 0;
  for (let i = 0; i < n; i++) {
    sa += a[a.length - n + i];
    sb += b[b.length - n + i];
  }
  const ma = sa / n;
  const mb = sb / n;
  let cov = 0;
  let va = 0;
  let vb = 0;
  for (let i = 0; i < n; i++) {
    const x = a[a.length - n + i] - ma;
    const y = b[b.length - n + i] - mb;
    cov += x * y;
    va += x * x;
    vb += y * y;
  }
  return va > 0 && vb > 0 ? cov / Math.sqrt(va * vb) : null;
}

/** Weekly log returns over the last `n` completed weeks up to `w` (for correlation). */
export function weeklyReturns(s, w, n = 52) {
  const out = [];
  for (let k = Math.max(1, w - n + 1); k <= w; k++) {
    const a = s.closes[k - 1];
    const b = s.closes[k];
    out.push(a > 0 && b > 0 ? Math.log(b / a) : 0);
  }
  return out;
}

/**
 * What the rules say about a REAL holding, by replaying the strategy's own
 * trade from the week before it was bought, at its actual average cost:
 *
 *   {action: "EXIT"|"HOLD", stop, initialStop, reason, r, weeks, entryWeek}
 *
 * The stop is DERIVED, not stored — the strategy's stop for that entry,
 * trailed by the strategy's rules to this week. If the replay says the stop
 * was breached, the answer is EXIT whatever the price is now: either a resting
 * order already did it, or it should have.
 *
 * `entryIso` is the first buy date of the open position; `avgCost` in the
 * stock's own currency. Returns null for a name with no series.
 */
export function manageHolding(s, entryIso, avgCost) {
  if (!s || !s.bars.length) return null;
  // The decision week is the last COMPLETED week before the first buy.
  let w = weekAsOf(s, entryIso);
  if (w >= 0 && s.bars[w].d >= entryIso) w -= 1;
  if (w < 1) return null;
  const t = runTrade(s, w, { entryPrice: avgCost > 0 ? avgCost : undefined, trace: true });
  // The stop a week ago, so ORDERS can say "raised this week" and the BOOK
  // can show the ratchet.
  const prevStop = t && t.stops && t.stops.length >= 2 ? t.stops[t.stops.length - 2][1] : t ? t.initialStop : null;
  const last = s.bars.length - 1;
  if (!t) {
    // Bought at or under where the strategy's stop would have been: the rules
    // never had this trade. Manage it under the stage rule alone.
    const line = s.sma30[last];
    const broken = line != null && s.closes[last] < line;
    return {
      action: broken ? "EXIT" : "HOLD",
      stop: null,
      initialStop: null,
      reason: broken ? "closed below its 30-week average: the uptrend is over" : "no stop-loss for this buy price: kept while it stays above its 30-week average",
      r: null,
      weeks: last - w,
      entryWeek: s.bars[w].d,
      legacy: true,
    };
  }
  if (!t.open) {
    const labels = { stop: "hit its stop-loss", trail: "hit its raised stop-loss", thesis: "closed below its 30-week average: the uptrend is over", time: `held ${t.weeks} weeks: time limit reached` };
    return {
      action: "EXIT",
      stop: t.stop,
      initialStop: t.initialStop,
      reason: `${labels[t.reason] || t.reason} (week of ${s.bars[t.exitIdx].d})`,
      r: t.r,
      weeks: t.weeks,
      entryWeek: s.bars[w].d,
      exitedAt: s.bars[t.exitIdx].d,
    };
  }
  return {
    action: "HOLD",
    stop: t.stop,
    prevStop,
    initialStop: t.initialStop,
    reason: t.stop > t.initialStop ? "stop-loss raised as it gained" : "original stop-loss",
    r: t.r,
    weeks: t.weeks,
    entryWeek: s.bars[w].d,
  };
}

/**
 * The week's orders.
 *
 * @param {Object} p
 * @param {number} p.equityGBP   cash + holdings at market
 * @param {number} p.cashGBP
 * @param {Array}  p.holdings    [{t, qty, entryGBP, stopGBP, priceGBP, sector, action, returns}]
 *                               `action` from manageHolding; `returns` weekly log returns
 * @param {Array}  p.candidates  BUY cards, best first: [{t, total, sector, entry, stop, returns}]
 *                               prices in the stock's own currency
 * @param {Object} p.budget      tape.js budgetFor(...)
 * @param {Function} p.toGBP     native price -> GBP
 * @returns {{orders, skipped, heatBefore, heatAfter, cashAfter, positionsAfter}}
 */
export function construct({ equityGBP, cashGBP, holdings = [], candidates = [], budget, toGBP = (x) => x, caps = CAPS }) {
  const orders = [];
  const skipped = [];
  let cash = cashGBP;
  const kept = [];
  const fresh = new Map(candidates.map((c) => [c.t, c]));
  const reset = new Set();

  // 1. exits (or resets), 2. trails
  for (const h of holdings) {
    // RESET: the rules say this trade is over, but the same name is a fresh
    // BUY this week. Selling at Monday's open to buy it back at the same open
    // pays the FX fee twice for nothing, so the shares are kept and
    // re-underwritten as the NEW trade: its stop, and risk measured from the
    // current price. Trimmed only if the old size is well past what the new
    // trade's risk allows.
    const c = h.action === "EXIT" ? fresh.get(h.t) : null;
    if (c && toGBP(c.entry) > toGBP(c.stop) && h.priceGBP > toGBP(c.stop)) {
      const stopGBP = toGBP(c.stop);
      const allowed = (equityGBP * (budget.riskPct / 100) * riskShare(c.total)) / (h.priceGBP - stopGBP);
      orders.push({
        action: "RESET",
        t: h.t,
        stopGBP,
        stopNative: c.stop,
        setup: c.setup,
        total: c.total,
        reason: `${h.reason}, but it's a fresh buy again this week: keep the shares with the new stop-loss`,
      });
      let qty = h.qty;
      if (qty > allowed * 1.25 && (qty - allowed) * h.priceGBP >= caps.minOrderGBP) {
        orders.push({ action: "TRIM", t: h.t, qty: qty - allowed, priceGBP: h.priceGBP, reason: "cut back to the size the new trade allows" });
        cash += (qty - allowed) * h.priceGBP * (1 - COSTS.fxPct / 100);
        qty = allowed;
      }
      kept.push({ ...h, qty, entryGBP: h.priceGBP, stopGBP, action: "HOLD" });
      reset.add(h.t);
      continue;
    }
    if (h.action === "EXIT") {
      orders.push({ action: "EXIT", t: h.t, qty: h.qty, priceGBP: h.priceGBP, reason: h.reason });
      cash += h.qty * h.priceGBP * (1 - COSTS.fxPct / 100);
      continue;
    }
    if (h.newStopGBP != null && h.newStopGBP > h.stopGBP + 1e-9) {
      orders.push({ action: "TRAIL", t: h.t, stopGBP: h.newStopGBP, stopNative: h.newStopNative, reason: "the price has risen, so raise the stop-loss to protect the gain" });
      h.stopGBP = h.newStopGBP;
    }
    kept.push(h);
  }

  // 3. trims
  for (const h of kept) {
    const value = h.qty * h.priceGBP;
    if (equityGBP > 0 && (value / equityGBP) * 100 > caps.trimPct) {
      const targetQty = ((caps.maxPositionPct / 100) * equityGBP) / h.priceGBP;
      const sell = h.qty - targetQty;
      if (sell * h.priceGBP >= caps.minOrderGBP) {
        orders.push({ action: "TRIM", t: h.t, qty: sell, priceGBP: h.priceGBP, reason: `now ${((value / equityGBP) * 100).toFixed(0)}% of your account, over the ${caps.trimPct}% limit: sell some to spread the risk` });
        h.qty = targetQty;
        cash += sell * h.priceGBP * (1 - COSTS.fxPct / 100);
      }
    }
  }

  const heatBefore = kept.reduce((a, h) => a + openRiskGBP(h), 0);
  let heat = heatBefore;
  const heatCap = (budget.heatMax / 100) * equityGBP;
  const book = kept.map((h) => ({ t: h.t, sector: h.sector, returns: h.returns }));
  let added = 0;

  // 4. buys
  for (const c of candidates) {
    if (reset.has(c.t)) continue; // already answered by its RESET order
    const skip = (why) => skipped.push({ t: c.t, total: c.total, reason: why });
    if (book.some((b) => b.t === c.t)) {
      skip("you already own it");
      continue;
    }
    if (added >= budget.maxNew) {
      skip(`this week's limit is ${budget.maxNew} new ${budget.maxNew === 1 ? "stock" : "stocks"} (${budget.level} week)`);
      continue;
    }
    if (book.length >= caps.maxPositions) {
      skip(`you already hold the maximum of ${caps.maxPositions} stocks`);
      continue;
    }
    if (c.sector && book.filter((b) => b.sector === c.sector).length >= caps.maxPerSector) {
      skip(`you already own ${caps.maxPerSector} ${c.sector} names`);
      continue;
    }
    const twin = book
      .map((b) => ({ t: b.t, r: correlation(c.returns, b.returns) }))
      .filter((x) => x.r != null && x.r > caps.maxCorr)
      .sort((a, b) => b.r - a.r)[0];
    if (twin) {
      skip(`moves almost in step with ${twin.t}, which you own (correlated with ${twin.t})`);
      continue;
    }
    const entryGBP = toGBP(c.entry);
    const stopGBP = toGBP(c.stop);
    if (!(entryGBP > stopGBP) || !(stopGBP > 0)) {
      skip("no sensible stop-loss price");
      continue;
    }
    let riskGBP = equityGBP * (budget.riskPct / 100) * riskShare(c.total);
    if (heat + riskGBP > heatCap) riskGBP = heatCap - heat;
    if (riskGBP <= 0) {
      skip(`total risk limit of ${budget.heatMax}% reached`);
      continue;
    }
    let qty = riskGBP / (entryGBP - stopGBP);
    const maxValue = (caps.maxPositionPct / 100) * equityGBP;
    if (qty * entryGBP > maxValue) qty = maxValue / entryGBP;
    const spend = cash / (1 + COSTS.fxPct / 100);
    if (qty * entryGBP > spend) qty = spend / entryGBP;
    if (qty * entryGBP < caps.minOrderGBP) {
      skip(cash < caps.minOrderGBP ? "not enough cash" : "would be too small to be worth buying");
      continue;
    }
    const cost = qty * entryGBP * (1 + COSTS.fxPct / 100);
    const risk = qty * (entryGBP - stopGBP);
    orders.push({
      action: "BUY",
      t: c.t,
      qty,
      priceGBP: entryGBP,
      entryNative: c.entry,
      stopNative: c.stop,
      stopGBP,
      riskGBP: risk,
      valueGBP: qty * entryGBP,
      total: c.total,
      setup: c.setup,
      reason: `score ${c.total?.toFixed(0) ?? "—"} · puts ${((risk / equityGBP) * 100).toFixed(2)}% of your account at risk`,
    });
    cash -= cost;
    heat += risk;
    added++;
    book.push({ t: c.t, sector: c.sector, returns: c.returns });
  }

  return {
    orders,
    skipped,
    heatBefore,
    heatAfter: heat,
    heatCapGBP: heatCap,
    cashAfter: cash,
    positionsAfter: book.length,
  };
}
