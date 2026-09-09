# Simulator chart patterns — implementation specification

Implementation spec for **chart pattern** recognition on the swing-trading
simulator (`web/v2/simulator.html`): triangles, wedges, flags, channels, double
tops and bottoms, head-and-shoulders, and support / resistance levels.

Evidence and design rationale are in
[`chart_pattern_research.md`](chart_pattern_research.md). Read it first —
several constants below are calibration targets rather than truths, and the
research note says which.

Single-candle patterns (engulfings, hammers, stars) are **tier 2** of this
design, not the subject. Their catalogue and rules live in
[`candlestick_pattern_spec.md`](candlestick_pattern_spec.md); §8 here supersedes
that document's own selection rules and renames its module.

Read [`.claude/skills/macro-beans-site/SKILL.md`](../../.claude/skills/macro-beans-site/SKILL.md)
§"Work on the simulator" before starting. Its two rules bind this work: **keep
the math out of the page module**, and **lay the bars out before measuring the
chart**.

---

## 0. Two decisions to take before writing code

### 0.1 The lookback window — a product decision

The simulator shows `LOOKBACK = 35` sessions when you decide. Research note §8:
that is a *flag-and-level* window. Triangles and wedges appear only at their
short end, head-and-shoulders is rare, cup-and-handle is impossible.

| | **Tier A — keep `LOOKBACK = 35`** | **Tier B — widen to 60** |
|---|---|---|
| Catalogue | flags, pennants, short triangles and wedges, rectangles, channels, double tops/bottoms, small H&S, S/R levels | adds cup-and-handle, broadening formations, triple tops/bottoms, full-size H&S |
| Hit rate | lower; the census in §13 decides if it is viable | materially higher |
| Cost | none | candles narrow from ~9.7px to ~5.7px of slot on a phone; the decision exercise changes character |

**Build Tier A.** It is the smaller change, it keeps the simulator's feel
intact, and §13's census produces the number that would justify Tier B. Do not
widen `LOOKBACK` speculatively — widen it if and only if the census shows Tier A
firing below its band.

Everything below is Tier A unless marked **[Tier B]**.

### 0.2 Forward space on the chart — a required layout change

A forecast zone projects *forward in time*, and in `decide` mode the chart's
right edge is the decision bar. There is nowhere to draw it.

Fix, in `renderChart()`:

```js
const FORWARD_SLOTS = 8;                      // reserved future space
const slot = plotW / (n + FORWARD_SLOTS);     // was: plotW / n
```

This is the conventional charting layout — every platform surveyed leaves room
to the right — and it must be **unconditional**, not applied only when a
pattern has a zone, or the candle width would jump between deals. Knock-ons:
`cx()`, the decision divider, the stop line and every marker keep working
unchanged; the stop line now crosses the forward gutter, which is correct and
reads better. Candles narrow by ~18%; `bodyW`'s existing
`clamp(1.4, slot*0.62, 9)` absorbs it.

---

## 1. What ships

At most **one** pattern annotation per deal:

1. **The shape** — the pattern's own trendlines, neckline or level, with a
   faint fill between them.
2. **A label** — one line of 9px text naming the pattern and its state.
3. **A forecast zone** — a shaded band projected forward in time, bounded by
   Bulkowski's statistical target and the textbook measured move, and
   time-boxed to the pattern's own duration (Autochartist's construction,
   research note §1).

Plus a state that evolves as the hand plays out: `forming` → `broken-out` →
`confirmed` / `failed` / `throwback` / `expired`.

### Non-goals

- **Simulator chart only.** Nothing in `price-sheet.html`, `charts.html`, the
  scanner, or v1.
- **No build-step or data change.** Detection is client-side from OHLC already
  in `web/v2/data/sim/<TICKER>.json`. Do not touch `build_sim.py`,
  `deploy.yml`, `.gitignore` or `nav.js`.
- **No new status chips.** `.sim-status` is capped at 52px (30px landscape) and
  `trade` mode already fits six. The annotation lives in the chart.
- **No scoring, no persistence, no hover tooltips.**
- **Never more than one pattern**, across all three tiers.

---

## 2. Files

| File | Action |
|---|---|
| `web/v2/js/sim-structure.js` | **new** — pivots, zigzag, trendlines, S/R levels |
| `web/v2/js/sim-patterns.js` | **new** — chart catalogue, tier ladder, state machine |
| `web/v2/js/sim-candles.js` | **new** — tier-2 candlesticks (was `sim-patterns.js` in the candlestick spec; renamed here) |
| `tests/web/sim-structure.test.js` | **new** |
| `tests/web/sim-patterns.test.js` | **new** |
| `tests/web/sim-candles.test.js` | **new** |
| `web/v2/js/simulator.js` | modify — §10 |
| `web/v2/css/cockpit.css` | modify — §9.6 |
| `scripts/tools/pattern_census.mjs` | **new** — calibration, §13 |
| `CHANGELOG.md`, `.claude/skills/macro-beans-site/SKILL.md` | modify |

All three JS modules must be **pure**: no DOM, no `fetch`. `sim-structure.js`
imports nothing; `sim-patterns.js` imports `sim-structure.js` and
`sim-candles.js`; `sim-candles.js` imports `sim-indicators.js`.

**Build `sim-structure.js` and its tests first, and stop there until they pass.**
Research note §10.1: stage 1 determines everything downstream. A pattern
catalogue built on a shaky pivot engine cannot be debugged.

---

## 3. The data contract

```js
/**
 * @typedef {Object} Pattern
 * @property {string}  id       // "ascending-triangle" — stable, kebab-case
 * @property {string}  label    // "ASC TRIANGLE" — drawn as-is, <= 16 chars
 * @property {1|2|3}   tier     // 1 chart, 2 candlestick, 3 level
 * @property {"bull"|"bear"|"either"|"neutral"} bias
 * @property {"reversal"|"continuation"|"level"} kind
 * @property {PatternState} state
 * @property {number}  startIdx
 * @property {number}  endIdx   // last bar of the SHAPE (not of the hand)
 * @property {Shape}   shape    // what to draw, §9.1
 * @property {number|null} trigger      // close beyond => broken out
 * @property {number|null} triggerDown  // bias "either" only: the other side
 * @property {number|null} invalidate
 * @property {number}  height        // measure-rule height
 * @property {number}  hitRate       // Bulkowski % meeting target, §7.3
 * @property {number|null} zoneNear  // trigger +/- height*hitRate
 * @property {number|null} zoneFar   // trigger +/- height*1.0
 * @property {number|null} zoneUntil // endIdx + (endIdx - startIdx)
 * @property {number|null} breakoutIdx
 * @property {number|null} resolvedIdx
 * @property {number}  quality  // touches*10 + span, for §8 precedence
 */

/** @typedef {"forming"|"broken-out"|"throwback"|"confirmed"|"failed"|"expired"|"abandoned"} PatternState */
```

`null` is the final outcome: **no pattern**. It must render as nothing at all.

### Exports

```js
// sim-structure.js
export function pivotsOf(bars, from, to, k);         // -> Pivot[]
export function zigzag(pivots, bars, atr, minSwing); // -> Pivot[] (alternating)
export function fitLine(points);                     // -> {m, b}
export function lineAt(line, i);
export function countTouches(line, pivots, atr);
export function levels(pivots, bars, atr, opts);     // -> Level[] (S/R), §6

// sim-patterns.js
export function detectPattern(bars, atr, anchorIdx, opts = {}); // -> Pattern | null
export function resolvePattern(pattern, bars, throughIdx);      // -> Pattern | null
export const CHART_PATTERNS, PATTERN_IDS;
```

`resolvePattern` is pure and idempotent; a terminal pattern comes back
unchanged.

---

## 4. Stage 1 — pivots

### 4.1 Constants

```js
const PIVOT_K       = 2;     // bars either side of a confirmed pivot
const MIN_SWING_ATR = 0.75;  // zigzag noise filter, in ATR(14)
```

`PIVOT_K` is the single most consequential number in this spec — it is what the
platforms expose as "left/right bar strength". §13 calibrates it.

### 4.2 Confirmed pivots

```
bars[i] is a pivot HIGH iff  bars[i].h > bars[j].h  for all j in [i-k, i+k], j != i
bars[i] is a pivot LOW  iff  bars[i].l < bars[j].l  for all j in [i-k, i+k], j != i
```

Strict inequality; on a tie neither bar is a pivot. Only `i` in
`[from + k, to - k]` can be confirmed.

### 4.3 The right edge is provisional — by construction

A pivot needs `k` bars to its right. **The last `k` bars can never hold a
confirmed pivot.** Do not engineer around this: it is the structural reason the
`forming` state exists (research note §2).

`pivotsOf` additionally emits, flagged `provisional: true`, the extreme high and
the extreme low within `(to - k, to]`. Provisional pivots may be used **only**
by patterns whose resulting state is `forming`, and never counted as a "touch"
for the ≥3-touch tests in §5.

### 4.4 ZigZag reduction

Walk pivots in index order and enforce alternation:

```
if next.type === lastKept.type:
    replace lastKept if next is the more extreme of the two
else:
    keep next only if |next.price - lastKept.price| >= MIN_SWING_ATR * atr[next.i]
```

ATR-relative, so one threshold works across a 500-name universe (research note
§2). The output alternates high, low, high, low… and is what every pattern in
§5 consumes.

---

## 5. Stages 2–3 — the chart pattern catalogue

### 5.1 Shared machinery

```js
const TOUCH_ATR    = 0.35;  // pivot within this of a line => a touch
const BREAK_ATR    = 0.25;  // close this far outside a boundary => broken
const FLAT_SLOPE   = 0.15;  // |rise over the span| <= this * width => horizontal
const CONVERGE     = 0.75;  // endWidth <= this * startWidth => converging
const PARALLEL     = 0.25;  // |endWidth - startWidth| <= this * startWidth
const APEX_MAX     = 0.85;  // reject past this fraction of the way to the apex
const MIN_BARS     = 8;     // shortest allowed pattern span
const MIN_WIDTH_ATR = 1.0;  // a pattern narrower than this is noise
const CHART_RECENCY = 5;    // endIdx must be within this of the anchor
```

```
fitLine(pts)            least squares on (i, price); 2 points give the exact line
width(u, l, i)          lineAt(u,i) - lineAt(l,i)
slopeClass(line, s, e, w)  r = (lineAt(line,e) - lineAt(line,s)) / w
                           |r| <= FLAT_SLOPE -> "flat", else "up"/"down"
touches(line, pivots)   count of p with |p.price - lineAt(line,p.i)| <= TOUCH_ATR*atr[p.i]
respected(u, l, s, e)   every i in [s,e]:  c[i] <= lineAt(u,i) + BREAK_ATR*atr[i]
                                       and c[i] >= lineAt(l,i) - BREAK_ATR*atr[i]
apexFrac(u, l, s, e)    lines converge at ia where width == 0;
                        (e - s) / (ia - s), or 0 if they diverge
```

### 5.2 Candidate generation

Anchor `A = dIdx`. Candidate spans start on a pivot and end near the anchor:

```
for e in [A - CHART_RECENCY + 1 .. A]:
    for each zigzag pivot s with s >= from and e - s + 1 >= MIN_BARS:
        P = zigzag pivots in [s, e]
        if P has >= 2 highs and >= 2 lows:  test the two-line families (5.3)
        test double top/bottom (5.5) and head-and-shoulders (5.6) on P
    test flags and pennants (5.4), which are anchored on a pole, not a pivot
```

Spans are ≤ 35 bars and pivots are few, so this is ~100 cheap candidates per
deal. Every candidate must satisfy `s >= from`: **a tier-1 pattern must be
fully visible.** Only tier-3 levels (§6) may count off-screen touches, because a
horizontal level is fully specified by its price.

### 5.3 The two-line families — one classification table

Fit `upper` through the pivot highs and `lower` through the pivot lows, then
classify. This single table replaces eight separate detectors:

| upper slope | lower slope | width behaviour | pattern | bias |
|---|---|---|---|---|
| flat | up | converging | `ascending-triangle` | bull |
| down | flat | converging | `descending-triangle` | bear |
| down | up | converging | `symmetrical-triangle` | **either** |
| up | up | converging | `rising-wedge` | bear |
| down | down | converging | `falling-wedge` | bull |
| flat | flat | parallel | `rectangle` | **either** |
| up | up | parallel | `ascending-channel` | bull |
| down | down | parallel | `descending-channel` | bear |

Every two-line candidate must also satisfy:

```
max(touches(upper), touches(lower)) >= 3            # Bulkowski, exactly:
min(touches(upper), touches(lower)) >= 2            # three on one, two on the other
respected(upper, lower, s, e)
width(upper, lower, s) >= MIN_WIDTH_ATR * atr[s]
e - s + 1 >= MIN_BARS
converging families only:  apexFrac(upper, lower, s, e) < APEX_MAX
```

The apex rule is Bulkowski's: ascending-triangle breakouts happen ~64% of the
way to the apex, and a triangle that reaches its apex has expired.

### 5.4 Flags and pennants

```js
const POLE_MIN = 4,  POLE_MAX = 15;
const POLE_ATR = 3.0;    // minimum pole height, in ATR(14)
const POLE_CLEAN = 0.35; // max counter-move inside the pole, as a fraction of it
const FLAG_MIN = 3,  FLAG_MAX = 15;
const FLAG_DEPTH = 0.50; // max retracement of the pole
const FLAG_DRIFT = 0.10; // max with-trend overshoot during the flag
const FLAG_TILT  = 0.05; // max with-trend tilt of the flag, per pole height
```

For a **bull** flag (bear mirrors throughout):

```
pole = [p0, p1] with p0 a zigzag pivot low, p1 = p0 + POLE_MIN..POLE_MAX
  poleH = c[p1] - c[p0]  >=  POLE_ATR * atr[p1]
  cleanliness: max drawdown within [p0,p1] <= POLE_CLEAN * poleH
flag = [p1+1, e], length FLAG_MIN..FLAG_MAX
  depth:      (c[p1] - min low(flag)) / poleH   <= FLAG_DEPTH
  overshoot:  (max high(flag) - c[p1]) / poleH  <= FLAG_DRIFT
  contraction: mean(h-l over flag) < mean(h-l over pole)
  tilt: least-squares slope through the flag's closes must be <= 0, or
        slope * flagLen <= FLAG_TILT * poleH
```

**Flag vs pennant** — with only 3–15 bars there are rarely enough pivots for a
reliable two-line fit, so use a range test instead:

```
rangeOf(firstHalf), rangeOf(secondHalf) of the flag
secondHalf <= CONVERGE * firstHalf   ->  pennant   (converging)
otherwise                            ->  flag      (parallel-ish)
```

`height` for the measure rule is **`poleH`, not the flag's own height**
(Bulkowski's rule for both patterns). `trigger` = the flag's high (bull),
`invalidate` = the flag's low.

### 5.5 Double top / double bottom

```js
const DB_TOL_ATR  = 0.6;   // how equal the two extremes must be
const DB_MIN_GAP  = 5, DB_MAX_GAP = 25;   // bars between them
const DB_RISE_ATR = 1.5;   // the intervening peak must be a real peak
```

For a **double bottom**, take three consecutive zigzag pivots `L1(low)`,
`P(high)`, `L2(low)`:

```
|L1.price - L2.price| <= DB_TOL_ATR * atr[L2.i]
L2.i - L1.i in [DB_MIN_GAP, DB_MAX_GAP]
P.price - max(L1.price, L2.price) >= DB_RISE_ATR * atr[P.i]
no close below min(L1,L2) - BREAK_ATR*atr between L1.i and L2.i
neckline = P.price   ->  trigger
invalidate = min(L1.price, L2.price)
height = neckline - invalidate
```

Double top mirrors. **This is the pattern where the state machine earns its
keep**: unconfirmed, double bottoms fail ~64% of the time; confirmed, ~16%
(research note §4). Draw the neckline emphatically.

### 5.6 Head-and-shoulders — Lo, Mamaysky & Wang, ATR-normalised

```js
const HS_TOL_ATR  = 0.7;   // shoulder / trough symmetry tolerance
const HS_HEAD_ATR = 1.5;   // the head must clear the troughs by this much
```

Five consecutive alternating zigzag pivots `E1..E5`. For a **bearish**
head-and-shoulders they run high, low, high, low, high:

```
E3 > E1  and  E3 > E5
avgTop = (E1 + E5)/2,  avgBot = (E2 + E4)/2
|E1 - avgTop| <= HS_TOL_ATR * atr[E1.i]
|E5 - avgTop| <= HS_TOL_ATR * atr[E5.i]
|E2 - avgBot| <= HS_TOL_ATR * atr[E2.i]
|E4 - avgBot| <= HS_TOL_ATR * atr[E4.i]
E3 - avgBot  >= HS_HEAD_ATR * atr[E3.i]
neckline = fitLine([E2, E4])          # a sloping neckline is allowed
trigger = lineAt(neckline, e)         # close below it, for the bearish form
invalidate = E3
height = E3 - lineAt(neckline, E3.i)
```

Inverse head-and-shoulders mirrors. This is Lo/Mamaysky/Wang's definition with
their fixed 1.5% tolerances replaced by ATR-relative ones — cite the paper in
the module header, and note the substitution. **This is the pattern most
constrained by `LOOKBACK = 35`**; expect it to be rare, and let §13 decide
whether it stays.

---

## 6. Tier 3 — support and resistance levels

The honest empty state. When no geometry fits there is usually still a level
price is pressing against, and naming it beats saying nothing.

```js
const SR_TOL_ATR     = 0.5;  // pivots within this collapse into one level
const SR_MIN_TOUCHES = 3;    // two is a coincidence
const SR_NEAR_ATR    = 1.5;  // the level must be near the current price
const SR_RECENT_BARS = 10;   // a touch inside this window counts 1.5
```

1. Cluster **all** pivots in `[from, anchor]` — including off-screen ones, the
   one exception to §5.2's visibility rule — by price within
   `SR_TOL_ATR * atr[anchor]`.
2. `level` = the touch-weighted mean price of the cluster; `touches` = its size.
3. Require `touches >= SR_MIN_TOUCHES`.
4. `score = touches + 0.5 × (touches inside the last SR_RECENT_BARS)`.
5. Take the highest-scoring level with
   `|level - c[anchor]| <= SR_NEAR_ATR * atr[anchor]`. If none, **return
   `null`** — this is what preserves the no-pattern state.

`bias: "neutral"`, `kind: "level"`, no forecast zone (a level makes no
prediction). Label: `RESISTANCE ×4` or `SUPPORT ×3`, by which side of the
current close it sits on. Draw as a horizontal **band** of half-width
`SR_TOL_ATR * atr` — the literature is consistent that levels are zones, and an
ATR-scaled band gets the dynamic sizing for free.

---

## 7. States, levels and the forecast zone

### 7.1 The machine

```
   ┌──────────┐  price stops respecting the shape,   ┌───────────┐
   │ FORMING  │──or the apex passes ────────────────▶│ ABANDONED │
   └────┬─────┘                                      └───────────┘
        │ close beyond `trigger`
        ▼
   ┌────────────┐ ◀──── back beyond trigger ─────┐
   │ BROKEN-OUT │                                │
   └────┬───────┘ ──── close returns to the ───▶ │ THROWBACK │
        │                trigger level           └───────────┘
        │                                              │
        ├──── close reaches zoneNear ──▶ CONFIRMED     │
        ├──── close through invalidate ─▶ FAILED ◀─────┘
        └──── zoneUntil passed ────────▶ EXPIRED
```

Terminal: `confirmed`, `failed`, `expired`, `abandoned`.
`broken-out` ⇄ `throwback` is the only cycle, and it is deliberate: throwbacks
happen on 62–72% of breakouts (research note §4), and a learner who does not
know that reads every one of them as a failure.

### 7.2 Per-bar resolution order

Pessimistic first, mirroring `stopFill()` in `sim-engine.js`:

1. `failed` — close through `invalidate`.
2. `confirmed` — close reached `zoneNear`.
3. `throwback` / `broken-out` — close back at, or beyond, `trigger` (from the
   far side) toggles to `throwback`; a later close beyond `trigger` again
   toggles back.
4. `expired` — `throughIdx > zoneUntil` with no terminal state reached.

While `forming`, each new bar re-tests `respected()` on the frozen shape; the
first close outside it by more than `BREAK_ATR * atr` that is *not* a breakout
through `trigger` makes the pattern `abandoned` (TrendSpider's discard rule).

### 7.3 The forecast zone

```
zoneNear  = trigger ± height * hitRate     # Bulkowski's honest target
zoneFar   = trigger ± height * 1.0         # the textbook measured move
zoneUntil = endIdx + (endIdx - startIdx)   # Autochartist: the pattern's own length
```

`hitRate` per pattern. **The `source` column is not decoration** — three of
these are assumptions and the census must revisit them:

| id | hitRate | source |
|---|---|---|
| `ascending-triangle` | 0.70 | measured |
| `descending-triangle` | 0.44 | measured (down breakouts) |
| `symmetrical-triangle` | 0.58 up / 0.36 down | measured |
| `double-bottom` / `double-top` | 0.66 | measured (Adam & Eve) |
| `flag` (bull / bear) | 0.46 | measured |
| `pennant` (bull / bear) | 0.35 | measured |
| `rising-wedge` | 0.32 | measured |
| `falling-wedge` | 0.58 | **assumed** — no published figure; borrows the symmetrical triangle's |
| `head-and-shoulders`, `inverse-head-and-shoulders` | 0.55 | **assumed** |
| `rectangle` | 0.58 | **assumed** |
| `ascending-channel`, `descending-channel` | — | **no zone**: a channel makes no measured-move claim |

**`bias: "either"`** (symmetrical triangle, rectangle) carries `trigger` and
`triggerDown` and **no zone at all while forming** — the pattern has not chosen
a side. The zone appears on breakout, on whichever side broke. This is
TradingView's grey "can show both" case, and drawing a directional zone before
the break would be inventing a claim the pattern does not make.

---

## 8. One pattern per chart — the tier ladder

Take the first tier that yields anything:

| Tier | Source | Rule |
|---|---|---|
| 1 | `sim-patterns.js` chart catalogue | §5 |
| 2 | `sim-candles.js` candlesticks | [`candlestick_pattern_spec.md`](candlestick_pattern_spec.md) §6, with its own trend gate |
| 3 | `sim-structure.js` S/R level | §6 |
| 4 | — | `null` |

This supersedes the candlestick spec's §7 selection rules: candlesticks are
consulted only when no chart pattern is found. Research note §9 — geometry is
the stronger claim; a candle marks the moment, and is worth naming when there
is no larger structure to name instead.

### Precedence within tier 1

1. **Quality** — `touches * 10 + span`, higher wins.
2. **Recency** — larger `endIdx` wins.
3. **Catalogue rank**, best first, following Bulkowski's measured performance:
   `ascending-triangle, descending-triangle, double-bottom, double-top,
   inverse-head-and-shoulders, head-and-shoulders, symmetrical-triangle,
   falling-wedge, rectangle, ascending-channel, descending-channel, bull-flag,
   bear-flag, rising-wedge, bull-pennant, bear-pennant`.

Quality leads here, unlike the candlestick tier where recency leads. A chart
pattern's span already *contains* the recent bars, so recency barely
discriminates; how well-formed the shape is does. The rank ordering is not
cosmetic: the rising wedge is 36th of 36 bearish patterns and the pennant fails
54% of the time, so both sort below patterns nobody puts on a T-shirt.

### Detection is pinned

Run `detectPattern` **once**, at deal time, over bars `[0..dIdx]`. The shape is
frozen for the hand; only its *state* evolves. A label that churns as you tap
`+1 DAY` teaches nothing, and the pattern you acted on is the one whose fate
you want to watch.

### Hard invariant: no look-ahead

`detectPattern(bars, atr, A)` may read only `j <= A`; the returned `endIdx`
must satisfy `endIdx <= A`. `resolvePattern(p, bars, T)` may read only
`j <= T`. §12 makes this a mandatory test — it is the one bug that would ruin
the simulator silently.

Note this is why §4.3's provisional pivots matter: they are how a pattern
touching the right edge is found *without* peeking.

---

## 9. Rendering

All drawing in `renderChart()`. Reuse `cx(i)`, `yPrice(v)`, `slot`, `bodyW`,
`PAD`, panel `P` and `sim-clip-price`. Everything below is emitted **after the
price grid and before the moving averages**, so candles draw on top.

### 9.1 The shape

`Pattern.shape` is a small drawing instruction, so the page module never needs
to know pattern semantics:

```js
/** @typedef {Object} Shape
 * @property {"lines"|"neckline"|"level"} kind
 * @property {Array<{m:number,b:number}>} lines  // 1 or 2, in index space
 * @property {Array<[number,number]>} [path]     // pivot polyline, e.g. E1..E5
 * @property {number} [level]                    // kind "level"
 * @property {number} [band]                     // kind "level": half-width
 */
```

- `lines` — one `<polyline>` per line from `cx(startIdx)` to
  `cx(breakoutIdx ?? endIdx)`, class `sim-pat-line`.
- `path` — a fainter polyline through the defining pivots (`sim-pat-path`), so
  a head-and-shoulders reads as a shape and not two stray lines.
- Fill — a `<polygon>` between the two lines at ~7% opacity
  (`sim-pat-fill`). The platforms all "shade the pattern zone"; on this dark
  ground it has to be very faint.
- `level` — a `<rect>` of half-height `band` spanning `PAD.l` to `W - PAD.r`.

### 9.2 The label

Top-**right** of the price panel, right-anchored (top-left holds the MA legend
and the off-scale-200SMA note):

```js
out += text(W - PAD.r - 3, P.top + 9,
            `${p.label} · ${p.state.toUpperCase()}`,
            `sim-pat-label sim-pat-${p.bias} sim-pat-${p.state}`, "end");
```

On `W < 340`, drop the ` · STATE` suffix; the line style still separates
forming from broken-out.

### 9.3 The forecast zone

Drawn when `zoneNear != null` and the state is `forming`, `broken-out` or
`throwback`. This is what §0.2's `FORWARD_SLOTS` exists for.

```js
const zx0 = cx(p.endIdx) + slot / 2;
const zx1 = Math.min(W - PAD.r, cx(p.zoneUntil));
const zy0 = yPrice(Math.max(p.zoneNear, p.zoneFar));
const zy1 = yPrice(Math.min(p.zoneNear, p.zoneFar));
// <rect class="sim-pat-zone sim-pat-<bias>" clip-path="url(#sim-clip-price)"
//       x=zx0 y=zy0 width=zx1-zx0 height=zy1-zy0 rx="2"/>
```

On `confirmed`, draw it dimmed. On `failed`, `expired` and `abandoned`, **draw
nothing** — the claim is dead and a zone still hanging there would be a lie.

**Off-scale zones.** A measured move often lands outside `[lo, hi]`. **Do not
add the zone bounds to `consider()`** — squashing every candle to fit a
hypothesis is the wrong trade. Reuse `renderChart()`'s existing
off-scale-200SMA idiom instead:

```js
if (p.zoneFar > hi || p.zoneFar < lo) {
  const up = p.zoneFar > hi;
  out += text(W - PAD.r - 3, up ? P.top + 20 : P.bot - 3,
              `TGT ${up ? "▲" : "▼"} ${fmtPx(p.zoneNear)}–${fmtPx(p.zoneFar)}`,
              `sim-pat-tgt-text sim-pat-${p.bias}`, "end");
}
```

The rect is clipped by `sim-clip-price`, so a partially-visible zone shows its
near edge and the text supplies the rest.

### 9.4 The breakout mark

A 5px vertical tick at `cx(breakoutIdx)` on the `trigger` level, class
`sim-pat-brk`. One mark, only once `breakoutIdx != null`.

### 9.5 Nothing else

No markers in the volume, MACD or RSI panels. No legend entry. No change to
`renderStatus()` or `renderActions()`.

### 9.6 CSS

Append to `web/v2/css/cockpit.css` after the existing simulator rules. Bias
sets colour; **state classes are declared last so they win**.

```css
/* ---- chart patterns ---- */
.sim-pat-line{ fill:none; stroke-width:1.2; opacity:.75; }
.sim-pat-path{ fill:none; stroke-width:1; opacity:.35; stroke-dasharray:2 2; }
.sim-pat-fill{ stroke:none; opacity:.07; }
.sim-pat-zone{ stroke-width:1; stroke-dasharray:2 3; fill-opacity:.10; opacity:.8; }
.sim-pat-brk{ stroke-width:1.6; }
.sim-pat-label{ font-family:var(--mono); font-size:9px; letter-spacing:.06em; }
.sim-pat-tgt-text{ font-family:var(--mono); font-size:9px; }

.sim-pat-bull{ stroke:var(--win);  fill:var(--win);  }
.sim-pat-bear{ stroke:var(--loss); fill:var(--loss); }
.sim-pat-either,
.sim-pat-neutral{ stroke:var(--dim); fill:var(--dim); }

/* state overrides — after bias so they cascade over it */
polyline.sim-pat-forming{ stroke-dasharray:4 3; opacity:.55; }
text.sim-pat-forming{ opacity:.6; }
polyline.sim-pat-broken-out{ stroke-width:1.6; opacity:1; }
rect.sim-pat-confirmed{ opacity:.4; }
.sim-pat-failed, .sim-pat-expired, .sim-pat-abandoned{
  stroke:var(--dim); fill:var(--dim); opacity:.4;
}
```

`--win`, `--loss` and `--dim` are already defined in `cockpit.css`; do not add
colours.

---

## 10. Wiring into `simulator.js`

**H1 — imports**, beside the existing siblings:
```js
import { detectPattern, resolvePattern, PATTERN_IDS } from "./sim-patterns.js";
```

**H2 — forward space.** `renderChart()`: `const slot = plotW / (n + FORWARD_SLOTS);`
per §0.2, with `FORWARD_SLOTS` beside the other chart constants.

**H3 — detect once.** In `newSession()`, after `const ind = indicatorsFor(bars);`,
add to the `S` object:
```js
pattern: params.get("p") === "0" ? null : detectPattern(bars, ind.atr, dIdx),
```

**H4 — resolve on every render.** First line of `render()`, before
`renderStatus()`:
```js
S.pattern = resolvePattern(S.pattern, S.bars, S.curIdx);
```
One hook covers `takePosition`, `advanceDay` and `pass` (which jumps 20
sessions at once, hence the loop in §7.2). It is idempotent and terminal states
short-circuit. `paintStop()` deliberately does not call `render()`, so dragging
the stop cannot disturb the annotation.

**H5 — draw.** Four insertions in `renderChart()` per §9.1–9.4, each guarded by
`if (S.pattern) { … }`.

**H6 — debug hook.** `window.__sim.pattern = () => S.pattern;`

### 10.1 `?p=` — deal a pattern on demand

Pairs with the existing `?t=<TICKER>&d=<ISO date>` fixed-hand params.

- `?p=0` — patterns off entirely; also the kill switch if this ships badly.
- `?p=<id>` — deal until a hand carries that pattern. Validate against
  `PATTERN_IDS`; warn and ignore an unknown id. Implementation: for each of up
  to 6 candidate tickers, walk the eligible decision range and take the first
  index where `detectPattern` returns that id; give up after 6, deal normally,
  and `console.warn`.

---

## 11. Worked example

`AAPL`, 35 sessions to the decision day. ZigZag (`k=2`, `MIN_SWING_ATR=0.75`)
returns seven alternating pivots. Five of them, from index `s = A-24`:

```
  highs at A-24 (188.40), A-16 (188.90), A-6 (188.10)
  lows  at A-20 (179.20), A-11 (183.40)
```

`upper` fits the three highs: slope ≈ `-0.013`/bar over a mean width of ~7.2,
so `|rise/width| = 0.04 <= FLAT_SLOPE` → **flat**. `lower` fits the two lows:
`+0.42`/bar, `rise/width = 1.05` → **up**. Widths: `9.2` at `s`, `4.1` at `e`
→ `4.1 <= 0.75 * 9.2` → **converging**.

Table lookup → `ascending-triangle`, bias `bull`. Touches: 3 upper, 2 lower ✓.
`respected()` holds. `width(s) = 9.2 >= 1.0 * atr` ✓. Apex is ~11 bars out, so
`apexFrac = 24/35 = 0.69 < 0.85` ✓.

```
startIdx = A-24, endIdx = A, trigger = 188.60 (upper line at A)
invalidate = 179.20, height = 188.60 - 179.20 = 9.40, hitRate = 0.70
zoneNear = 188.60 + 6.58 = 195.18
zoneFar  = 188.60 + 9.40 = 198.00
zoneUntil = A + 24
quality = 5*10 + 25 = 75
state = "forming"
```

Chart: two green lines converging over 25 sessions with a 7%-opacity fill, the
label `ASC TRIANGLE · FORMING` top-right, and a shaded band from 195.18 to
198.00 in the forward gutter, running 24 slots right (clipped at the axis).

The player buys. Then:

- Close 189.40 (> 188.60) → **`broken-out`**, `breakoutIdx` set, lines
  thicken, a tick appears on the trigger. Eleven sessions later a close at
  195.60 reaches `zoneNear` → **`confirmed`**; the zone dims.
- Or: close 189.40 breaks out, then 188.20 falls back to the trigger →
  **`throwback`** — the 64% case, and the one a learner must not read as
  failure. A later close at 190.10 → back to `broken-out`.
- Or: a close at 178.80 (< 179.20) → **`failed`**. Lines and label go grey, the
  zone disappears.
- Or: 24 sessions pass with no close beyond either level → **`expired`**.
- Or: while still forming, a close at 176.00 — outside the lower line, and not
  a breakout through `trigger` — → **`abandoned`**.

The annotation never touches the stop, the fills or the P&L. It is commentary,
not a control.

---

## 12. Tests

`npm test` runs `node --test tests/web/*.test.js` and must stay green. Match the
house style in `sim-indicators.test.js`.

### `sim-structure.test.js` — write this first

| Group | What |
|---|---|
| Pivots | a hand-built zigzag series with known extrema; strict-inequality ties yield no pivot; nothing within `k` of either end is confirmed |
| Provisional | exactly one provisional high and one low, drawn from the last `k` bars, both flagged |
| ZigZag | output strictly alternates; same-type runs keep the more extreme; sub-`MIN_SWING_ATR` swings are dropped |
| Lines | `fitLine` on 2 points is exact; on collinear points is exact; slope sign is right |
| Touches | a pivot exactly `TOUCH_ATR * atr` away counts; slightly further does not |
| Levels | three pivots inside tolerance cluster into one level with `touches: 3`; two do not qualify; a level far from the close returns `null` |

### `sim-patterns.test.js`

| Group | Count | What |
|---|---|---|
| Positives | 16 | one clean synthetic instance of each catalogue entry |
| Near-misses | 16 | one clause broken per pattern → `null` or a different id |
| Classification | 8 | the §5.3 table: each slope/width combination yields the right id |
| Touch rule | ≥3 | 3+2 passes; 2+2 fails; 3+1 fails |
| Apex | ≥2 | a triangle past `APEX_MAX` is rejected; one just inside is not |
| Visibility | ≥2 | a pattern starting before `from` is rejected (tier 1); a level using off-screen touches is not (tier 3) |
| Ladder | ≥4 | chart beats candle beats level beats null; a candle-only chart returns tier 2 |
| Precedence | ≥4 | quality before recency; rank as the final tiebreak; determinism |
| States | ≥10 | every transition in §7.1, including `broken-out` → `throwback` → `broken-out`; both-levels-breached → `failed`; terminal states frozen |
| Zones | ≥3 | `zoneNear`/`zoneFar`/`zoneUntil` arithmetic; `bias:"either"` has no zone while forming and gains one on breakout; channels never have one |
| Invariants | ≥4 | no look-ahead; `endIdx <= anchorIdx`; short arrays → `null`, never a throw; `resolvePattern` idempotent |

**The look-ahead test is mandatory and must be written first:**

```js
test("detectPattern never reads past the anchor", () => {
  const full  = detectPattern(bars, atr, A);
  const trunc = detectPattern(bars.slice(0, A + 1), atr.slice(0, A + 1), A);
  assert.deepEqual(trunc, full);
});
```

Run it over several anchors on a long series, not one hand-picked index.

Synthetic fixtures beat real data here: a triangle you constructed has known
pivots, so a failure localises. Build the series from a small DSL (`up(8, 3.2)`,
`down(5, 1.1)`) rather than pasting OHLC arrays.

---

## 13. Calibration — `scripts/tools/pattern_census.mjs`

A one-off Node ESM script, **not** wired into CI or `deploy.yml`. It imports
the three modules directly (no port, no drift), reads `web/v2/data/sim/*.json`,
and runs `detectPattern` at every eligible decision index across the universe.

Those JSON files are gitignored, so build them first:

```bash
python -m src.data.refresh --tickers-file config/sp500.csv --start 2018-01-01
/usr/local/bin/python3 scripts/site/build_sim.py
node scripts/tools/pattern_census.mjs
```

It reports: the share of decision points reaching each tier; the distribution
by id within tier 1; the state distribution at the decision bar; and — running
`resolvePattern` forward to the end of the runway — the terminal-state split
per pattern.

### Acceptance bands

| Measure | Band | Why |
|---|---|---|
| Tier 1 (chart pattern) | **20 %–45 %** | below 20 % the feature barely exists; above 45 % the geometry is too loose |
| Tier 1+2+3 combined | **≤ 75 %** | "no pattern" must stay a real, common outcome |
| Largest single tier-1 id | **≤ 30 %** | one dominant id means one over-loose rule |
| Every shipped pattern | **≥ 0.3 %** of tier-1 hits | rarer than this and it can never be seen — cut it or loosen it |
| `forming` at the decision bar | **50 %–85 %** | most patterns should still be open when you decide; that is the interesting case |

Tune in this order: **`PIVOT_K`** (the master knob), then `MIN_SWING_ATR`, then
`TOUCH_ATR`, then `CHART_RECENCY`. Only after all four are exhausted should
`LOOKBACK` be reconsidered per §0.1 — and that is a decision to put to the
owner, not to take.

Paste the census output into the PR body and append it here under a dated
`## Calibration results` heading.

**Read the terminal-state split critically.** Bulkowski's measured break-even
failure rates run 16–54% (research note §5). A census showing 90% of patterns
confirming would mean `zoneNear` is trivially reachable — that the targets are
too close, not that the detector is good.

---

## 14. Acceptance checklist

- [ ] `sim-structure.js` and its tests land and pass **before** the catalogue is written.
- [ ] All three modules are pure: no DOM, no `fetch`.
- [ ] `npm test` green; every group in §12 covered.
- [ ] The look-ahead test exists and passes across multiple anchors.
- [ ] Every threshold in §4.1, §5.1, §5.4–5.6 and §6 is a named constant.
- [ ] Provisional pivots are used only by `forming` patterns and never counted as touches.
- [ ] Tier-1 patterns are fully visible (`startIdx >= from`); only tier-3 levels use off-screen touches.
- [ ] The tier ladder yields at most one pattern; selection is total and deterministic.
- [ ] All seven states reachable, `broken-out` ⇄ `throwback` included, demonstrated by tests.
- [ ] `bias: "either"` carries no zone until breakout.
- [ ] `null` renders as nothing at all.
- [ ] Detection is pinned at deal time; the shape does not change mid-hand.
- [ ] Zone bounds are **not** in `consider()`; off-scale zones use the edge label.
- [ ] `FORWARD_SLOTS` applied unconditionally; the page still fills `100dvh` and never scrolls, portrait and landscape.
- [ ] No new status chips; `.sim-status` unchanged.
- [ ] `?p=0` disables the feature; `?p=<id>` deals that pattern; `window.__sim.pattern()` works.
- [ ] `build_sim.py`, `deploy.yml`, `.gitignore` and `nav.js` untouched.
- [ ] Census run, all bands met, output in the PR body and appended to §13.
- [ ] The three assumed `hitRate` values in §7.3 are revisited against the census.
- [ ] `CHANGELOG.md` updated; SKILL.md's file map and cheatsheet mention the three new modules.

---

## 15. Deliberately out of scope

- **[Tier B] patterns** — cup-and-handle, broadening formations, triple
  tops/bottoms, full-size head-and-shoulders. Blocked on §0.1.
- **Combining tiers.** A bullish engulfing *at* an ascending triangle's lower
  trendline is the bar on which the pattern was defended (research note §9),
  and marking it would be genuinely useful. It is also two patterns on one
  chart, so it needs its own design.
- **Volume confirmation.** Bulkowski finds volume trends down during formation
  78–86% of the time for triangles, and the contraction-then-expansion
  signature is a standard flag filter. Cheap to add, but it changes hit rates,
  so it needs its own census.
- **A recap-mode chip.** `recap` runs four chips and has room for
  `PATTERN  ASC TRIANGLE · FAILED`. Needs a look at the strip's budget.
- **Tap-to-explain**, and a **spot-it-yourself mode** that hides the label until
  the player has committed — arguably the better teaching tool, arguably a
  different product.
- **Throwback-aware entries.** Since 62–72% of breakouts throw back, "wait for
  the throwback" is a real tactic the simulator could teach. That is a change
  to the *game*, not to the annotation.
