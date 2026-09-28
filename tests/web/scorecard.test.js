// Unit tests for the scorecard (web/v2/js/scorecard.js).
//
// The load-bearing ones:
//   * fail open — an unavailable block drops out of the headline, which
//     rescales over what remains; it is never scored zero.
//   * no look-ahead — an earnings report is known only on a date STRICTLY
//     after it, and a fundamentals snapshot never grades a week before it.
//   * the vetoes — an earnings date inside the window holds a BUY back to
//     WATCH; reward:risk under MIN_RR is a PASS whatever the score.

import assert from "node:assert/strict";
import test from "node:test";

import {
  PROFILES,
  BLOCKS,
  MIN_RR,
  EARNINGS_WINDOW_DAYS,
  grade,
  headline,
  earningsBlock,
  nextEarnings,
  fundamentalBlock,
  analogueBlock,
  structureBlock,
  scoreCard,
  ordinal,
  daysBetween,
  addDays,
} from "../../web/v2/js/scorecard.js";
import { prepareSeries, setupsAt } from "../../web/v2/js/strategy.js";
import { barsFromCloses, walk } from "./_weekly-bars.js";

test("profiles: every setup's weights cover every block and sum to 100", () => {
  for (const [k, p] of Object.entries(PROFILES)) {
    assert.deepEqual(Object.keys(p.weights).sort(), [...BLOCKS].sort(), k);
    assert.equal(Object.values(p.weights).reduce((a, b) => a + b, 0), 100, k);
  }
});

test("grade: A–F bands", () => {
  assert.equal(grade(0.9), "A");
  assert.equal(grade(0.7), "B");
  assert.equal(grade(0.5), "C");
  assert.equal(grade(0.4), "D");
  assert.equal(grade(0.1), "F");
  assert.equal(grade(null), "—");
});

test("fail open: an unavailable block leaves the headline, it is not scored zero", () => {
  const b = (score, available = true) => ({ available, score });
  const weights = { market: 50, stage: 50 };
  assert.equal(headline({ market: b(0.8), stage: b(0.4) }, weights), 60);
  assert.equal(headline({ market: b(0.8), stage: b(null, false) }, weights), 80);
  assert.equal(headline({ market: b(null, false), stage: b(null, false) }, weights), null);
});

test("earnings: a report is known only STRICTLY after its date", () => {
  const reports = [{ d: "2026-07-30", surprise: 8 }];
  assert.equal(earningsBlock(reports, "2026-07-30").available, false, "same day: after the close, not yet known");
  const b = earningsBlock(reports, "2026-07-31");
  assert.equal(b.available, true);
  assert.ok(b.score > 0.5, "a positive surprise scores above neutral");
});

test("earnings: the drift is spent after a quarter; negative surprises score below neutral", () => {
  assert.equal(earningsBlock([{ d: "2026-01-02", surprise: 10 }], "2026-06-01").available, false);
  assert.ok(earningsBlock([{ d: "2026-05-01", surprise: -12 }], "2026-05-08").score < 0.5);
  assert.equal(earningsBlock([{ d: "2026-05-01", surprise: null }], "2026-05-08").available, false, "a scheduled report with no surprise yet");
});

test("nextEarnings: the first report strictly after the decision", () => {
  const r = [{ d: "2026-07-30" }, { d: "2026-10-29" }];
  assert.equal(nextEarnings(r, "2026-07-30"), "2026-10-29");
  assert.equal(nextEarnings(r, "2026-11-01"), null);
});

test("fundamentals: a snapshot never grades a week before it was taken", () => {
  const f = { quality: 70, value: 40, asOf: "2026-09-27" };
  assert.equal(fundamentalBlock(f, "PULLBACK", "2026-09-25").available, true, "the Friday just before a Sunday snapshot");
  assert.equal(fundamentalBlock(f, "PULLBACK", "2025-01-03").available, false, "a year earlier is look-ahead");
  assert.equal(fundamentalBlock(f, "PULLBACK", "2026-12-31").available, false, "a stale snapshot is not this week's");
  const q = fundamentalBlock({ quality: 80, value: 20, asOf: "2026-09-27" }, "REVERSAL", "2026-09-25");
  assert.ok(Math.abs(q.score - (0.8 * 0.8 + 0.2 * 0.2)) < 1e-9, "REVERSAL leans on quality");
});

test("analogues: fewer than three past trades on the name say nothing", () => {
  assert.equal(analogueBlock({ n: 2, shrunkR: 1, prior: 0.3 }).available, false);
  const b = analogueBlock({ n: 10, meanR: 0.9, shrunkR: 0.5, prior: 0.3, win: 0.4, edge: 0.01 });
  assert.ok(b.score > 0.5, "better than the universe's expectancy scores above neutral");
});

test("structure: reward:risk drives the score", () => {
  const lo = structureBlock({ rr: 1.2, entry: 100, atr: 3, support: null, blueSky: false, target: 104 }, "BREAKOUT");
  const hi = structureBlock({ rr: 3.5, entry: 100, atr: 3, support: null, blueSky: true, target: null }, "BREAKOUT");
  assert.ok(hi.score > lo.score);
});

test("ordinal, daysBetween, addDays", () => {
  assert.deepEqual([1, 2, 3, 11, 12, 13, 22, 53, 81].map(ordinal), ["1st", "2nd", "3rd", "11th", "12th", "13th", "22nd", "53rd", "81st"]);
  assert.equal(daysBetween("2026-09-25", "2026-10-09"), 14);
  assert.equal(addDays("2026-09-25", 14), "2026-10-09");
});

/* ---------- the card ---------- */

function firstBuy(seed) {
  const s = prepareSeries(barsFromCloses(walk(3000, { seed })));
  for (let w = 200; w < s.bars.length - 2; w++) {
    if (setupsAt(s, w).some((x) => x.status === "BUY")) return { s, w };
  }
  return null;
}

test("card: a report due inside the window holds a BUY back to WATCH", () => {
  const { s, w } = firstBuy(21);
  const date = s.bars[w].d;
  const clear = scoreCard({ t: "X", s, w, market: null, events: [], priors: null, earnings: [], fundamentals: null });
  const soon = scoreCard({
    t: "X",
    s,
    w,
    market: null,
    events: [],
    priors: null,
    earnings: [{ d: addDays(date, EARNINGS_WINDOW_DAYS - 3), surprise: null }],
    fundamentals: null,
  });
  if (clear.status === "BUY") {
    assert.equal(soon.status, "WATCH");
    assert.match(soon.why, /earnings/);
  }
  assert.ok(soon.flags.some((f) => f.startsWith("earnings")));
});

test("card: reward:risk under MIN_RR is a PASS, whatever the score", () => {
  for (const seed of [3, 5, 7, 9, 11, 13, 21, 33]) {
    const s = prepareSeries(barsFromCloses(walk(3000, { seed })));
    for (let w = 200; w < s.bars.length - 2; w++) {
      const c = scoreCard({ t: "X", s, w, market: null, events: [], priors: null, earnings: null, fundamentals: null });
      if (c.setup && c.plan.rr != null && c.plan.rr < MIN_RR) {
        assert.equal(c.status, "PASS");
        assert.ok(c.vetoes.some((v) => v.startsWith("too little room to rise")));
        return;
      }
    }
  }
  assert.fail("no fixture produced a low R:R setup");
});

test("card: a week with no setup still carries the stage for the BOOK", () => {
  const s = prepareSeries(barsFromCloses(walk(1500, { seed: 4 })));
  let w = 200;
  while (setupsAt(s, w).length) w++;
  const c = scoreCard({ t: "X", s, w, market: null, events: [], priors: null, earnings: null, fundamentals: null });
  assert.equal(c.setup, null);
  assert.equal(c.status, null);
  assert.equal(c.stage, s.stage[w]);
});

test("card: no look-ahead — the card at week w ignores everything after it", () => {
  const daily = barsFromCloses(walk(2600, { seed: 5 }));
  const full = prepareSeries(daily);
  for (let w = 150; w < full.bars.length - 30; w += 23) {
    const cutDaily = daily.slice(0, full.bars[w].di + 1);
    const cut = prepareSeries(cutDaily, cutDaily[cutDaily.length - 1].d);
    const ctx = { t: "X", market: null, events: [], priors: null, earnings: null, fundamentals: null };
    assert.deepEqual(scoreCard({ ...ctx, s: cut, w }), scoreCard({ ...ctx, s: full, w }), `week ${w}`);
  }
});
