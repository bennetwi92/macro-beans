/* Strategy engine — pure functions shared between the single-instrument
   strategy page and the cross-instrument league table.

   No DOM, no state, no fetch — given a bar series and a settings object it
   returns events + stats. Format helpers are included here so both pages
   render numbers identically. */

export const HORIZONS = [1, 2, 3];

/* ---------- regime filter + max adverse excursion (scanner Phase 3) ----------
   Both additive — callers that omit opts.regime / ignore event.mae are
   unaffected (v1 pages keep working).
   - regimeSkip: with opts.regime set, only count events that fired in that
     200-day trend regime ('up' = close at/above the 200-day SMA).
   - maePct: the worst close-based drawdown from entry over the hold window
     (max adverse excursion), in %. */
function regimeSkip(sma200, i, regime, close){
  if(!sma200) return false;
  const s = sma200[i];
  if(!Number.isFinite(s)) return true;          // not enough history -> exclude
  return (regime === "up") !== (close >= s);    // skip on regime mismatch
}
function maePct(bars, exitIndexBase, entryPrice, maxH){
  let mae = 0;
  for(let h = 1; h <= maxH; h++){
    const r = bars[exitIndexBase + h][2] / entryPrice - 1;
    if(r < mae) mae = r;
  }
  return mae * 100;
}

/* findEvents
   bars: [[date_iso, open, close], ...]
   opts: {direction:'down'|'up', threshold:pct (positive number),
          entry:'close'|'open', range:'5y'|'all'}
   returns events in chronological order:
     [{date, trig, d1, d2, d3}]   (returns are %, cumulative from entry) */
export function findEvents(bars, opts){
  const thr = opts.threshold / 100;
  const sign = opts.direction === "down" ? -1 : 1;
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const needed = opts.entry === "open" ? 4 : 3;
  const rsma = opts.regime ? simpleMA(bars, 200) : null;
  const events = [];

  for(let i = 1; i < bars.length - needed; i++){
    const [date, , close] = bars[i];
    const prevClose = bars[i - 1][2];
    const trig = close / prevClose - 1;
    if(sign === -1 && trig > -thr) continue;
    if(sign === +1 && trig < +thr) continue;
    if(minDate && date < minDate) continue;
    if(regimeSkip(rsma, i, opts.regime, close)) continue;

    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){
      entryPrice    = close;
      exitIndexBase = i;
    } else {
      entryPrice    = bars[i + 1][1];
      exitIndexBase = i + 1;
    }
    const ds = HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);
    events.push({
      date,
      trig: trig * 100,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
      mae: maePct(bars, exitIndexBase, entryPrice, 3),
    });
  }
  return events;
}

function yearsAgo(bars, n){
  const lastDate = bars[bars.length - 1][0];
  const [Y, M, D] = lastDate.split("-").map(Number);
  return `${Y - n}-${String(M).padStart(2,"0")}-${String(D).padStart(2,"0")}`;
}

/* Horizons (trading days) measured forward for the Red Streak strategy.
   Stored in the d1/d2/d3 event slots so computeStats can be reused as-is —
   the pages label the columns DAY 1 / DAY 3 / DAY 5. */
export const STREAK_HORIZONS = [1, 3, 5];

/* findStreakEvents
   bars: [[date_iso, open, close], ...]
   opts: {direction:'down'|'up', streak:N (>=2), entry:'close'|'open',
          range:'5y'|'all'}
   An event fires on the day that completes a run of N consecutive closes in
   the chosen direction (each close below the prior for 'down', above for 'up').
   returns events in chronological order:
     [{date, streak, d1, d2, d3}]   (returns are %, cumulative from entry) */
export function findStreakEvents(bars, opts){
  const N = Math.max(2, Math.round(opts.streak));
  const up = opts.direction === "up";
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const maxH = STREAK_HORIZONS[STREAK_HORIZONS.length - 1];
  const needed = opts.entry === "open" ? maxH + 1 : maxH;
  const rsma = opts.regime ? simpleMA(bars, 200) : null;
  const events = [];

  for(let i = N; i < bars.length - needed; i++){
    const [date, , close] = bars[i];

    // require N consecutive closes in the chosen direction, ending at i
    let run = true;
    for(let k = 0; k < N; k++){
      const c = bars[i - k][2], prev = bars[i - k - 1][2];
      if(up ? !(c > prev) : !(c < prev)){ run = false; break; }
    }
    if(!run) continue;
    if(minDate && date < minDate) continue;
    if(regimeSkip(rsma, i, opts.regime, close)) continue;

    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){
      entryPrice    = close;
      exitIndexBase = i;
    } else {
      entryPrice    = bars[i + 1][1];
      exitIndexBase = i + 1;
    }
    const ds = STREAK_HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);
    events.push({
      date,
      streak: N,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
      mae: maePct(bars, exitIndexBase, entryPrice, maxH),
    });
  }
  return events;
}

/* ---------- multi-day change ----------
   Forward horizons (trading days) for the multi-day momentum strategy.
   Stored in d1/d2/d3 so computeStats is reused as-is; the pages label the
   columns DAY 1 / DAY 5 / DAY 10. */
export const MULTIDAY_HORIZONS = [1, 5, 10];

/* findMultiDayEvents
   bars: [[date_iso, open, close], ...]
   opts: {direction:'down'|'up', threshold:pct (positive), window:N (>=2),
          entry:'close'|'open', range:'5y'|'all'}
   An event fires on every day whose trailing `window`-day close-to-close move
   clears the threshold in the chosen direction. Like Buy the Bounce, but the
   move is measured over N days instead of one — so overlapping days in a long
   run can each qualify (the same convention as Red Streak).
   returns [{date, trig, d1, d2, d3}]  (returns are %, cumulative from entry). */
export function findMultiDayEvents(bars, opts){
  const thr  = opts.threshold / 100;
  const down = opts.direction === "down";
  const win  = Math.max(2, Math.round(opts.window));
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const maxH = MULTIDAY_HORIZONS[MULTIDAY_HORIZONS.length - 1];
  const needed = opts.entry === "open" ? maxH + 1 : maxH;
  const rsma = opts.regime ? simpleMA(bars, 200) : null;
  const events = [];

  for(let i = win; i < bars.length - needed; i++){
    const [date, , close] = bars[i];
    const move = close / bars[i - win][2] - 1;
    if(down ? move > -thr : move < thr) continue;
    if(minDate && date < minDate) continue;
    if(regimeSkip(rsma, i, opts.regime, close)) continue;

    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){ entryPrice = close; exitIndexBase = i; }
    else { entryPrice = bars[i + 1][1]; exitIndexBase = i + 1; }
    const ds = MULTIDAY_HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);
    events.push({
      date,
      trig: move * 100,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
      mae: maePct(bars, exitIndexBase, entryPrice, maxH),
    });
  }
  return events;
}

/* ---------- breakout (broke n-day high / low) ----------
   Forward horizons for the breakout strategy. */
export const BREAKOUT_HORIZONS = [1, 5, 10];

/* findBreakoutEvents
   opts: {direction:'up'|'down', lookback:N (>=2), entry, range}
   'up'   fires when today's close exceeds the highest close of the prior N days.
   'down' fires when today's close is below the lowest close of the prior N days.
   Closes are used as the high/low series (the build emits open+close only),
   which is the cleaner, gap-free definition of an n-day extreme.
   returns [{date, trig, d1, d2, d3}]   trig = % beyond the level just broken. */
export function findBreakoutEvents(bars, opts){
  const up = opts.direction === "up";
  const look = Math.max(2, Math.round(opts.lookback));
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const maxH = BREAKOUT_HORIZONS[BREAKOUT_HORIZONS.length - 1];
  const needed = opts.entry === "open" ? maxH + 1 : maxH;
  const rsma = opts.regime ? simpleMA(bars, 200) : null;
  const events = [];

  for(let i = look; i < bars.length - needed; i++){
    const [date, , close] = bars[i];
    let hi = -Infinity, lo = Infinity;
    for(let k = 1; k <= look; k++){
      const c = bars[i - k][2];
      if(c > hi) hi = c;
      if(c < lo) lo = c;
    }
    const level = up ? hi : lo;
    if(up ? !(close > hi) : !(close < lo)) continue;
    if(minDate && date < minDate) continue;
    if(regimeSkip(rsma, i, opts.regime, close)) continue;

    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){ entryPrice = close; exitIndexBase = i; }
    else { entryPrice = bars[i + 1][1]; exitIndexBase = i + 1; }
    const ds = BREAKOUT_HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);
    events.push({
      date,
      trig: (close / level - 1) * 100,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
      mae: maePct(bars, exitIndexBase, entryPrice, maxH),
    });
  }
  return events;
}

/* ---------- range / consolidation (trade within +-n% over y days) ----------
   Forward horizons for the range strategy. */
export const RANGE_HORIZONS = [1, 5, 10];

/* windowSpread — peak-to-trough spread of the `win` closes ending at index j,
   expressed as a fraction of the window mean. null if the window is incomplete.
   (hi - lo) / mean <= 2*band marks a band of +-band% around the average. */
function windowSpread(bars, j, win){
  if(j - win + 1 < 0) return null;
  let hi = -Infinity, lo = Infinity, sum = 0;
  for(let k = 0; k < win; k++){
    const c = bars[j - k][2];
    if(c > hi) hi = c;
    if(c < lo) lo = c;
    sum += c;
  }
  return (hi - lo) / (sum / win);
}

/* findRangeEvents
   A range forms when, over the trailing `window` days, every close sat inside a
   band of +-`band`% around the window's average (peak-to-trough spread
   <= 2*band%). The event fires on the first day a fresh range completes (the
   window qualifies but the prior window did not), so one event marks one quiet
   stretch — not one per day — and the forward returns show how it resolved.
   opts: {band:pct (half-width), window:y (>=3), entry, range}
   returns [{date, trig, d1, d2, d3}]   trig = the range's spread, in %. */
export function findRangeEvents(bars, opts){
  const band = opts.band / 100;
  const win  = Math.max(3, Math.round(opts.window));
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const maxH = RANGE_HORIZONS[RANGE_HORIZONS.length - 1];
  const needed = opts.entry === "open" ? maxH + 1 : maxH;
  const rsma = opts.regime ? simpleMA(bars, 200) : null;
  const events = [];

  for(let i = win - 1; i < bars.length - needed; i++){
    const spread = windowSpread(bars, i, win);
    if(spread === null || spread > 2 * band) continue;
    const prev = windowSpread(bars, i - 1, win);
    if(prev !== null && prev <= 2 * band) continue;   // only the first day
    if(minDate && bars[i][0] < minDate) continue;

    const close = bars[i][2];
    if(regimeSkip(rsma, i, opts.regime, close)) continue;
    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){ entryPrice = close; exitIndexBase = i; }
    else { entryPrice = bars[i + 1][1]; exitIndexBase = i + 1; }
    const ds = RANGE_HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);
    events.push({
      date: bars[i][0],
      trig: spread * 100,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
      mae: maePct(bars, exitIndexBase, entryPrice, maxH),
    });
  }
  return events;
}

/* ---------- moving-average cross (crossed above / below the 200-day) ----------
   Forward horizons for the MA-cross strategy — held longer, it's a slow signal. */
export const CROSS_HORIZONS = [5, 10, 20];

/* simpleMA — array of trailing `period`-day means of the close, NaN until the
   window fills. One O(n) pass with a rolling sum. */
function simpleMA(bars, period){
  const n = bars.length;
  const ma = new Array(n).fill(NaN);
  let run = 0;
  for(let i = 0; i < n; i++){
    run += bars[i][2];
    if(i >= period) run -= bars[i - period][2];
    if(i >= period - 1) ma[i] = run / period;
  }
  return ma;
}

/* findCrossEvents
   opts: {direction:'up'|'down', period:N (default 200), entry, range}
   'up'   fires when the close crosses from at-or-below its N-day average to
          above it; 'down' fires on the opposite cross. A cross is a single
          dated event, so these never overlap.
   returns [{date, trig, d1, d2, d3}]   trig = close's % gap to the average. */
export function findCrossEvents(bars, opts){
  const up = opts.direction === "up";
  const period = Math.max(2, Math.round(opts.period || 200));
  const minDate = opts.range === "5y" ? yearsAgo(bars, 5) : null;
  const maxH = CROSS_HORIZONS[CROSS_HORIZONS.length - 1];
  const needed = opts.entry === "open" ? maxH + 1 : maxH;
  const ma = simpleMA(bars, period);
  const rsma = opts.regime ? simpleMA(bars, 200) : null;
  const events = [];

  for(let i = period; i < bars.length - needed; i++){
    const sPrev = ma[i - 1], sCur = ma[i];
    if(!Number.isFinite(sPrev) || !Number.isFinite(sCur)) continue;
    const cPrev = bars[i - 1][2], cCur = bars[i][2];
    const crossed = up ? (cPrev <= sPrev && cCur > sCur)
                       : (cPrev >= sPrev && cCur < sCur);
    if(!crossed) continue;
    if(minDate && bars[i][0] < minDate) continue;
    if(regimeSkip(rsma, i, opts.regime, cCur)) continue;

    let entryPrice, exitIndexBase;
    if(opts.entry === "close"){ entryPrice = cCur; exitIndexBase = i; }
    else { entryPrice = bars[i + 1][1]; exitIndexBase = i + 1; }
    const ds = CROSS_HORIZONS.map(h => bars[exitIndexBase + h][2] / entryPrice - 1);
    events.push({
      date: bars[i][0],
      trig: (cCur / sCur - 1) * 100,
      d1: ds[0] * 100,
      d2: ds[1] * 100,
      d3: ds[2] * 100,
      mae: maePct(bars, exitIndexBase, entryPrice, maxH),
    });
  }
  return events;
}

/* ---------- live signals (scanner) ----------
   These ask "is the setup firing on the most recent bar?" — the question
   the scanner answers. They mirror the firing conditions in findEvents /
   findStreakEvents exactly, but require no forward bars (the event finders
   skip the last few bars because they need forward returns to score, so
   they never report a signal on the latest bar). Reusing the same
   comparisons keeps the scanner and the strategy pages in agreement. */

/* liveBounce — does the single-day move on the most recent bar clear the
   threshold in the chosen direction?
   opts:{direction:'down'|'up', threshold:pct}
   returns {triggered, move}   (move is the latest day's % change) */
export function liveBounce(bars, opts){
  if(!bars || bars.length < 2) return {triggered:false, move:NaN};
  const thr  = opts.threshold / 100;
  const last = bars[bars.length - 1][2];
  const prev = bars[bars.length - 2][2];
  const move = last / prev - 1;
  const triggered = opts.direction === "down" ? move <= -thr : move >= thr;
  return {triggered, move: move * 100};
}

/* liveStreak — does a run of at least N consecutive closes in the chosen
   direction end on the most recent bar?
   opts:{direction:'down'|'up', streak:N (>=2)}
   returns {triggered, run}   (run = length of the current consecutive run) */
export function liveStreak(bars, opts){
  const N  = Math.max(2, Math.round(opts.streak));
  const up = opts.direction === "up";
  if(!bars || bars.length < 2) return {triggered:false, run:0};
  const last = bars.length - 1;
  let run = 0;
  for(let k = 0; last - k - 1 >= 0; k++){
    const c = bars[last - k][2], prev = bars[last - k - 1][2];
    if(up ? c > prev : c < prev) run++; else break;
  }
  return {triggered: run >= N, run};
}

/* liveMultiDay — does the trailing `window`-day move on the most recent bar
   clear the threshold in the chosen direction?
   opts:{direction, threshold:pct, window:N}
   returns {triggered, move}   (move is the trailing window's % change). */
export function liveMultiDay(bars, opts){
  const win = Math.max(2, Math.round(opts.window));
  if(!bars || bars.length < win + 1) return {triggered:false, move:NaN};
  const last = bars.length - 1;
  const move = bars[last][2] / bars[last - win][2] - 1;
  const thr  = opts.threshold / 100;
  const triggered = opts.direction === "down" ? move <= -thr : move >= thr;
  return {triggered, move: move * 100};
}

/* liveBreakout — is the most recent close a fresh N-day high (up) or low (down)?
   opts:{direction:'up'|'down', lookback:N}
   returns {triggered, beyond}   (beyond = % past the broken level). */
export function liveBreakout(bars, opts){
  const look = Math.max(2, Math.round(opts.lookback));
  if(!bars || bars.length < look + 1) return {triggered:false, beyond:NaN};
  const last = bars.length - 1;
  const close = bars[last][2];
  let hi = -Infinity, lo = Infinity;
  for(let k = 1; k <= look; k++){
    const c = bars[last - k][2];
    if(c > hi) hi = c;
    if(c < lo) lo = c;
  }
  const up = opts.direction === "up";
  const level = up ? hi : lo;
  const triggered = up ? close > hi : close < lo;
  return {triggered, beyond: (close / level - 1) * 100};
}

/* liveRange — is the market currently inside a tight +-band% range over the
   trailing `window` days?  opts:{band:pct, window:y}
   returns {triggered, spread}   (spread = the range's peak-to-trough %). */
export function liveRange(bars, opts){
  const win = Math.max(3, Math.round(opts.window));
  if(!bars || bars.length < win) return {triggered:false, spread:NaN};
  const spread = windowSpread(bars, bars.length - 1, win);
  if(spread === null) return {triggered:false, spread:NaN};
  return {triggered: spread <= 2 * opts.band / 100, spread: spread * 100};
}

/* liveCross — did the most recent bar cross its N-day average in the chosen
   direction?  opts:{direction:'up'|'down', period:N}
   returns {triggered, gap}   (gap = close's % distance to the average). */
export function liveCross(bars, opts){
  const period = Math.max(2, Math.round(opts.period || 200));
  if(!bars || bars.length < period + 1) return {triggered:false, gap:NaN};
  const last = bars.length - 1;
  let run = 0;
  for(let k = last - period + 1; k <= last; k++) run += bars[k][2];
  const sCur = run / period;                       // mean [last-period+1 .. last]
  run -= bars[last][2];
  run += bars[last - period][2];
  const sPrev = run / period;                       // mean [last-period .. last-1]
  const up = opts.direction === "up";
  const cPrev = bars[last - 1][2], cCur = bars[last][2];
  const triggered = up ? (cPrev <= sPrev && cCur > sCur)
                       : (cPrev >= sPrev && cCur < sCur);
  return {triggered, gap: (cCur / sCur - 1) * 100};
}

/* ---------- value snapshot (cheap vs its own history) ----------
   valueMetrics — where the last close sits versus the instrument's own recent
   highs and long-run average. No forward strategy beyond fwdWhenCheap, which is
   evidence, not a forecast. Pure (no DOM/fetch).
   returns {last, offHigh52, vsSma200, rangePos5y, fwdWhenCheap, nCheap}:
     offHigh52    % vs the highest close of the last 252 days  (<=0 = below it)
     vsSma200     % vs the trailing 200-day average            (<0  = cheap)
     rangePos5y   position in the 5-year close range, 0=low .. 100=high
     fwdWhenCheap avg forward 21-day return on past days the close sat below its
                  200-day average (the "cheap" zone); nCheap = how many days. */
export function valueMetrics(bars){
  const out = {last:NaN, offHigh52:NaN, vsSma200:NaN, rangePos5y:NaN, fwdWhenCheap:NaN, nCheap:0};
  if(!bars || bars.length === 0) return out;
  const n = bars.length;
  const closes = bars.map(b => b[2]);
  const last = closes[n - 1];
  out.last = last;

  // % vs the highest close of the last 252 trading days (~1 year)
  const w52 = Math.min(252, n);
  let hi52 = -Infinity;
  for(let i = n - w52; i < n; i++) if(closes[i] > hi52) hi52 = closes[i];
  out.offHigh52 = (last / hi52 - 1) * 100;

  // % vs the trailing 200-day average
  const wSma = Math.min(200, n);
  let s = 0;
  for(let i = n - wSma; i < n; i++) s += closes[i];
  out.vsSma200 = (last / (s / wSma) - 1) * 100;

  // position in the 5-year (1260-day) close range
  const w5 = Math.min(1260, n);
  let lo5 = Infinity, hi5 = -Infinity;
  for(let i = n - w5; i < n; i++){ const c = closes[i]; if(c < lo5) lo5 = c; if(c > hi5) hi5 = c; }
  out.rangePos5y = hi5 > lo5 ? (last - lo5) / (hi5 - lo5) * 100 : NaN;

  // evidence: the MEDIAN forward 21-day return on every past day the close sat
  // below its trailing 200-day average. Median, not mean — a few days when the
  // price was tiny (e.g. natural gas in a crash) produce huge ratio outliers
  // that wreck an average. Rolling sum keeps the scan a single O(n) pass.
  const FWD = 21, P = 200;
  if(n > P + FWD){
    let run = 0;
    for(let k = 0; k < P; k++) run += closes[k];
    const fwd = [];
    for(let i = P - 1; i < n - FWD; i++){
      if(closes[i] < run / P) fwd.push(closes[i + FWD] / closes[i] - 1);
      run -= closes[i - P + 1];
      run += closes[i + 1];
    }
    if(fwd.length > 0){ out.fwdWhenCheap = median(fwd) * 100; out.nCheap = fwd.length; }
  }
  return out;
}

/* ---------- as-of / outcome helpers (scanner rewind) ----------
   These let the scanner replay itself as it would have looked on a past date.
   Both are pure and operate on the [date_iso, open, close] bar series. */

/* indexAsOf — index of the last bar whose date is on or before `isoDate`
   (a binary search over the chronologically sorted dates). Returns -1 when the
   series is empty or `isoDate` precedes the first bar. Lexicographic string
   comparison is correct for zero-padded ISO dates. */
export function indexAsOf(bars, isoDate){
  if(!bars || bars.length === 0) return -1;
  let lo = 0, hi = bars.length - 1, ans = -1;
  while(lo <= hi){
    const mid = (lo + hi) >> 1;
    if(bars[mid][0] <= isoDate){ ans = mid; lo = mid + 1; }
    else hi = mid - 1;
  }
  return ans;
}

/* forwardReturn — the actual % return of entering at the close of bar `idx` and
   exiting at the close `horizon` trading days later. NaN when `idx` is invalid
   or the exit bar lies beyond the series (the outcome window hasn't elapsed
   yet). This is the realised outcome the scanner shows in rewind mode, measured
   the same way as the AVG RETURN track record (close-to-close, cumulative). */
export function forwardReturn(bars, idx, horizon){
  if(idx < 0) return NaN;
  const exit = idx + horizon;
  if(exit >= bars.length) return NaN;
  return (bars[exit][2] / bars[idx][2] - 1) * 100;
}

/* computeStats — returns [day1, day2, day3] each:
     {n, wins, rate, avg, med, worst, best}    rates as percent points. */
export function computeStats(events){
  return HORIZONS.map((_, idx) => {
    const key = ["d1","d2","d3"][idx];
    const vals = events.map(e => e[key]);
    const n = vals.length;
    if(n === 0) return {n:0, wins:0, rate:NaN, avg:NaN, med:NaN, worst:NaN, best:NaN};
    const wins = vals.filter(v => v > 0).length;
    return {
      n, wins,
      rate:  wins / n * 100,
      avg:   vals.reduce((a,b)=>a+b,0) / n,
      med:   median(vals),
      worst: Math.min(...vals),
      best:  Math.max(...vals),
    };
  });
}

export function median(arr){
  const s = [...arr].sort((a,b)=>a-b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m-1] + s[m]) / 2;
}

/* ---------- formatting ---------- */

export const fmt = v => {
  if(!Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : (v < 0 ? "−" : "");
  return sign + Math.abs(v).toFixed(1) + "%";
};

export const fmtInt = v => Number.isFinite(v) ? Math.round(v).toString() : "—";

export const cls = v => {
  if(!Number.isFinite(v)) return "";
  return v > 0 ? "cell-pos" : (v < 0 ? "cell-neg" : "");
};

export function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"
  })[c]);
}
