/* Strategy engine — pure functions shared between the single-instrument
   strategy page and the cross-instrument league table.

   No DOM, no state, no fetch — given a bar series and a settings object it
   returns events + stats. Format helpers are included here so both pages
   render numbers identically. */

export const HORIZONS = [1, 2, 3];

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
  const events = [];

  for(let i = 1; i < bars.length - needed; i++){
    const [date, , close] = bars[i];
    const prevClose = bars[i - 1][2];
    const trig = close / prevClose - 1;
    if(sign === -1 && trig > -thr) continue;
    if(sign === +1 && trig < +thr) continue;
    if(minDate && date < minDate) continue;

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
    });
  }
  return events;
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
