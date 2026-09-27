// Shared trading-book accounting (average cost, GBP). Pure functions used by
// both the Positions and Portfolio pages so the numbers always agree.

import { toGBP, autoCloseNative, guessCurrency } from "./prices.js";

const byDate = (x, y) =>
  x.traded_at < y.traded_at ? -1 : x.traded_at > y.traded_at ? 1 : x.created_at < y.created_at ? -1 : 1;

// Average-cost metrics for one position from its trades (+ optional mark).
export function positionMetrics(posTrades, mark) {
  const ts = [...posTrades].sort(byDate);
  let qty = 0, avg = 0, realized = 0;
  for (const t of ts) {
    const q = +t.quantity, pr = +t.price, fee = +t.fees || 0;
    if (t.side === "sell") {
      realized += pr * q - fee - avg * q; // proceeds net of fees, minus cost
      qty -= q;
      if (qty < 1e-9) qty = 0;
    } else {
      const cost = avg * qty + pr * q + fee; // buy fees fold into the cost basis
      qty += q;
      avg = qty > 0 ? cost / qty : 0;
    }
  }
  const m = mark != null && mark !== "" ? +mark : null;
  const open = qty > 1e-9;
  const costBasis = open ? qty * avg : 0;
  const mktVal = open && m != null ? qty * m : null;
  const unreal = open && m != null ? (m - avg) * qty : null;
  return { qty, avg, realized, mark: m, open, costBasis, mktVal, unreal, total: realized + (unreal || 0), nTrades: ts.length };
}

// Currency-aware metrics in GBP for one position. Trade prices are entered in
// the instrument's native currency and converted here; fees are already GBP.
// Mark is the manual mark (GBP) if set, else the auto cockpit close (native ->
// GBP). All returned monetary fields are GBP.
export function gbpPositionMetrics(pos, posTrades) {
  const cur = pos.currency || guessCurrency(pos.instrument);
  const gbpTrades = posTrades.map((t) => ({ ...t, price: toGBP(+t.price, cur) }));
  const manual = pos.mark != null && pos.mark !== "" ? +pos.mark : null;
  const autoN = autoCloseNative(pos.instrument);
  const markGBP = manual != null ? manual : autoN != null ? toGBP(autoN, cur) : null;
  const m = positionMetrics(gbpTrades, markGBP);
  return { ...m, cur, markGBP, markAuto: manual == null && markGBP != null, manualMark: manual };
}

// Signed GBP impact of a trade on the account's cash (buys spend, sells add).
// Trade prices are native; convert to GBP using the position's currency.
export function tradeCashGBP(t, currency) {
  const q = +t.quantity, pr = toGBP(+t.price, currency), fee = +t.fees || 0;
  return t.side === "sell" ? pr * q - fee : -(pr * q + fee);
}

// The OPEN lot of a position in its native currency: quantity, average cost,
// and the date of the first buy since the position was last flat. The weekly
// strategy replays its rules from that date (construct.js manageHolding), so
// a name bought, sold out and bought again is judged on the current trade.
export function openLot(posTrades) {
  const ts = [...posTrades].sort(byDate);
  let qty = 0, avg = 0, firstBuy = null;
  for (const t of ts) {
    const q = +t.quantity, pr = +t.price;
    if (t.side === "sell") {
      qty -= q;
      if (qty < 1e-9) { qty = 0; avg = 0; firstBuy = null; }
    } else {
      if (qty < 1e-9) firstBuy = t.traded_at;
      avg = (avg * qty + pr * q) / (qty + q);
      qty += q;
    }
  }
  return { qty, avg, firstBuy, open: qty > 1e-9 };
}

// Cash balance of an account in GBP: its cash flows plus the settlement of
// every trade in it. The same arithmetic as the Portfolio page.
export function accountCashGBP(accountId, positions, trades, cashFlows) {
  const posById = Object.fromEntries(positions.map((p) => [p.id, p]));
  let bal = 0;
  for (const cf of cashFlows) if (cf.account_id === accountId) bal += +cf.amount;
  for (const t of trades) {
    const p = posById[t.position_id];
    if (p && p.account_id === accountId) bal += tradeCashGBP(t, p.currency || "GBP");
  }
  return bal;
}
