# Simulator candlestick patterns — implementation specification

Implementation spec for candlestick pattern recognition on the swing-trading
simulator (`web/v2/simulator.html`). Written to be handed to an implementing
agent: every threshold, rule, state transition and file is named, and §14 is a
checklist you can fail.

The evidence behind the design decisions is in
[`candlestick_pattern_research.md`](candlestick_pattern_research.md). Read it
first — several rules below are deliberate departures from TA-Lib, and the
reasons are there, not here.

Read [`.claude/skills/macro-beans-site/SKILL.md`](../../.claude/skills/macro-beans-site/SKILL.md)
§"Work on the simulator" before starting. Its two rules bind this work:
**keep the math out of the page module**, and **lay the bars out before
measuring the chart**.

---

## 1. What ships

The simulator chart gains **at most one** candlestick pattern annotation per
deal, consisting of three things:

1. A **bracket** drawn around the candles that form the pattern.
2. A **label** — one short line of 9px text naming the pattern and its state.
3. A **target tick** — a small dotted mark at the level a working pattern
   would be expected to reach.

Plus a state that evolves as the hand plays out: a pattern that was *complete*
when you decided becomes *confirmed* or *failed* over the following sessions,
and the annotation says which.

### Non-goals

- **Simulator chart only.** Nothing in `price-sheet.html`, `charts.html`, the
  scanner, or v1. No shared "pattern" concept across the site.
- **No build-step or data change.** Detection is client-side from the OHLC
  already in `web/v2/data/sim/<TICKER>.json`. Do not touch `build_sim.py`,
  `deploy.yml`, `.gitignore`, or `nav.js`.
- **No new status chips.** `.sim-status` is capped at 52px (30px landscape) and
  `trade` mode already fits six chips into it. The annotation lives in the
  chart. See [`simulator_progression.md` §1](simulator_progression.md).
- **No scoring, no persistence, no accuracy stats.** Out of scope, and
  `simulator_progression.md` argues at length about why that needs its own
  design.
- **Never more than one pattern**, and no hover tooltips — the simulator is a
  touch-first single screen that never scrolls.

### A note on information leakage

The label is visible in `decide` mode, before the player commits. This is not
a leak: the pattern is computed **only from bars already drawn on screen**, so
it names something the player can already see. Naming it is the entire teaching
value. What must never happen is the annotation reading a bar the player
cannot — §5.4 makes that a hard invariant with a test attached.

---

## 2. Files

| File | Action |
|---|---|
| `web/v2/js/sim-patterns.js` | **new** — pure detection + state machine |
| `tests/web/sim-patterns.test.js` | **new** — unit tests (`node --test`) |
| `web/v2/js/simulator.js` | modify — 5 named hook points, §9 |
| `web/v2/css/cockpit.css` | modify — `.sim-pat-*` block, §8.5 |
| `scripts/tools/pattern_census.mjs` | **new** — one-off calibration, §13 |
| `CHANGELOG.md` | modify — new dated section |
| `.claude/skills/macro-beans-site/SKILL.md` | modify — file map + cheatsheet row |

`sim-patterns.js` must be **pure**: no DOM, no `fetch`, no `import` other than
from `sim-indicators.js`. It is unit-tested under Node, like its two siblings.

---

## 3. The data contract

```js
/**
 * @typedef {Object} Pattern
 * @property {string}  id          // "bull-engulfing" — stable, kebab-case
 * @property {string}  label       // "BULL ENGULFING" — drawn as-is, <= 18 chars
 * @property {"bull"|"bear"|"neutral"} bias
 * @property {"reversal"|"continuation"|"indecision"} kind
 * @property {PatternState} state
 * @property {number}  startIdx    // first bar of the pattern
 * @property {number}  endIdx      // last bar PRESENT (see `forming`)
 * @property {number}  size        // bars a COMPLETE instance needs (1|2|3)
 * @property {number}  hi          // highest high across [startIdx..endIdx]
 * @property {number}  lo          // lowest low across [startIdx..endIdx]
 * @property {number|null} trigger     // close beyond this => confirmed
 * @property {number|null} invalidate  // close beyond this => failed
 * @property {number|null} target      // measure-rule projection
 * @property {number|null} resolvedIdx // bar that confirmed or failed it
 */

/** @typedef {"forming"|"complete"|"confirmed"|"failed"|"aborted"|"expired"} PatternState */
```

`null` is the sixth outcome: **no pattern**. It is the common case and must
render as nothing at all — no empty label, no placeholder.

### Exports

```js
export function detectPattern(bars, atr, anchorIdx, opts = {});  // -> Pattern | null
export function resolvePattern(pattern, bars, throughIdx);       // -> Pattern | null
export const PATTERNS;      // the ordered catalogue, §6
export const PATTERN_IDS;   // string[] — for ?p=<id> validation and tests
```

`bars` are the simulator's bar objects: `{d, o, h, l, c, v}`. `atr` is the
`atr(bars, 14)` array from `sim-indicators.js` — same length, leading `null`s.

`resolvePattern` is **pure and idempotent**: same inputs, same output; a
pattern already in a terminal state is returned unchanged (identity is fine).

---

## 4. Candle metrics — the threshold system

Adopt TA-Lib's relative-threshold scheme wholesale. Every notion of "long",
"short" and "near" is a multiple of a trailing average, so the same rules work
on a $9 stock and a $900 one. Do **not** use fixed percentages anywhere.

### 4.1 Per-bar primitives

```js
const body  = (b) => Math.abs(b.c - b.o);
const upper = (b) => b.h - Math.max(b.o, b.c);
const lower = (b) => Math.min(b.o, b.c) - b.l;
const hl    = (b) => b.h - b.l;
const top   = (b) => Math.max(b.o, b.c);   // top of the real body
const base  = (b) => Math.min(b.o, b.c);   // bottom of the real body
const isUp  = (b) => b.c >= b.o;           // "white" in TA-Lib's language
const isDn  = (b) => b.c <  b.o;           // "black"
```

### 4.2 The settings table

Verbatim from TA-Lib's `ta_global.c`. `range` picks which primitive is
averaged; `n` is the averaging period; `f` the multiplier.

```js
export const CANDLE = {
  bodyLong:        { range: "body",    n: 10, f: 1.0  },
  bodyVeryLong:    { range: "body",    n: 10, f: 3.0  },
  bodyShort:       { range: "body",    n: 10, f: 1.0  },
  bodyDoji:        { range: "hl",      n: 10, f: 0.1  },
  shadowLong:      { range: "body",    n:  0, f: 1.0  },
  shadowVeryLong:  { range: "body",    n:  0, f: 2.0  },
  shadowShort:     { range: "shadows", n: 10, f: 1.0  },
  shadowVeryShort: { range: "hl",      n: 10, f: 0.1  },
  near:            { range: "hl",      n:  5, f: 0.2  },
  far:             { range: "hl",      n:  5, f: 0.6  },
  equal:           { range: "hl",      n:  5, f: 0.05 },
};
```

`shadows` = `upper(b) + lower(b)`.

### 4.3 `avg(kind, bars, i)`

Two behaviours, and conflating them is the classic way a home-grown detector
goes wrong:

```
n === 0  ->  f * rangeOf(kind.range, bars[i])
              // compared to THIS bar. "long shadow" means longer than
              // this candle's own body, not longer than usual.

n  >  0  ->  f * mean( rangeOf(kind.range, bars[j]) for j in [i-n, i-1] )
              // the n bars STRICTLY BEFORE i. Bar i is never in its own
              // average — TA-Lib accumulates [i-n, i-1] and shifts.
```

Return `null` when `i - n < 0`. Any rule that reads a `null` average fails
closed (no pattern), never throws and never treats `null` as `0`.

### 4.4 Warm-up

A pattern at bar `e` needs `e - size - 10 >= 0` for its averages and
`e - size - TREND_N - 1 >= 0` for its trend gate (§5). The simulator always
has 200+ bars of history before `dIdx`, so this never binds in production —
but `detectPattern` must still return `null` rather than `NaN` when it does,
because the tests will hand it short arrays deliberately.

---

## 5. The trend gate — mandatory

TA-Lib does not check trend and says so in its own source comments (research
note §2.3). A reversal pattern with no prior trend is not a weak signal, it is
**not the pattern**: the meaning of a hammer is rejection at the low of a move,
and with no move there is nothing to reject. Shipping TA-Lib's rules ungated
produces textbook-looking false positives, which is the worst possible failure
mode for a training tool.

### 5.1 Definition

```js
const TREND_N   = 10;   // bars of prior move measured
const TREND_ATR = 1.5;  // threshold, in units of ATR(14)

/** "up" | "down" | "flat" | null(insufficient history), for the run of bars
 *  ending immediately BEFORE the pattern's first bar. */
function trendBefore(bars, atr, startIdx) {
  const j = startIdx - 1;
  if (j - TREND_N < 0) return null;
  const a = atr[j];
  if (a == null || !(a > 0)) return null;
  const move = (bars[j].c - bars[j - TREND_N].c) / a;
  if (move >=  TREND_ATR) return "up";
  if (move <= -TREND_ATR) return "down";
  return "flat";
}
```

ATR-normalising is what makes one threshold work across the whole S&P 500, and
`atr(bars, 14)` is already computed in `indicatorsFor()` — pass it in rather
than recomputing.

### 5.2 The gate

| `kind` | Required `trendBefore` |
|---|---|
| `reversal`, bullish | `"down"` |
| `reversal`, bearish | `"up"` |
| `continuation`, bullish | `"up"` |
| `continuation`, bearish | `"down"` |
| `indecision` | none — any trend, including `"flat"` |

`"flat"` rejects every directional pattern. `null` rejects everything.

### 5.3 Do not measure the trend across the pattern

`trendBefore` reads bars up to `startIdx - 1`. A three-bar bullish pattern
whose own candles rally hard must not be allowed to count that rally as the
"prior downtrend" — that is the bug this signature exists to prevent.

### 5.4 Hard invariant: no look-ahead

`detectPattern(bars, atr, A)` may read `bars[j]` and `atr[j]` **only for
`j <= A`**, and the returned `endIdx` must satisfy `endIdx <= A`.
`resolvePattern(p, bars, T)` may read only `j <= T`.

There is a mandatory test for this (§12). A simulator that quietly peeks at
tomorrow is worse than one with no patterns at all, and nothing on screen would
say so.

---

## 6. The pattern catalogue

Seventeen signed entries across twelve families — Finviz's proven retail set
(research note §1), split by direction. This is the whole catalogue; adding to
it is a separate change with its own calibration run.

Notation: `e` is the index of the pattern's **last** bar; `b(k)` is
`bars[e - k]`; `A(kind, k)` is `avg(CANDLE.kind, bars, e - k)`.

### 6.1 One-bar patterns

**`hammer`** — BULL · reversal · "HAMMER"
```
body(b0)  <  A(bodyShort, 0)
body(b0)  >  A(bodyDoji, 0)                    // not a doji; keeps §7 exclusive
lower(b0) >  A(shadowLong, 0)                  // > this bar's own body
upper(b0) <  A(shadowVeryShort, 0)
base(b0)  <= b1.l + A(near, 1)                 // body sits near the prior low
```

**`hanging-man`** — BEAR · reversal · "HANGING MAN" — the same shape, separated
only by the trend gate. TA-Lib's mirror of the last line:
```
…as hammer, except:  base(b0) >= b1.h - A(near, 1)
```

**`inverted-hammer`** — BULL · reversal · "INV HAMMER"
```
body(b0)  <  A(bodyShort, 0)
body(b0)  >  A(bodyDoji, 0)
upper(b0) >  A(shadowLong, 0)
lower(b0) <  A(shadowVeryShort, 0)
top(b0)   <= base(b1) + A(near, 1)
```
> **Deviation.** TA-Lib requires a hard gap down from the prior body. On daily
> US equities that is rare enough to make the pattern invisible. The `near`
> test above ("at or near the prior body's low") mirrors the hammer's own
> proximity test and is the same relaxation applied to piercing and the stars.

**`shooting-star`** — BEAR · reversal · "SHOOTING STAR"
```
…as inverted-hammer, except:  base(b0) >= top(b1) - A(near, 1)
```

**`marubozu-bull` / `marubozu-bear`** — continuation · "BULL MARUBOZU" /
"BEAR MARUBOZU"
```
body(b0)  >  A(bodyLong, 0)
upper(b0) <  A(shadowVeryShort, 0)
lower(b0) <  A(shadowVeryShort, 0)
bias = isUp(b0) ? "bull" : "bear"
```

**`doji`** — NEUTRAL · indecision. No trend gate.
```
body(b0) <= A(bodyDoji, 0)
```
Label by shadow shape:
- `lower > 2*upper && upper < A(shadowVeryShort,0)` → `"DRAGONFLY DOJI"`
- `upper > 2*lower && lower < A(shadowVeryShort,0)` → `"GRAVESTONE DOJI"`
- otherwise → `"DOJI"`

The id stays `doji` in all three cases; only `label` changes.

### 6.2 Two-bar patterns

**`bull-engulfing`** — BULL · reversal · "BULL ENGULFING" — TA-Lib's rule plus
two size floors TA-Lib omits (without them, a speck engulfing a smaller speck
qualifies):
```
isUp(b0) && isDn(b1)
( (b0.c >= b1.o && b0.o <  b1.c) ||
  (b0.c >  b1.o && b0.o <= b1.c) )              // body covers body
!(b0.o === b1.c && b0.c === b1.o)               // not a perfect tie on both
body(b0) > A(bodyShort, 0)                      // ADDED: engulfer isn't tiny
body(b1) > A(bodyDoji, 1)                       // ADDED: something to engulf
```

**`bear-engulfing`** — BEAR · reversal · "BEAR ENGULFING" — mirror
(`isDn(b0) && isUp(b1)`, comparisons flipped).

**`bull-harami`** — BULL · reversal
```
isDn(b1) && body(b1) >  A(bodyLong, 1)          // 1st: long and black
             body(b0) <= A(bodyShort, 0)        // 2nd: short
top(b0)  < top(b1) && base(b0) > base(b1)       // 2nd body inside the 1st
```
Label: `"BULL HARAMI CROSS"` when `body(b0) <= A(bodyDoji, 0)`, else
`"BULL HARAMI"`. Id stays `bull-harami`.

**`bear-harami`** — BEAR · reversal — mirror (`isUp(b1)`), labels
`"BEAR HARAMI CROSS"` / `"BEAR HARAMI"`.

**`piercing`** — BULL · reversal · "PIERCING LINE"
```
isDn(b1) && body(b1) > A(bodyLong, 1)
isUp(b0) && body(b0) > A(bodyLong, 0)
b0.o < b1.c                                     // opens below the prior close
b0.c < b1.o                                     // still inside the prior body
b0.c > b1.c + body(b1) * PENETRATION_2BAR       // past its midpoint
```
`PENETRATION_2BAR = 0.5`.
> **Deviation.** TA-Lib requires `b0.o < b1.l` — a gap below the prior *low*.
> Relaxed to the prior *close*, which is Nison's formulation and the one every
> retail source teaches. The `b0.c < b1.o` line is what keeps piercing and
> engulfing mutually exclusive.

**`dark-cloud`** — BEAR · reversal · "DARK CLOUD" — mirror:
```
isUp(b1) && body(b1) > A(bodyLong, 1)
isDn(b0) && body(b0) > A(bodyLong, 0)
b0.o > b1.c
b0.c > b1.o
b0.c < b1.c - body(b1) * PENETRATION_2BAR
```

### 6.3 Three-bar patterns

**`morning-star`** — BULL · reversal
```
isDn(b2) && body(b2) >  A(bodyLong, 2)          // 1st: long black
            body(b1) <= A(bodyShort, 1)         // 2nd: short
top(b1) < base(b2) + A(near, 2)                 // 2nd gaps (or nearly) below
isUp(b0) && body(b0) >  A(bodyShort, 0)         // 3rd: not short, white
b0.c > b2.c + body(b2) * PENETRATION_3BAR       // closes well into the 1st body
```
`PENETRATION_3BAR = 0.30` (TA-Lib's default).
Label: `"MORNING DOJI STAR"` when `body(b1) <= A(bodyDoji, 1)`, else
`"MORNING STAR"`. Id stays `morning-star`.
> **Deviation.** TA-Lib requires a strict body gap (`top(b1) < base(b2)`). The
> `+ A(near, 2)` tolerance keeps the pattern findable on daily US equities,
> which gap far less than the Japanese rice market the rule came from.

**`evening-star`** — BEAR · reversal — mirror; labels `"EVENING DOJI STAR"` /
`"EVENING STAR"`.

**`three-white-soldiers`** — BULL · reversal · "3 WHITE SOLDIERS" — TA-Lib
verbatim:
```
isUp(b2) && isUp(b1) && isUp(b0)
upper(b2) < A(shadowVeryShort,2) && upper(b1) < A(shadowVeryShort,1)
                                 && upper(b0) < A(shadowVeryShort,0)
b0.c > b1.c && b1.c > b2.c                      // consecutive higher closes
b1.o > b2.o && b1.o <= b2.c + A(near, 2)        // each opens within/near the prior body
b0.o > b1.o && b0.o <= b1.c + A(near, 1)
body(b1) > body(b2) - A(far, 2)                 // not "far shorter" — excludes advance block
body(b0) > body(b1) - A(far, 1)
body(b0) > A(bodyShort, 0)                      // not short
```

**`three-black-crows`** — BEAR · reversal · "3 BLACK CROWS" — mirror.

---

## 7. One pattern per chart

Multiple definitions match the same bars constantly. The catalogue is designed
so most overlaps are impossible (hammer/hanging-man are trend-separated;
piercing and engulfing are mutually exclusive by construction; hammer and doji
by the `bodyDoji` floor), but three-bar patterns still contain two-bar ones and
neutral candles are everywhere. Selection must be **total and deterministic**.

### 7.1 The window

```js
const RECENCY = 3;   // a pattern's last bar must be within RECENCY-1 of the anchor
```
Consider every completed match whose `e` satisfies
`anchor - (RECENCY - 1) <= e <= anchor`.

### 7.2 Forming candidates

For each multi-bar pattern, also test whether its **first `size - 1` bars**
match, ending exactly at `anchor` — the pattern needs one more session and it
is not there yet. Concretely, evaluate every clause of the rule that mentions
only `b(size-1) … b(1)`, plus the trend gate. Any clause referencing `b0` is
skipped.

Forming candidates are only produced for `size >= 2`, and only at `e === anchor`.

### 7.3 Precedence

Sort all candidates by these keys in order; take the first.

1. **Directional beats neutral.** `bias !== "neutral"` first, always,
   regardless of recency. A doji on the decision bar must never displace a
   morning star that completed two sessions ago — the doji is the most common
   candle in the catalogue and would otherwise become wallpaper.
2. **Completed beats forming.** A pattern that happened outranks one that
   might.
3. **Recency.** Larger `e` wins.
4. **Size.** Larger `size` wins — the three-bar reading of the same bars is
   the more specific claim.
5. **Catalogue rank.** The order patterns are declared in `PATTERNS`, which
   must be, best first:
   `three-white-soldiers, three-black-crows, morning-star, evening-star,
    piercing, dark-cloud, bull-engulfing, bear-engulfing, hammer,
    shooting-star, inverted-hammer, hanging-man, bull-harami, bear-harami,
    marubozu-bull, marubozu-bear, doji`
   (roughly Bulkowski's overall-performance order, research note §3.1, with
   the low-information continuation and indecision candles last.)

Ties beyond key 5 are impossible: each id appears once.

---

## 8. States

### 8.1 The machine

```
                     ┌──────────┐
    (size-1 bars)───▶│ FORMING  │
                     └────┬─────┘
              final bar   │   final bar
                 matches  │   does not match
                     ┌────▼─────┐        ┌─────────┐
    (all bars)──────▶│ COMPLETE │        │ ABORTED │◀──┘
                     └────┬─────┘        └─────────┘
        close beyond      │      close beyond
        trigger           │      invalidate
                     ┌────▼─────┐  ┌────────┐  ┌─────────┐
                     │CONFIRMED │  │ FAILED │  │ EXPIRED │
                     └──────────┘  └────────┘  └─────────┘
                                     ▲              ▲
                         (invalidation checked      │
                          before trigger)     CONFIRM_WINDOW
                                              bars, neither hit
```

`confirmed`, `failed`, `aborted` and `expired` are **terminal and frozen**. A
confirmed pattern that later reverses is not relabelled — it confirmed, and
what the trade did next is the trader's problem, not the pattern's.

### 8.2 Levels

Computed over `[startIdx .. endIdx]` once the pattern is complete (and
provisionally, over the bars present, while forming):

```js
height = hi - lo;
bull:    trigger = hi,  invalidate = lo,  target = hi + height
bear:    trigger = lo,  invalidate = hi,  target = lo - height
neutral: trigger = invalidate = target = null
```

This is Bulkowski's measure rule for candles: pattern height projected from
the breakout price (research note §3.4). Breakout is the top of the pattern
for a bullish reading, its bottom for a bearish one.

### 8.3 `resolvePattern(p, bars, T)`

```
if p == null or p.state is terminal            -> return p unchanged

if p.state === "forming":
    k = p.endIdx + 1
    if k > T                                   -> return p unchanged
    re-run the full rule for this id at e = k
    match     -> p.state = "complete"; p.endIdx = k; recompute hi/lo/levels;
                 fall through to the "complete" scan below, from k+1
    no match  -> p.state = "aborted"; return

if p.state === "complete":
    for j from p.endIdx+1 to min(T, p.endIdx + CONFIRM_WINDOW):
        # invalidation FIRST — see below
        if bull && bars[j].c < p.invalidate  -> failed at j; return
        if bear && bars[j].c > p.invalidate  -> failed at j; return
        if bull && bars[j].c > p.trigger     -> confirmed at j; return
        if bear && bars[j].c < p.trigger     -> confirmed at j; return
    if T >= p.endIdx + CONFIRM_WINDOW         -> expired
```

`CONFIRM_WINDOW = 3`. Classical practice waits for the *next* candle; three
gives the pattern a fair hearing without letting the label hang around all
hand.

Two decisions worth not reversing:

- **Closes, not intraday touches.** The simulator's whole model is "you decide
  on the close". A stop fills intraday because it is a live order; a pattern
  confirmation is an observation, and observations happen at the close. Using
  intraday extremes here would also make confirmation and failure fire on the
  same bar constantly.
- **Invalidation is tested before the trigger.** On a bar that closes beyond
  both (possible when `height` is small relative to the bar), assume the bad
  outcome. This mirrors `stopFill()` in `sim-engine.js`, which fills a gapped
  stop at the open rather than the stop price for exactly the same reason.

`neutral` patterns have no levels: they go `complete` → `expired` after
`CONFIRM_WINDOW` and never confirm or fail. A doji claims nothing, so there is
nothing for the market to prove.

---

## 9. Rendering

All drawing is in `renderChart()` in `simulator.js`. The chart already owns
`cx(i)`, `yPrice(v)`, `slot`, `bodyW`, `PAD`, panel `P` and the
`sim-clip-price` clip path — reuse them, add no geometry helpers.

### 9.1 The bracket

Emitted **after the price grid, before the moving averages**, so candles and
lines draw on top of it.

```js
const x0 = Math.max(PAD.l, cx(p.startIdx) - bodyW / 2 - 3);
const x1 = Math.min(W - PAD.r, cx(p.endIdx) + bodyW / 2 + 3);
const y0 = yPrice(p.hi) - 4;
const y1 = yPrice(p.lo) + 4;
// <rect class="sim-pat-box sim-pat-<bias> sim-pat-<state>"
//       clip-path="url(#sim-clip-price)" x y width height rx="2"/>
```

`fill:none`; a filled box would muddy the candles on this dark ground. Clamp
rather than skip when the pattern runs off the left edge — a half-bracket still
says "the pattern starts before the window".

### 9.2 The label

Top-**right** of the price panel, right-anchored. The top-left corner is taken
by the 9EMA/22EMA/200SMA legend and the off-scale-200SMA note.

```js
out += text(W - PAD.r - 3, P.top + 9,
            `${p.label} · ${p.state.toUpperCase()}`,
            `sim-pat-label sim-pat-${p.bias} sim-pat-${p.state}`, "end");
```

On a narrow chart (`W < 340`) drop the ` · STATE` suffix — the bracket's stroke
style still distinguishes forming from complete.

### 9.3 The expectation signal

The bracket already **is** the trigger and invalidation: its top edge is one
level and its bottom edge the other. Do not draw separate ticks for them; that
is the same information twice on a chart that has none to spare.

What is missing is the **target** — what a working pattern would be expected
to reach. Draw it only while the claim is live and directional, i.e.
`state ∈ {forming, complete, confirmed}` and `bias !== "neutral"`:

```js
const ty = yPrice(p.target);
// dotted tick spanning the last ~3 slots, ending at the plot's right edge:
//   <line class="sim-pat-target sim-pat-<bias> sim-pat-<state>"
//         x1=W-PAD.r-slot*3  x2=W-PAD.r  y1=ty y2=ty/>
// plus a caret at the right end: "▲" for bull, "▼" for bear, class sim-pat-tgt-text
```

On `failed`, `aborted` and `expired`, draw **nothing** — the claim is dead and
a target still hanging there would be a lie. On `confirmed`, draw it dimmed
(the CSS handles this); the expectation is still live but the reader has the
answer.

**Off-scale targets.** A target one pattern-height beyond the breakout will
often sit outside `[lo, hi]`. **Do not add `p.target` to `consider()`** —
squashing every candle to fit a hypothesis is the wrong trade. Reuse the idiom
already in `renderChart()` for the off-scale 200SMA: a small text at the panel
edge instead.

```js
if (p.target > hi || p.target < lo) {
  const away = ((p.target - bars[to].c) / bars[to].c) * 100;
  const ly = p.target > hi ? P.top + 20 : P.bot - 3;   // +20 clears the label
  out += text(W - PAD.r - 3, ly,
              `TGT ${p.target > hi ? "▲" : "▼"} ${fmtPx(p.target)} (${fmtPct(away)})`,
              `sim-pat-tgt-text sim-pat-${p.bias}`, "end");
}
```

### 9.4 Nothing else

No pattern marker in the volume, MACD or RSI panels. No legend entry. No
change to `renderStatus()` or `renderActions()`.

### 9.5 CSS

Append one block to `web/v2/css/cockpit.css`, after the existing simulator
rules. Bias sets the colour; **state classes come last so they win**.

```css
/* ---- candlestick patterns ---- */
.sim-pat-box{ fill:none; stroke-width:1; opacity:.5; }
.sim-pat-label{ font-family:var(--mono); font-size:9px; letter-spacing:.06em; }
.sim-pat-target{ fill:none; stroke-width:1; stroke-dasharray:1 3; opacity:.7; }
.sim-pat-tgt-text{ font-family:var(--mono); font-size:9px; }

.sim-pat-bull{ stroke:var(--win);  fill:var(--win);  }
.sim-pat-bear{ stroke:var(--loss); fill:var(--loss); }
.sim-pat-neutral{ stroke:var(--dim); fill:var(--dim); }

/* state overrides — declared after bias so they cascade over it */
rect.sim-pat-forming{ stroke-dasharray:3 3; opacity:.35; }
text.sim-pat-forming{ opacity:.6; }
rect.sim-pat-confirmed{ stroke-width:1.4; opacity:.8; }
line.sim-pat-confirmed{ opacity:.35; }
.sim-pat-failed, .sim-pat-aborted, .sim-pat-expired{
  stroke:var(--dim); fill:var(--dim); opacity:.45;
}
```

Element-qualified selectors (`rect.` / `text.` / `line.`) keep the three
annotation parts independently styleable from one shared state class.

---

## 10. Wiring into `simulator.js`

Five edits, all small.

**H1 — import**, beside the existing sibling imports:
```js
import { detectPattern, resolvePattern, PATTERN_IDS } from "./sim-patterns.js";
```

**H2 — detect once, at deal time.** In `newSession()`, after
`const ind = indicatorsFor(bars);`, add `pattern` to the `S` object:
```js
pattern: params.get("p") === "0" ? null : detectPattern(bars, ind.atr, dIdx),
```
Detection is **pinned**: run once per deal, never re-run. A label that churns
as you tap `+1 DAY` teaches nothing, and a pattern you have already acted on is
the one whose fate you want to watch. Its *state* evolves; its identity does
not.

**H3 — resolve on every render.** First line of `render()`, before
`renderStatus()`:
```js
S.pattern = resolvePattern(S.pattern, S.bars, S.curIdx);
```
One hook covers every path that moves `curIdx` — `takePosition`, `advanceDay`,
`pass` (which jumps 20 sessions at once, hence the loop in §8.3). It is
idempotent and terminal states short-circuit, so the repeated calls cost
nothing. Note `paintStop()` deliberately does not call `render()`, so dragging
the stop cannot disturb the annotation.

**H4 — draw.** Three insertions in `renderChart()` per §9.1–9.3, each guarded
by `if (S.pattern) { … }`.

**H5 — debug hook.** Extend `window.__sim`:
```js
pattern: () => S.pattern,
```

### 10.1 `?p=` — deal a pattern on demand

Pairs with the existing `?t=<TICKER>&d=<ISO date>` fixed-hand params, which the
site skill documents as the way to test the simulator.

- `?p=0` — patterns off entirely (also the kill switch if this ships badly).
- `?p=<id>` — deal until a hand carries that pattern. Validate against
  `PATTERN_IDS`; an unknown id is ignored with a `console.warn`.

Implementation: for each of up to 6 candidate tickers, walk the eligible
decision range and take the first index where `detectPattern` returns that id.
Give up after 6 tickers, deal normally, and `console.warn` — a rare pattern on
a small sample legitimately may not be there.

---

## 11. Worked example

`TSLA`, decision day a Thursday. The prior 10 sessions fell 2.4 ATR — trend
`down`, so bullish reversals are eligible. Bars `d-1` and `d`:

```
d-1:  o 214.80  h 216.10  l 205.30  c 206.40   long black body
d  :  o 205.90  h 213.20  l 204.10  c 212.85   white, engulfs it
```

`bull-engulfing` matches: `isUp(d) && isDn(d-1)`, `c[d] (212.85) >= o[d-1]
(214.80)`? No — so the first disjunct fails; the second needs
`c[d] > o[d-1]`, also false. **Not an engulfing.** Body 206.40→214.80 is not
covered.

Change `c[d]` to `215.40` and it matches. Then:

```
startIdx = d-1, endIdx = d, size = 2
hi = 216.10, lo = 204.10, height = 12.00
trigger = 216.10, invalidate = 204.10, target = 228.10
state = "complete"     (its last bar IS the decision bar)
```

Chart: a green bracket around the two candles spanning 204.10–216.10; the label
`BULL ENGULFING · COMPLETE` top-right; the target at 228.10 is above the price
scale, so `TGT ▲ 228.10 (+5.9%)` appears at the panel edge instead.

The player buys. Entry fills at the next open. Three sessions later:

- closes 214.20, 215.05, 217.60 → the third closes above 216.10 →
  **`confirmed`** at that bar. Bracket thickens, target dims.
- closes 214.20, 209.90, 203.40 → the third closes below 204.10 →
  **`failed`**. Bracket and label go grey, target disappears.
- closes 214.20, 215.05, 213.90 → neither level taken in three sessions →
  **`expired`**. Same grey treatment.

The trade continues in all three cases. The pattern annotation never touches
the stop, the fills, or the P&L — it is commentary, not a control.

---

## 12. Tests — `tests/web/sim-patterns.test.js`

`npm test` runs `node --test tests/web/*.test.js` and must stay green. Match
the house style in `sim-indicators.test.js`: a comment at the top saying why
the fixtures are what they are, then `node:assert/strict`.

**Fixtures.** A builder that takes `[o,h,l,c]` tuples and prepends a synthetic
preamble long enough to (a) seed the 10-bar averages with a known baseline and
(b) establish the trend the gate requires. Three preambles: `down` (a steady
2-ATR slide), `up`, `flat` (a tight range). Volume and dates can be constant.

**Required cases:**

| Group | Count | What |
|---|---|---|
| Positives | 17 | one clean instance of each catalogue entry, right preamble |
| Near-misses | 17 | one clause broken per pattern → `null` or a different id |
| Trend gate | 14 | each directional pattern's candles on a `flat` preamble → not that id |
| Precedence | ≥5 | doji vs directional; harami inside a morning star; two-bar inside three-bar; forming vs completed; recency |
| States | ≥8 | complete→confirmed, →failed, →expired; forming→complete, →aborted; both-levels-breached→failed; terminal states frozen under further `resolvePattern` calls |
| Invariants | ≥4 | no look-ahead; `endIdx <= anchorIdx`; short arrays → `null`, never a throw; `resolvePattern` idempotent |

**The look-ahead test is mandatory and must be written first:**

```js
test("detectPattern never reads past the anchor", () => {
  const full  = detectPattern(bars, atrFull, A);
  const trunc = detectPattern(bars.slice(0, A + 1), atrFull.slice(0, A + 1), A);
  assert.deepEqual(trunc, full);
});
```

Run it over several anchors on a long random-ish series, not one hand-picked
index.

---

## 13. Calibration — `scripts/tools/pattern_census.mjs`

A one-off Node ESM script, not wired into CI or `deploy.yml`. It imports
`sim-patterns.js` and `sim-indicators.js` directly (no port, no drift), reads
`web/v2/data/sim/*.json`, and runs `detectPattern` at **every** eligible
decision index across the whole universe.

Those JSON files are gitignored, so build them first:
```bash
python -m src.data.refresh --tickers-file config/sp500.csv --start 2018-01-01
/usr/local/bin/python3 scripts/site/build_sim.py
node scripts/tools/pattern_census.mjs
```

It prints four things: the share of decision points carrying a pattern, the
distribution by id, the split of `forming` vs `complete` at the decision bar,
and — running `resolvePattern` forward — the confirmed / failed / expired split
per pattern.

### Acceptance bands

| Measure | Band | Why |
|---|---|---|
| Decision points with a pattern | **35 %–60 %** | below 35 % the feature is invisible; above 60 % it is wallpaper |
| Largest single pattern's share | **≤ 25 %** | one dominant id means one over-loose rule |
| Every shipped pattern's share | **≥ 0.3 %** | rarer than this and it can never be seen in practice — cut it or loosen it |
| `forming` share of hits | **5 %–20 %** | a real state, not a curiosity and not the norm |

If out of band, tune in this order: `RECENCY`, then `TREND_ATR`, then cut the
loosest patterns from the catalogue. **Do not take `TREND_ATR` below 1.0** —
below that the gate stops gating and §5's whole argument collapses.

Paste the census output into the PR body and append it to this document under
a `## Calibration results` heading, dated.

The confirmed/failed split is worth reading even though nothing depends on it.
Bulkowski's measured reversal rates run 59–82 % (research note §3.1) and the
academic evidence is weaker still; a census showing 90 % confirmation would
mean the confirmation test is trivially satisfied, not that the patterns work.

---

## 14. Acceptance checklist

- [ ] `sim-patterns.js` has no DOM, no `fetch`, and imports nothing but `sim-indicators.js`.
- [ ] `npm test` green; `tests/web/sim-patterns.test.js` covers every group in §12.
- [ ] The look-ahead test exists and passes across multiple anchors.
- [ ] Every threshold in §4.2 is a named constant; no fixed percentages anywhere.
- [ ] The trend gate is applied to all 16 directional patterns.
- [ ] Never more than one pattern; selection is total and deterministic.
- [ ] All six states reachable, and demonstrated by tests.
- [ ] `null` (no pattern) renders as nothing at all.
- [ ] Detection is pinned at deal time; the label does not change identity mid-hand.
- [ ] `p.target` is **not** in `consider()`; off-scale targets use the edge label.
- [ ] No new status chips; `.sim-status` unchanged.
- [ ] Page still fills `100dvh` and never scrolls, portrait and landscape phone.
- [ ] `?p=0` fully disables the feature; `?p=<id>` deals that pattern.
- [ ] `window.__sim.pattern()` returns the live pattern.
- [ ] `build_sim.py`, `deploy.yml`, `.gitignore` and `nav.js` untouched.
- [ ] Census run, output in the PR body and appended to §13, all bands met.
- [ ] `CHANGELOG.md` updated; the SKILL.md file map and cheatsheet mention `sim-patterns.js`.

---

## 15. Deliberately out of scope

Candidates for a later pass, listed so they are not smuggled into this one:

- **A recap-mode chip.** `recap` runs four chips and has room for
  `PATTERN  BULL ENGULFING · FAILED`. Genuinely useful — "you traded a failed
  hammer" is a real lesson — but it needs its own look at the strip's budget.
- **Tap-to-explain.** Tapping the label showing one line on what the pattern
  claims. TradingView does this with tooltips; the simulator would need a
  touch-friendly equivalent.
- **Bulkowski's context boosts.** Patterns within a third of the yearly
  high/low perform materially better, as do taller candles. Both are cheap to
  compute and would sharpen the catalogue — but they change hit rates, so they
  need their own census.
- **Spot-it-yourself mode.** Hiding the label until the player has decided,
  behind the same affordance as the ticker's `TAP TO REVEAL`. Arguably the
  better teaching tool, and arguably a different product.
- **A tick on the resolving bar.** A 4px mark at the bar that confirmed or
  failed the pattern. Cheap, but the chart is crowded and this can wait until
  the annotation has been lived with.
- **More patterns.** Tweezers, three inside up/down, rising/falling three
  methods, spinning top, high wave. Each addition needs a fresh census run;
  seventeen is a set a person can actually learn.
