# Candlestick pattern recognition: what the platforms do, and what is true

> **Scope note.** The primary subject of this feature is **chart patterns** —
> triangles, wedges, flags, channels, double bottoms, support and resistance —
> covered in [`chart_pattern_research.md`](chart_pattern_research.md). Single-candle
> patterns are **tier 2**: consulted only when no chart pattern is found. This
> note stands as the evidence base for that tier; §3 in particular is why it is
> tier 2 and not tier 1.

Research note behind the simulator's pattern-recognition feature. It answers
three questions in order: what do comparable platforms actually ship, what are
the patterns' rules precisely enough to code, and how much are the patterns
worth? The last question is the uncomfortable one, and it is the one that
should shape the design.

The companion document — [`candlestick_pattern_spec.md`](candlestick_pattern_spec.md)
— turns these findings into an implementation spec.

## 1. What the platforms ship

Five reference implementations, in rough order of how closely they match what
the simulator needs.

### Finviz — the closest analogue

Finviz's automatic candlestick detection is the tightest of the group and the
best model for us. It detects **fourteen** patterns — Doji, Hammer, Hanging
Man, Inverted Hammer, Shooting Star, Marubozu, Engulfing, Harami, Piercing
Line, Dark Cloud Cover, Morning Star, Evening Star, Three White Soldiers, Three
Black Crows — and draws them as **pattern labels plus a highlight on the
candles where the pattern appears**, with tooltips, and a bullish / bearish /
neutral colour split the user can toggle per category.

Fourteen is the interesting number. TA-Lib recognises 61. Finviz shipped the
subset a retail trader can actually name, which is exactly our problem: this is
a training tool, and a label you cannot recognise teaches nothing.

### TradingView — labels, colours, tooltips

TradingView exposes pattern detection as indicators under *Technicals →
Patterns*. When one fires, "a special label will appear on the chart: blue for
Bullish indicators, red for Bearish indicators, or gray for indicators that can
show both Bullish and Bearish signals", and hovering the label opens a tooltip
explaining the pattern. Detection is capped at the most recent 600 bars. The
labels wire into the alert system.

Two things to steal: the **three-colour convention** (bullish / bearish /
either-way) and the fact that the label, not a drawing, is the primary artefact.
The pattern is *annotated*, not *illustrated*.

### The bounding-box school

A second visual convention shows up in community scripts and newer tools: draw
a **box around the pattern's candles**. TradingView's "Engulfing Box" script
draws a coloured box around each engulfing pair; BullBear Lens describes itself
as having grown out of "a single tool that drew bounding boxes around candles".
Finviz's "highlight the candles where patterns appear" is the same idea in a
softer form.

This is the half that answers *"draw the pattern on the chart"*. A label alone
tells you a pattern exists; the box tells you **which candles are the pattern**,
which is the part a learner cannot infer.

### Linn Software CPR — the density problem, solved badly

Linn Software's Candlestick Pattern Recognition renders each pattern name as
"a horizontal line with diamonds marking positions where patterns were
recognized", with a hover tooltip. It is a matrix: sixty rows of diamonds under
the price panel. It is complete, it is honest, and it is unreadable. It is the
strongest argument in this whole note for the **one-pattern-per-chart** rule.

### TrendSpider / MetaStock — the scale end

TrendSpider advertises 150+ recognised patterns, backtestable and wireable into
bots. Useful as a bound: at that count, patterns stop being something you read
and become something you screen on. Not our use case.

## 2. The rules, precisely

The reference implementation for machine-checkable candlestick rules is
**TA-Lib**, whose 61 `CDL*` functions each return `+100` (bullish), `-100`
(bearish) or `0`. Its source is the most quotable specification available, and
it is worth reading rather than paraphrasing.

### 2.1 The threshold system

TA-Lib does not use fixed percentages. Every notion of "long", "short",
"near" is defined **relative to a trailing average** of recent candles, so the
same rules work on a $9 stock and a $900 one. From `ta_global.c`:

| Setting | Measured against | Avg period | Factor | Meaning |
|---|---|---|---|---|
| `BodyLong` | real body | 10 | 1.0 | body longer than the average of the last 10 bodies |
| `BodyVeryLong` | real body | 10 | 3.0 | longer than 3× that average |
| `BodyShort` | real body | 10 | 1.0 | shorter than that average |
| `BodyDoji` | high−low | 10 | 0.1 | body under 10% of the average high−low range |
| `ShadowLong` | real body | 0 | 1.0 | shadow longer than *this bar's* body |
| `ShadowVeryLong` | real body | 0 | 2.0 | shadow longer than 2× this bar's body |
| `ShadowShort` | sum of shadows | 10 | 1.0 | — |
| `ShadowVeryShort` | high−low | 10 | 0.1 | shadow under 10% of the average range |
| `Near` | high−low | 5 | 0.2 | within 20% of the average 5-bar range |
| `Far` | high−low | 5 | 0.6 | at least 60% of it |
| `Equal` | high−low | 5 | 0.05 | within 5% of it |

Note `ShadowLong` / `ShadowVeryLong` have `avgPeriod = 0` — they compare the
shadow to the **same candle's** body, not to history. That is the difference
between "this candle has a long tail" and "this candle is bigger than usual",
and conflating them is the most common way a home-grown hammer detector goes
wrong.

This scheme is the right one to adopt. It is self-normalising, it needs only
ten bars of warm-up, and it makes every threshold a named, tunable constant
instead of a magic number buried in a conditional.

### 2.2 Four rules verbatim

Transcribed from the TA-Lib C source, with the comments left in.

**Hammer** (`ta_CDLHAMMER.c`) — small real body; lower shadow longer than the
body (`ShadowLong`); upper shadow under 10% of the average range
(`ShadowVeryShort`); and the body sits **near the prior candle's low**:

```c
fabs(close[i] - open[i]) < AVERAGE(BodyShort, i) &&                    /* small rb */
(min(open[i],close[i]) - low[i]) > AVERAGE(ShadowLong, i) &&           /* long lower shadow */
(high[i] - max(open[i],close[i])) < AVERAGE(ShadowVeryShort, i) &&     /* very short upper shadow */
min(close[i],open[i]) <= low[i-1] + AVERAGE(Near, i-1)                 /* rb near the prior candle's lows */
```

**Engulfing** (`ta_CDLENGULFING.c`) — direction flip, and the second **body**
covers the first body. Shadows are ignored, and a shared open/close boundary is
allowed on one side but not both:

```c
white[i] && black[i-1] &&
((close[i] >= open[i-1] && open[i] <  close[i-1]) ||
 (close[i] >  open[i-1] && open[i] <= close[i-1]))
/* … then reject if open[i] == close[i-1] && close[i] == open[i-1] */
```

**Morning star** (`ta_CDLMORNINGSTAR.c`) — long black, a short body that **gaps
below** it, then a body that closes at least `penetration` (default **0.30**)
of the way back into the first body:

```c
black[i-2] && white[i] &&
max(open[i-1],close[i-1]) < min(open[i-2],close[i-2]) &&           /* gapping down */
close[i] > close[i-2] + fabs(close[i-2]-open[i-2]) * penetration && /* well within 1st rb */
fabs(close[i-2]-open[i-2]) > AVERAGE(BodyLong,  i-2) &&             /* 1st: long */
fabs(close[i-1]-open[i-1]) <= AVERAGE(BodyShort, i-1) &&            /* 2nd: short */
fabs(close[i]  -open[i])   > AVERAGE(BodyShort, i)                  /* 3rd: longer than short */
```

**Harami** (`ta_CDLHARAMI.c`) — long body, then a short body wholly inside it.
The sign is the *opposite* of the first candle's:

```c
fabs(close[i-1]-open[i-1]) > AVERAGE(BodyLong,  i-1) &&   /* 1st: long */
fabs(close[i]  -open[i])   <= AVERAGE(BodyShort, i) &&    /* 2nd: short */
max(close[i],open[i]) < max(close[i-1],open[i-1]) &&
min(close[i],open[i]) > min(close[i-1],open[i-1])         /* 2nd engulfed by 1st */
```

### 2.3 The gap that matters: TA-Lib does not check trend

This is the single most important finding in the note, and TA-Lib says it out
loud in its own source comments — three times, in three different files:

> *"the user should consider that a piercing pattern is significant when it
> appears in a downtrend, while this function does not consider it"*
> — `ta_CDLPIERCING.c`

> *"the user should consider that a shooting star must appear in an uptrend,
> while this function does not consider it"*
> — `ta_CDLSHOOTINGSTAR.c`

> *"the user should consider that 3 white soldiers is significant when it
> appears in downtrend, while this function does not consider it"*
> — `ta_CDL3WHITESOLDIERS.c`

`CDLENGULFING` and `CDLHAMMER` carry no trend test at all. And a reversal
pattern without a prior trend is not a weak signal — it is **not the pattern**.
The whole meaning of a hammer is rejection at the low of a move; with no move,
there is nothing to reject. The literature is unanimous on this: a hammer needs
a prior downtrend, ideally two or three bearish sessions, or "the reversal has
nothing to reverse", and in choppy markets hammers generate numerous false
signals.

So: any implementation that wires TA-Lib's rules straight to a chart label
inherits a large, systematic false-positive rate — and it is precisely the kind
of false positive that trains a bad instinct, because the shape on screen looks
textbook. **A trend gate is not an enhancement; it is part of the pattern
definition**, and we have to supply the half TA-Lib deliberately leaves out.

## 3. What the patterns are worth

Two independent bodies of evidence, and they do not flatter each other.

### 3.1 Bulkowski's measurements

Thomas Bulkowski measured 103 candlestick patterns over more than 4.7 million
price bars — the largest consistent dataset in public. His "overall performance
rank" is *"a ranked sum of the percentage price changes from 1, 3, 5 and 10
trading days after the breakout, using all combinations of bull/bear markets
and up/down breakout directions"*; his "frequency rank" is how often the candle
shows up at all.

| Pattern | Acts as stated | Overall perf. rank | Frequency rank | Hits measure-rule target |
|---|---|---|---|---|
| Three white soldiers | bullish reversal **82%** | — | — | — |
| Morning star | bullish reversal **78%** | **12** / 103 | 66 (rare) | — |
| Three inside up | bullish reversal **65%** | — | — | — |
| Bullish engulfing | bullish reversal **63%** | 84 / 103 | 12 (common) | 67% |
| Hammer | bullish reversal **60%** | 65 / 103 | 36 | **88%** |
| Shooting star | bearish reversal **59%** | 55 / 103 | 37 | 84% |

Read the two rank columns against each other and the picture is bleak in a
specific way. The **bullish engulfing** — the pattern every beginner learns
first and the 12th most common of 103 — reverses 63% of the time and then ranks
**84th out of 103** for what happens next. It is reliable at being right about
direction and near-worthless about magnitude. The **morning star** is the
mirror image: it ranks 12th for performance, but 66th for frequency, so you
will barely ever see one.

Bulkowski is blunt about the weaker end. Of the shooting star's 59% he writes
that this is *"near random"* and that traders should not depend on the reversal
happening.

Three context rules recur across his pattern pages and are worth more than the
rules themselves:

1. Patterns within **a third of the yearly low** (bullish) or high (bearish)
   perform best.
2. **Taller candles** outperform.
3. Best results come when the pattern is a **retrace against a larger trend**
   that it then rejoins — not when it tries to turn the primary trend. He
   explicitly warns against bullish engulfings taken *against* a downward
   primary trend: they "produce only temporary reversals".

### 3.2 The academic evidence

Thinner and more negative. The systematic reviews find no agreement that
candlestick charting is profitable; studies on the U.S. and Japanese markets
find that most candlestick reversal patterns **do not generate statistically
significant mean returns**, and that binomial tests reject reliable directional
prediction even for the patterns whose mean returns do reach significance. The
positive results are narrow and market-specific — a handful of patterns clear
transaction costs in the Taiwan market, and that is about the strength of it.

The honest summary: **candlestick patterns are a vocabulary for describing what
just happened, not a profitable signal in isolation.** That is not a reason not
to ship them. It is a very strong reason to ship them as *labels* rather than
as *recommendations*.

### 3.3 Confirmation

Classical practice, and every source consulted, treats a completed pattern as a
*warning*, not a completed reversal:

- A multi-candle pattern is "generally considered unconfirmed until the third
  candle closes".
- A hammer or shooting star "gains conviction" when it forms at a defined
  support/resistance level, on above-average volume, and is **confirmed by the
  following candle closing in the expected direction**.
- Hammers fail often enough that "the confirmation step is not a formality".

This gives the state machine its backbone, and it is the reason a pattern needs
more than an on/off label: *complete* and *confirmed* are different claims about
the world, and the difference is where all the risk lives.

### 3.4 Targets — the measure rule

Bulkowski's measure rule takes the **pattern height** (highest high minus
lowest low across the pattern's candles) and projects it from the **breakout
price** — the point at which price pushes above the top of the pattern
(bullish) or below its bottom (bearish). For candles specifically he notes that
the raw height often sets an almost impossible target, and multiplies it by the
measured "percentage meeting price target" for a nearer, more accurate one.

The hit rates are the surprising part: the hammer's target is reached **88%**
of the time (bull market, up breakout), the shooting star's 84%, the bullish
engulfing's 67%. These are conditional on the breakout having happened — which
is the whole trick, and the reason the target must never be drawn as though it
were free.

## 4. What this means for the simulator

Six conclusions, carried forward into the spec.

1. **Ship ~14 patterns, not 61.** Finviz's set is the proven retail vocabulary.
   A label nobody can name is decoration.
2. **One pattern per chart.** Linn Software's diamond matrix is what the
   alternative looks like. The chart already carries four panels, three moving
   averages, a decision divider and a draggable stop.
3. **Gate on trend, always.** TA-Lib's own comments say the trend test is the
   caller's job. Skipping it ships textbook-looking false positives, which is
   worse than shipping nothing.
4. **Use TA-Lib's relative-threshold scheme**, not fixed percentages. Ten bars
   of warm-up, every threshold named and tunable.
5. **States, not a boolean.** *Forming*, *complete*, *confirmed*, *failed* are
   the distinctions the literature actually makes, and they are the distinctions
   worth teaching.
6. **Label, never recommend.** Given §3.2, an expectation marker has to read as
   *"this is what this pattern claims"* — with the failure states drawn just as
   plainly as the successes. A feature that only lights up when the pattern
   works would be a machine for manufacturing false confidence, and this repo
   has already written down why that is the wrong trade
   ([`simulator_progression.md` §2](simulator_progression.md)).

## Sources

- [Automatic candlestick pattern detection — TradingView](https://www.tradingview.com/support/solutions/43000584462-automatic-candlestick-pattern-detection/)
- [Introducing Automatic Candlestick Detection on Finviz Charts](https://finviz.com/blog/introducing-automatic-candlestick-detection-on-finviz-charts/)
- [Candlestick Pattern Recognition (CPR) — Linn Software](https://www.linnsoft.com/techind/candlestick-pattern-recognition-cpr)
- [Engulfing Box — TradingView script](https://my.tradingview.com/script/6TZkioRl-Engulfing-Box)
- [Pattern Recognition Functions — TA-Lib](https://ta-lib.github.io/ta-lib-python/func_groups/pattern_recognition.html)
- [`ta_global.c` (candle setting defaults) — TA-Lib](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_common/ta_global.c)
- [`ta_CDLHAMMER.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLHAMMER.c) · [`ta_CDLENGULFING.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLENGULFING.c) · [`ta_CDLMORNINGSTAR.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLMORNINGSTAR.c) · [`ta_CDLHARAMI.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLHARAMI.c) · [`ta_CDLPIERCING.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLPIERCING.c) · [`ta_CDLSHOOTINGSTAR.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLSHOOTINGSTAR.c) · [`ta_CDL3WHITESOLDIERS.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDL3WHITESOLDIERS.c) · [`ta_CDLDARKCLOUDCOVER.c`](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLDARKCLOUDCOVER.c)
- Bulkowski, *The Pattern Site*: [Bullish Engulfing](https://thepatternsite.com/BullEngulfing.html) · [Hammer](https://thepatternsite.com/Hammer.html) · [Morning Star](https://thepatternsite.com/MorningStar.html) · [Shooting Star](https://thepatternsite.com/ShootingStar.html) · [Three White Soldiers](https://www.thepatternsite.com/ThreeWhiteSoldiers.html) · [Measure Rule](https://thepatternsite.com/measure.html) · [Glossary](https://www.thepatternsite.com/glossary.html)
- [The Eight Best-Performing Candles — Bulkowski, *Technical Analysis of Stocks & Commodities*](http://traders.com/Documentation/FEEDbk_docs/2011/11/Bulkowski.html)
- [Profitability of Candlestick Charting Patterns in the Stock Exchange of Thailand — *SAGE Open*](https://journals.sagepub.com/doi/10.1177/2158244017736799)
- [The profitability of candlestick charting in the Taiwan stock market — *Pacific-Basin Finance Journal*](https://www.sciencedirect.com/science/article/abs/pii/S0927538X13000735)
- [Candlestick Confirmation: Key Techniques — LuxAlgo](https://www.luxalgo.com/blog/candlestick-confirmation-key-techniques/)
- [The Hammer Candlestick Pattern: A Trader's Guide — TrendSpider](https://trendspider.com/learning-center/the-hammer-candlestick-pattern-a-traders-guide/)
