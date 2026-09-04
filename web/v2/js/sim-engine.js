// Trade accounting for the swing-trading simulator — pure functions, no DOM,
// no fetch, so the rules can be unit-tested under `node --test`.
//
// The model the simulator trains against:
//   * You decide on the CLOSE of the decision day, with the stop already set.
//   * Entry fills at the NEXT day's OPEN — you cannot buy the bar you decided on.
//   * Discretionary exits (half or all) fill at that day's CLOSE.
//   * The stop is live from the entry bar onwards and fills intraday: at the
//     stop price normally, at the open if the bar gapped straight through it.
//   * Everything is quoted in percent of the notional at entry, plus R — the
//     result divided by the distance from entry to stop, which is the number
//     that actually transfers between trades of different sizes.

export const LONG = "long";
export const SHORT = "short";

const EPS = 1e-9;

/** Open a position. `fraction` of the original size still on is tracked as `open`. */
export function openTrade({ side, stop, entryIndex, entryPrice }) {
  return {
    side,
    stop,
    entryIndex,
    entryPrice,
    open: 1,
    exits: [], // [{index, price, fraction, reason}]
    stopped: false,
  };
}

export const isOpen = (trade) => !!trade && trade.open > EPS;

/** +1 for a long, -1 for a short. */
export const dirOf = (trade) => (trade.side === SHORT ? -1 : 1);

/**
 * The fill price if `bar` ({o, h, l, c}) breaches the trade's stop, else null.
 * A bar that gaps through the stop fills at the open, not at the stop — the
 * single most common way a "1R risk" turns into a 3R loss in real trading.
 */
export function stopFill(trade, bar) {
  if (!isOpen(trade)) return null;
  if (trade.side === SHORT) {
    if (bar.h < trade.stop) return null;
    return Math.max(trade.stop, bar.o);
  }
  if (bar.l > trade.stop) return null;
  return Math.min(trade.stop, bar.o);
}

/**
 * Close `fraction` of the ORIGINAL position at `price`. Fractions are clamped
 * to whatever is still open, so "exit 50%" twice closes the trade exactly.
 */
export function exitTrade(trade, { index, price, fraction = 1, reason = "manual" }) {
  const size = Math.min(fraction, trade.open);
  if (size <= EPS) return trade;
  return {
    ...trade,
    open: trade.open - size,
    exits: [...trade.exits, { index, price, fraction: size, reason }],
    stopped: trade.stopped || reason === "stop",
  };
}

/**
 * Advance the trade onto `bar` (index `index`), applying the stop if it is
 * breached. Returns the trade plus whether this bar stopped it out.
 */
export function stepTrade(trade, bar, index) {
  const fill = stopFill(trade, bar);
  if (fill == null) return { trade, stopped: false };
  return {
    trade: exitTrade(trade, { index, price: fill, fraction: trade.open, reason: "stop" }),
    stopped: true,
  };
}

/** Percent move from entry in the trade's direction (a long's loss is negative). */
function legPct(trade, price) {
  return dirOf(trade) * (price / trade.entryPrice - 1) * 100;
}

/**
 * Result so far, marked at `markPrice` for whatever is still open.
 *   realized / unrealized / total — percent of the notional at entry
 *   risk                          — entry-to-stop distance, percent
 *   r                             — total / risk, the comparable number
 */
export function tradeStats(trade, markPrice) {
  const realized = trade.exits.reduce(
    (acc, e) => acc + e.fraction * legPct(trade, e.price),
    0
  );
  const unrealized = trade.open > EPS && markPrice != null
    ? trade.open * legPct(trade, markPrice)
    : 0;
  const total = realized + unrealized;
  const risk = Math.abs(trade.entryPrice - trade.stop) / trade.entryPrice * 100;
  return {
    realized,
    unrealized,
    total,
    risk,
    r: risk > EPS ? total / risk : 0,
  };
}

/**
 * Is this stop usable for `side` given the last close? A long's stop sits below
 * the price and a short's above it; the simulator uses this to enable the BUY
 * and SHORT buttons rather than letting you take a position that is already
 * stopped out.
 */
export function stopAllows(side, stop, lastClose) {
  return side === SHORT ? stop > lastClose : stop < lastClose;
}
