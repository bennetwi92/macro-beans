// The real book, judged by the weekly strategy — shared by BOOK (step 4) and
// ORDERS (step 5). Reads the owner's Neon trading book (accounts, positions,
// trades, cash flows; RLS-scoped to the signed-in user) and, for every open
// position in the scored universe, replays the strategy's own rules from the
// week before the first buy (construct.js `manageHolding`):
//
//   * the stop is DERIVED — the strategy's initial stop for that entry,
//     trailed by the strategy's rules to this week — not typed in;
//   * EXIT when the replay says the stop was breached, the 30-week broke, or
//     the time limit passed; HOLD otherwise.
//
// Positions outside the scored universe (the LSE ETFs of the registry) are
// listed, valued, and left alone: the weekly strategy has nothing to say
// about them.

import { db } from "./neon.js";
import { openLot, accountCashGBP } from "./book.js";
import { loadPrices, toGBP, guessCurrency, autoCloseNative } from "./prices.js";
import { manageHolding, weeklyReturns, openRiskGBP } from "./construct.js";
import { loadScorecards, loadSeries } from "./review.js";
import { daysBetween, EARNINGS_WINDOW_DAYS } from "./scorecard.js";

export async function loadBook() {
  await loadPrices();
  const [a, p, t, c] = await Promise.all([
    db.from("accounts").select("*").order("name"),
    db.from("positions").select("*"),
    db.from("trades").select("*"),
    db.from("cash_flows").select("*"),
  ]);
  if (a.error) throw new Error(a.error.message);
  return { accounts: a.data || [], positions: p.data || [], trades: t.data || [], cash: c.error ? [] : c.data || [] };
}

/** Thesis wording for a holding: the stage now, read against the trade. */
function thesis(m, row) {
  if (!m) return { word: "UNSCORED", cls: "" };
  if (m.action === "EXIT") return { word: "BROKEN", cls: "down" };
  const st = row?.st;
  if (st === 2) return { word: "INTACT", cls: "up" };
  if (st === 1) return { word: "BASING", cls: "" };
  if (st === 3) return { word: "DEGRADED", cls: "cd-flag" };
  if (st === 4) return { word: "BROKEN", cls: "down" };
  return { word: "—", cls: "" };
}

/**
 * Every open position (optionally for one account), evaluated.
 * Returns `{sc, holdings, cashGBP, equityGBP}`; each holding:
 *   {pos, t, qty, cur, avgNative, firstBuy, priceNative, priceGBP, valueGBP,
 *    entryGBP, stopNative, stopGBP, prevStopNative, riskGBP, rNow, m, row,
 *    scored, thesis, earningsSoon, sector, returns}
 */
export async function evaluate(book, accountId = null) {
  const sc = await loadScorecards();
  const rows = new Map(sc.rows.map((r) => [r.t, r]));
  const positions = book.positions.filter((p) => accountId == null || p.account_id === accountId);
  const holdings = [];
  for (const pos of positions) {
    const lot = openLot(book.trades.filter((t) => t.position_id === pos.id));
    if (!lot.open) continue;
    const t = String(pos.instrument || "").toUpperCase();
    const cur = pos.currency || guessCurrency(t);
    const row = rows.get(t) || null;
    let m = null;
    let returns = row?.ret || null;
    if (row) {
      try {
        const { s } = await loadSeries(t, sc.data_as_of);
        m = manageHolding(s, lot.firstBuy, lot.avg);
        if (!returns) returns = weeklyReturns(s, s.bars.length - 1);
      } catch (_) {
        m = null;
      }
    }
    const manual = pos.mark != null && pos.mark !== "" ? +pos.mark : null; // manual marks are GBP
    const priceNative = row?.c ?? autoCloseNative(t);
    const priceGBP = manual != null ? manual : priceNative != null ? toGBP(priceNative, cur) : null;
    const entryGBP = toGBP(lot.avg, cur);
    const stopGBP = m?.stop != null ? toGBP(m.stop, cur) : null;
    const risk0 = m?.initialStop != null ? lot.avg - m.initialStop : null;
    const h = {
      pos,
      t,
      qty: lot.qty,
      cur,
      avgNative: lot.avg,
      firstBuy: lot.firstBuy,
      priceNative,
      priceGBP,
      valueGBP: priceGBP != null ? priceGBP * lot.qty : null,
      entryGBP,
      stopNative: m?.stop ?? null,
      stopGBP,
      prevStopNative: m?.prevStop ?? null,
      rNow: risk0 > 0 && priceNative != null ? (priceNative - lot.avg) / risk0 : null,
      m,
      row,
      scored: !!row,
      sector: row?.s || null,
      returns,
      earningsSoon: row?.next && daysBetween(sc.week, row.next) <= EARNINGS_WINDOW_DAYS ? row.next : null,
    };
    h.thesis = thesis(m, row);
    h.riskGBP = stopGBP != null && entryGBP != null ? openRiskGBP({ qty: h.qty, entryGBP, stopGBP }) : 0;
    holdings.push(h);
  }
  holdings.sort((a, b) => (b.valueGBP ?? 0) - (a.valueGBP ?? 0));
  const accountIds = accountId == null ? book.accounts.map((a) => a.id) : [accountId];
  const cashGBP = accountIds.reduce((s, id) => s + accountCashGBP(id, book.positions, book.trades, book.cash), 0);
  const equityGBP = cashGBP + holdings.reduce((s, h) => s + (h.valueGBP ?? 0), 0);
  return { sc, holdings, cashGBP, equityGBP };
}
