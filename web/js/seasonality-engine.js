/* seasonality-engine.js — pure functions for the Best Months pages.

   Given a per-instrument daily bar series it collapses the data into one
   return per calendar month, then buckets those by month-of-year to show how
   each month has historically performed. A different computation shape from
   the event/forward-return engine, so it lives in its own module — but the
   same rule applies: no DOM, no state, no fetch. The single-instrument page
   and the league page both import from here so their numbers always agree. */

import { median } from "./strategy-engine.js";

export const MONTH_NAMES =
  ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// Nov–Apr is the "winter" half in the old "sell in May and go away" saying.
const WINTER_MONTHS = new Set([11, 12, 1, 2, 3, 4]);

function yearsAgoKey(bars, n){
  // "YYYY-MM" cutoff n years before the last bar.
  const last = bars[bars.length - 1][0];
  const y = Number(last.slice(0, 4)) - n;
  return `${y}${last.slice(4, 7)}`;
}

/* monthlyReturns — collapse daily bars into one return per calendar month.
   Month return = last close of the month / last close of the previous month − 1
   (standard month-over-month). Drops the first month (no prior to compare to).
   opts.range '10y' keeps the last 10 years; 'all' keeps everything.
   returns [{y, m, ret}] chronological, ret as a decimal. */
export function monthlyReturns(bars, opts){
  const cutoff = (opts && opts.range === "10y") ? yearsAgoKey(bars, 10) : null;

  // last close seen in each "YYYY-MM", preserving first-seen order
  const lastClose = new Map();
  const order = [];
  for(const [date, , close] of bars){
    const key = date.slice(0, 7);
    if(!lastClose.has(key)) order.push(key);
    lastClose.set(key, close);
  }

  const out = [];
  for(let i = 1; i < order.length; i++){
    const key = order[i];
    if(cutoff && key < cutoff) continue;
    const base = lastClose.get(order[i - 1]);
    const cur  = lastClose.get(key);
    const [Y, M] = key.split("-").map(Number);
    out.push({ y: Y, m: M, ret: cur / base - 1 });
  }
  return out;
}

/* computeMonths — aggregate the per-month returns by month-of-year.
   returns [{m, name, n, green, avg, med, best, worst}] of length 12.
     n     = number of years counted for that month
     green = % of those years the month finished positive
     avg / med / best / worst = % return across the years */
export function computeMonths(bars, opts){
  const rets = monthlyReturns(bars, opts);
  return MONTH_NAMES.map((name, idx) => {
    const m = idx + 1;
    const vals = rets.filter(r => r.m === m).map(r => r.ret * 100);
    const n = vals.length;
    if(n === 0) return {m, name, n:0, green:NaN, avg:NaN, med:NaN, best:NaN, worst:NaN};
    return {
      m, name, n,
      green: vals.filter(v => v > 0).length / n * 100,
      avg:   vals.reduce((a,b)=>a+b,0) / n,
      med:   median(vals),
      best:  Math.max(...vals),
      worst: Math.min(...vals),
    };
  });
}

/* seasonHalves — the "sell in May" split.
   winter = Nov–Apr, summer = May–Oct. Each: average month return (%),
   green % of months, and the count of months pooled. */
export function seasonHalves(bars, opts){
  const rets = monthlyReturns(bars, opts);
  const part = isWinter => {
    const vals = rets
      .filter(r => WINTER_MONTHS.has(r.m) === isWinter)
      .map(r => r.ret * 100);
    const n = vals.length;
    if(n === 0) return {n:0, avg:NaN, green:NaN};
    return {
      n,
      avg:   vals.reduce((a,b)=>a+b,0) / n,
      green: vals.filter(v => v > 0).length / n * 100,
    };
  };
  return { winter: part(true), summer: part(false) };
}
