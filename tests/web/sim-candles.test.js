// Unit tests for the simulator's tier-2 candlestick catalogue
// (web/v2/js/sim-candles.js).
//
// Two things here are worth more than the catalogue coverage. The threshold
// system has two behaviours — a trailing average and a comparison against the
// bar's own body — and conflating them is the classic way a home-grown
// detector goes wrong, so `avg` is tested directly. And the trend gate is part
// of each definition rather than a filter over it: a hammer with no prior
// downtrend is not a weak hammer, it is not a hammer, so every reversal
// pattern is tested BOTH ways round.

import assert from "node:assert/strict";
import test from "node:test";

import { CANDLE, CANDLE_IDS, avg, candlesAt, trendBefore } from "../../web/v2/js/sim-candles.js";
import { atr } from "../../web/v2/js/sim-indicators.js";
import { series } from "./_sim-bars.js";

const WARM = 40;

/**
 * A run of `n` quiet bars, then a `trend` leg, then the caller's own candles.
 * Returns the bars, the ATR array and the index of the last bar.
 */
function tape(trend, paint) {
  const s = series(120).flat(WARM, 1.2);
  if (trend === "down") s.down(14, 2.6);
  else if (trend === "up") s.up(14, 2.6);
  else s.flat(14, 1.2);
  paint(s, s.price);
  const bars = s.build();
  return { bars, atrArr: atr(bars, 14), e: bars.length - 1 };
}

const idsAt = (t) => candlesAt(t.bars, t.atrArr, t.e).map((m) => m.entry.id);
const has = (t, id) => idsAt(t).includes(id);

/* ---------- the threshold system ---------- */

test("avg: n = 0 compares against this bar's own body", () => {
  const bars = series(100).flat(20, 1).build();
  const i = 15;
  const b = bars[i];
  const body = Math.abs(b.c - b.o);
  assert.equal(avg(CANDLE.shadowLong, bars, i), 1.0 * body);
  assert.equal(avg(CANDLE.shadowVeryLong, bars, i), 2.0 * body);
});

test("avg: n > 0 averages the n bars STRICTLY BEFORE i", () => {
  const s = series(100);
  for (let i = 0; i < 20; i++) s.bar({ o: 100, h: 101, l: 99, c: 100.5 });
  // Bar 15 is enormous; it must not raise the bar it has to clear.
  s.rows[15] = { o: 100, h: 130, l: 70, c: 129, v: 1e6 };
  const bars = s.build();
  const before = avg(CANDLE.bodyDoji, bars, 15);
  const after = avg(CANDLE.bodyDoji, bars, 16);
  assert.ok(before < after, "bar 15 is excluded from its own average and included in bar 16's");
  assert.equal(before, 0.1 * 2, "ten quiet bars of range 2");
});

test("avg: returns null rather than throwing when the history is short", () => {
  const bars = series(100).flat(6, 1).build();
  assert.equal(avg(CANDLE.bodyLong, bars, 3), null);
  assert.equal(avg(CANDLE.near, bars, 2), null);
  assert.equal(avg(CANDLE.bodyLong, bars, 99), null);
});

/* ---------- the trend gate ---------- */

test("trendBefore: reads only the bars before the pattern's first", () => {
  const t = tape("down", (s) => s.up(4, 6)); // a hard rally AFTER the downtrend
  const first = t.e - 3;
  assert.equal(
    trendBefore(t.bars, t.atrArr, first),
    "down",
    "the pattern's own rally must not be counted as its prior trend"
  );
});

test("trendBefore: flat is flat, and short history is null", () => {
  const t = tape("flat", (s) => s.flat(2, 1));
  assert.equal(trendBefore(t.bars, t.atrArr, t.e), "flat");
  assert.equal(trendBefore(t.bars, t.atrArr, 3), null);
});

/* ---------- the catalogue ---------- */

/** A long black bar, then a white one that swallows it whole. */
const engulfBull = (s, p) => {
  s.bar({ o: p, h: p + 0.2, l: p - 5.2, c: p - 5 });
  s.bar({ o: p - 5.2, h: p + 0.6, l: p - 5.4, c: p + 0.4 });
};
const engulfBear = (s, p) => {
  s.bar({ o: p, h: p + 5.2, l: p - 0.2, c: p + 5 });
  s.bar({ o: p + 5.2, h: p + 5.4, l: p - 0.6, c: p - 0.4 });
};
/**
 * A small body sitting on top of a long lower shadow, with its body down at
 * the prior bar's low — the hammer's own proximity test.
 */
const hammerBar = (s, p) => {
  s.bar({ o: p - 3.6, h: p - 3.4, l: p - 8, c: p - 7.6 }); // sets the prior low
  s.bar({ o: p - 7.7, h: p - 6.7, l: p - 11, c: p - 6.9 });
};
/** The mirror: a long upper shadow, body up at the prior bar's top. */
const starBar = (s, p) => {
  s.bar({ o: p + 3.6, h: p + 4, l: p + 3.4, c: p + 7.6 });
  s.bar({ o: p + 7.7, h: p + 11, l: p + 6.7, c: p + 6.9 });
};
/** The hammer's shape after a rally, with its body up at the prior HIGH. */
const hangingMan = (s, p) => {
  s.bar({ o: p, h: p + 4, l: p - 0.2, c: p + 3.8 });
  s.bar({ o: p + 3.5, h: p + 4.5, l: p + 0.3, c: p + 4.3 });
};

test("catalogue: bullish engulfing needs a downtrend", () => {
  assert.ok(has(tape("down", engulfBull), "bull-engulfing"));
  assert.ok(!has(tape("flat", engulfBull), "bull-engulfing"), "flat rejects it");
  assert.ok(!has(tape("up", engulfBull), "bull-engulfing"), "an uptrend rejects it");
});

test("catalogue: bearish engulfing needs an uptrend", () => {
  assert.ok(has(tape("up", engulfBear), "bear-engulfing"));
  assert.ok(!has(tape("down", engulfBear), "bear-engulfing"));
});

test("catalogue: hammer and hanging man are the same shape, split by trend", () => {
  assert.ok(has(tape("down", hammerBar), "hammer"));
  assert.ok(!has(tape("down", hammerBar), "hanging-man"));
  assert.ok(!has(tape("up", hammerBar), "hammer"), "the gate is the definition");
  // The same silhouette after a rally is the bearish half of the pair. Only
  // the proximity test differs — to the prior high rather than the prior low —
  // so the fixture differs; neither ever fires on both trends.
  assert.ok(has(tape("up", hangingMan), "hanging-man"));
  assert.ok(!has(tape("down", hangingMan), "hanging-man"));
});

test("catalogue: shooting star needs an uptrend", () => {
  assert.ok(has(tape("up", starBar), "shooting-star"));
  assert.ok(!has(tape("down", starBar), "shooting-star"));
});

test("catalogue: a doji is trend-free — it claims nothing to gate", () => {
  const paint = (s, p) => s.bar({ o: p, h: p + 2, l: p - 2, c: p });
  for (const trend of ["up", "down", "flat"]) {
    assert.ok(has(tape(trend, paint), "doji"), `doji missing after a ${trend} trend`);
  }
});

test("catalogue: a doji is labelled by its shadows", () => {
  const dragonfly = tape("flat", (s, p) => s.bar({ o: p, h: p + 0.05, l: p - 3, c: p }));
  const m = candlesAt(dragonfly.bars, dragonfly.atrArr, dragonfly.e).find((x) => x.entry.id === "doji");
  assert.equal(m.label, "DRAGONFLY DOJI");
  assert.equal(m.entry.id, "doji", "the id is stable; only the label changes");
});

test("catalogue: marubozu is a continuation and needs the trend to match", () => {
  const paint = (s, p) => s.bar({ o: p, h: p + 6.02, l: p - 0.02, c: p + 6 });
  assert.ok(has(tape("up", paint), "marubozu-bull"));
  assert.ok(!has(tape("down", paint), "marubozu-bull"), "a bull marubozu continues an uptrend");
});

test("catalogue: three white soldiers", () => {
  const paint = (s, p) => {
    s.bar({ o: p, h: p + 3.05, l: p - 0.1, c: p + 3 });
    s.bar({ o: p + 1.5, h: p + 6.05, l: p + 1.4, c: p + 6 });
    s.bar({ o: p + 4.5, h: p + 9.05, l: p + 4.4, c: p + 9 });
  };
  assert.ok(has(tape("down", paint), "three-white-soldiers"));
});

test("catalogue: morning star, and its doji-star label", () => {
  const paint = (s, p) => {
    s.bar({ o: p, h: p + 0.2, l: p - 6.2, c: p - 6 }); // long black
    s.bar({ o: p - 6.4, h: p - 6.3, l: p - 6.5, c: p - 6.4 }); // the star: a doji
    s.bar({ o: p - 6.2, h: p - 1.8, l: p - 6.3, c: p - 2 }); // long white back in
  };
  const t = tape("down", paint);
  const m = candlesAt(t.bars, t.atrArr, t.e).find((x) => x.entry.id === "morning-star");
  assert.ok(m, "morning star not found");
  assert.equal(m.label, "MORNING DOJI STAR");
});

test("catalogue: piercing and engulfing are mutually exclusive", () => {
  const paint = (s, p) => {
    s.bar({ o: p, h: p + 0.2, l: p - 6.2, c: p - 6 });
    s.bar({ o: p - 6.6, h: p - 2.4, l: p - 6.8, c: p - 2.5 }); // opens below, closes inside
  };
  const ids = idsAt(tape("down", paint));
  assert.ok(ids.includes("piercing"));
  assert.ok(!ids.includes("bull-engulfing"), "closing inside the prior body rules engulfing out");
});

test("catalogue: a tiny bar engulfing a tinier one does not qualify", () => {
  const paint = (s, p) => {
    s.bar({ o: p, h: p + 0.02, l: p - 0.04, c: p - 0.02 });
    s.bar({ o: p - 0.03, h: p + 0.03, l: p - 0.05, c: p + 0.01 });
  };
  assert.ok(!has(tape("down", paint), "bull-engulfing"), "the two size floors do their job");
});

/* ---------- invariants ---------- */

test("invariant: candlesAt never reads past e", () => {
  const t = tape("down", engulfBull);
  const full = candlesAt(t.bars, t.atrArr, t.e - 1).map((m) => m.entry.id);
  const trunc = candlesAt(t.bars.slice(0, t.e), t.atrArr.slice(0, t.e), t.e - 1).map(
    (m) => m.entry.id
  );
  assert.deepEqual(trunc, full);
});

test("invariant: short input and out-of-range indices return [], never a throw", () => {
  assert.deepEqual(candlesAt([], [], 0), []);
  const tiny = series(100).flat(4, 1).build();
  assert.deepEqual(candlesAt(tiny, atr(tiny, 14), 3), []);
  assert.deepEqual(candlesAt(tiny, atr(tiny, 14), 99), []);
});

test("invariant: matches come back in catalogue order, and every id is unique", () => {
  assert.equal(new Set(CANDLE_IDS).size, CANDLE_IDS.length);
  assert.equal(CANDLE_IDS.length, 17, "seventeen signed entries across twelve families");
  const t = tape("down", engulfBull);
  const ids = idsAt(t);
  const order = ids.map((id) => CANDLE_IDS.indexOf(id));
  assert.deepEqual(order, order.slice().sort((a, b) => a - b));
});
