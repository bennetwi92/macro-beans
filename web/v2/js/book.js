// Shared trading-book accounting (average cost, GBP). Pure functions used by
// both the Positions and Portfolio pages so the numbers always agree.

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

// Signed GBP impact of a trade on the account's cash (buys spend, sells add).
export function tradeCash(t) {
  const q = +t.quantity, pr = +t.price, fee = +t.fees || 0;
  return t.side === "sell" ? pr * q - fee : -(pr * q + fee);
}
