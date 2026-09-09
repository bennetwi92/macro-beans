# Chart pattern recognition: what the platforms do, and what is true

Research note behind the simulator's pattern-recognition feature. The subject
is **chart patterns** — triangles, wedges, flags, channels, double bottoms,
head-and-shoulders, and the support and resistance levels underneath them all.
These are patterns in *price structure*: they are made of pivots and
trendlines, span weeks, and are found by geometry.

That is a different problem from single-candle patterns (engulfings, hammers,
morning stars), which are found by comparing four numbers on two or three
adjacent bars. Those are covered separately in
[`candlestick_pattern_research.md`](candlestick_pattern_research.md) and enter
this design as a **secondary tier** — significant, but not the thing being
looked for first. §9 says how the two fit together.

The companion document — [`chart_pattern_spec.md`](chart_pattern_spec.md) —
turns these findings into an implementation spec.

## 1. What the platforms ship

### Autochartist — the one to copy

Autochartist is the engine behind pattern recognition at a large number of
retail brokers, and its design answers our hardest question. Three things stand
out:

**It detects patterns that have not finished yet.** It identifies "not only
patterns that have already formed, but also patterns that are being formed,
which means a trader can anticipate price movements early". *Emerging* and
*completed* are first-class, separately-drawn states.

**It draws a forecast *zone*, not a target line.** On a completed pattern it
shades a rectangle extending forward in time. From its own API documentation,
the geometry is:

- **Height** — for an emerging pattern, `resistance_y0 - support_y0` (the
  pattern's own span). For a completed one, the `prediction_price_from` /
  `prediction_price_to` band.
- **Width** — the zone runs from `pattern_end_time + 5px` to
  `pattern_end_time + pattern_length`, clamped to the visible graph. **The
  pattern's own duration is how long its forecast gets to play out.**

A zone reads as an expectation. A line reads as a promise. Given §7, that
distinction is the whole ethical difference between a useful annotation and a
misleading one — and the time-boxing gives the pattern a natural expiry.

**It publishes a hit rate for the zone** (~70% of completed patterns reach the
forecast area), which is the sort of claim that belongs next to a drawn
prediction.

It covers 16 chart patterns.

### TrendSpider — and one sentence worth quoting

TrendSpider detects 13+ formations: ascending / descending / symmetrical
triangles, double tops and bottoms, head-and-shoulders and its inverse,
horizontal / ascending / descending channels, rising and falling wedges, and
cup-and-handle. Patterns are drawn as overlaid trendlines with labels, and
pivot sensitivity ("left/right bar strength") is user-configurable.

The design rule is in one sentence:

> *"We don't display patterns in the past. We discard ongoing patterns which
> don't seem to be respected by the price action any more."*

Two ideas in there. Patterns are **near the right edge or they are noise** —
nobody trades a triangle that resolved five weeks ago. And a pattern that price
has stopped respecting must be **actively discarded**, not left on the chart.
That second one is a state, and it needs a name.

### TradingView and the community scripts

TradingView's auto chart pattern indicators and the Trendoscope-family scripts
converge on the same recipe, and are the clearest statement of the standard
pipeline: use a **ZigZag library to identify swing highs and lows**, fit
trendlines through them, then match geometry. For each detected structure they
"draw pattern boundaries (trendlines, neckline, channel, triangle), shade the
pattern zone, and place text labels with pattern names", and "project price
targets based on pattern height".

Exposed settings are consistently: **pivot sensitivity** (left/right bar
strength), which pattern classes to show, and per-pattern tolerances.

## 2. The pipeline everybody uses

Every implementation surveyed — commercial and academic — is the same four
stages. This is the architecture, and it is worth being explicit about because
it means **the pattern catalogue is the easy part**. Stage 1 decides everything.

```
  bars ──▶ [1] pivots ──▶ [2] trendlines ──▶ [3] geometry ──▶ [4] validity
           swing highs     least-squares      constraints      still respected?
           and lows        fits through       on the shape     broken? stale?
           (ZigZag)        the pivots
```

### Stage 1 — pivots

Two approaches, and they agree more than they differ.

**The practitioner's: the N-bar fractal.** "A pivot high is a candle whose high
is higher than N bars to the left and right; a pivot low is the opposite."
Then a ZigZag reduction enforces alternation (high, low, high, low…) and drops
swings smaller than a threshold. `N` is *the* sensitivity knob: it is what
platforms expose as "left/right bar strength" and what silently determines
whether you find three patterns or three hundred.

The unavoidable consequence: **a pivot needs `N` bars to its right before it
can be confirmed.** The most recent `N` bars can never contain a confirmed
pivot. Every pattern touching the right edge is therefore provisional — which
is not a flaw to engineer around, it is the reason the *forming* state exists.

**The academic's: kernel regression.** Lo, Mamaysky and Wang (2000),
*Foundations of Technical Analysis* — the canonical paper, 31 years of US
stocks, 1962–1996 — do the same thing more smoothly: fit a kernel-regression
estimator to the price series, take local extrema from the **first derivative
of the smoothed curve**, and define patterns over those extrema. The bandwidth
plays the role `N` plays in the fractal method.

Their pattern definitions are the cleanest formalism available: a pattern is a
set of constraints on five consecutive alternating extrema `E1…E5`. Their
head-and-shoulders, for instance:

```
E1 is a maximum
E3 > E1  and  E3 > E5                          (the head is the highest)
|E1 - avg_top| < 0.015 * avg_top               (shoulders within 1.5%
|E5 - avg_top| < 0.015 * avg_top                of each other)
|E2 - avg_bot| < 0.015 * avg_bot               (troughs within 1.5%
|E4 - avg_bot| < 0.015 * avg_bot                of each other)
    where avg_top = (E1+E5)/2,  avg_bot = (E2+E4)/2
```

That is the shape of every definition worth writing: *alternating extrema, plus
inequalities, plus tolerances*. The tolerances are the whole art — 1.5% is a
choice, and a different choice is a different pattern.

One adaptation is needed for our purposes: a fixed **percentage** tolerance
mis-scales across a 500-name universe with different volatilities. ATR-relative
tolerances behave the same way on a quiet utility and a volatile semi.

### Stage 2 — trendlines

Least-squares fit through the pivot highs for the upper line and the pivot lows
for the lower. Then two tests decide whether the line is real:

- **Touches.** Bulkowski's identification rule for triangles is explicit:
  price must cross the pattern side-to-side with **at least three touches on
  one line and two on the other**. Two points define a line; three make it a
  claim.
- **Containment.** No bar inside the pattern may close meaningfully outside the
  lines — if one did, the pattern was already broken there.

### Stage 3 — geometry

Slopes, convergence, and symmetry, per pattern. §5.

### Stage 4 — validity

TrendSpider's discard rule, made mechanical: broken, stale, or past its apex.
Bulkowski's apex rule is the sharp version of "stale" — for the ascending
triangle, breakouts happen on average **64% of the way to the apex**, and a
triangle that reaches its apex has stopped being a triangle.

## 3. Support and resistance — the substrate

Every geometric pattern above is made of horizontal and sloping lines that
price respected. Detecting the horizontal ones on their own is both simpler and
more broadly useful, and the algorithm is standard:

1. **Find pivots** — the same stage-1 swing highs and lows.
2. **Cluster them** — pivots within a tight tolerance collapse into one zone.
   The surveyed implementations use a fixed percentage (~0.3%); ATR-relative is
   the better choice across a mixed universe.
3. **Count touches** — a level is "touched" when price comes within tolerance.
   Each touch raises a strength score, weighted by recency.
4. **Rank** — the consensus threshold is **three or more touches**; two is a
   coincidence.

The consistent recommendation is to draw **zones, not lines** — "consolidates
nearby swing points into structured zones with dynamic sizing to prevent zones
from being too narrow in fast markets or too wide in slow ones". An ATR-scaled
half-width does exactly that for free.

This matters for the simulator beyond drawing levels: it is the honest **empty
state**. When no geometric pattern fits, there is almost always still a level
price is pressing against, and saying *"resistance, four touches"* is more
useful than saying nothing.

## 4. The lifecycle

The states are not a design invention — they are what the platforms and the
statistics both insist on.

```
                          ┌──────────┐
   pivots fit, price ────▶│ FORMING  │──── price leaves the shape without
   still inside           └────┬─────┘     a clean break, or the apex
                               │           passes ──▶ ABANDONED / EXPIRED
              close beyond     │
              a boundary       ▼
                          ┌──────────┐
                          │ BROKEN   │  the breakout bar
                          │  OUT     │  (Bulkowski: "confirmed")
                          └────┬─────┘
                  ┌────────────┼────────────┐
                  ▼            ▼            ▼
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │ REACHED  │ │  FAILED  │ │ THROWBACK│
            │  TARGET  │ │(back in) │ │(and on)  │
            └──────────┘ └──────────┘ └──────────┘
```

Four findings pin this down.

**Confirmation is the single largest effect in the whole literature.** For
double bottoms, "without neckline confirmation the pattern fails roughly
two-thirds of the time (a 64% pre-confirmation failure rate); once price closes
above the neckline, that failure rate collapses" — Adam & Adam double bottoms
run a **16% break-even failure rate** post-confirmation against 64% before it.
The same pattern, the same shape, and a four-fold difference in outcome
depending on one close. If the annotation makes only one distinction, that is
the one.

**Throwbacks are the norm, not the exception.** Ascending triangle 64%,
symmetrical triangle 62%, rising wedge 72%. Price comes back to the breakout
level most of the time before going anywhere. A learner who does not know this
reads every throwback as a failure and exits.

**The apex is a deadline.** Ascending-triangle breakouts happen at ~64% of the
way to the apex; for symmetrical triangles, "expect the market to turn when it
reaches the apex", which it does around 60% of the time. A triangle that
reaches its apex has expired.

**"Still being respected" is a live test, not a one-off.** TrendSpider's
discard rule again: a forming pattern must be re-tested against every new bar,
and dropped when price stops honouring it.

## 5. The catalogue, and what each is worth

Bulkowski's *Encyclopedia of Chart Patterns* is the only large consistent
dataset. Bull-market figures. **Break-even failure rate** = the share of
patterns that fail to move even 5% past the breakout. **% meeting target** = how
often the full measured move is reached.

| Pattern | Break-even failure | Avg rise/decline | Throwback | % meeting target | Typical duration |
|---|---|---|---|---|---|
| Ascending triangle (up) | **17%** | 43% | 64% | **70%** | ~1–2 months |
| Symmetrical triangle (up) | 25% | 34% | 62% | 58% | ~1–3 months |
| Symmetrical triangle (down) | 37% | 12% | 65% | 36% | — |
| Double bottom (Adam&Adam, confirmed) | **16%** | 39% | — | 66% (A&E) | bottoms weeks apart |
| Double bottom (**un**confirmed) | **64%** | — | — | — | — |
| Falling wedge (up) | 26% | 38% | — | — | 3 wks–3 months |
| Rising wedge (down) | **51%** | 9% | 72% | **32%** | 3 wks–3 months |
| Flag (up) | **44%** | 9% | — | **46%** | **< 3 weeks** |
| Pennant (up) | **54%** | 7% | — | **35%** | **≤ 3 weeks** |

Read that table honestly and three things fall out.

**The famous patterns are not the good ones.** Flags and pennants — the two
most-drawn continuation patterns on retail charts — fail the break-even test
44% and 54% of the time, and reach their measured-move target 46% and 35% of
the time. The pennant is a coin flip that costs commission. Meanwhile the
ascending triangle, which nobody puts on a T-shirt, fails 17% of the time and
hits target 70%.

**The rising wedge ranks 36th out of 36 bearish patterns** — dead last, 51%
break-even failure on downward breakouts, 9% average decline, and its target
reached under a third of the time. It is a pattern that is famous for being
famous.

**Confirmation dominates pattern choice.** The gap between a confirmed and an
unconfirmed double bottom (16% vs 64%) is larger than the gap between the best
and worst patterns in the table. *Which* pattern matters less than *whether it
broke out*.

## 6. Targets — the measure rule, and its honest form

The textbook rule is: take the **pattern height** (highest high minus lowest
low, or flagpole length for flags) and project it from the **breakout price**.
That is what every platform draws, and it is systematically optimistic — the
"% meeting target" column is what fraction of the time it is actually reached.

Bulkowski's own correction is to multiply the height by that percentage:

> *"Usually the measure rule is the height added to (upward breakouts) or
> subtracted from (downward breakouts) the breakout price. Instead, multiply
> the height by the 'percentage meeting price target', which results in a
> closer and more accurate price target."*

So each pattern has **two** natural targets: the statistically-typical one
(`height × hit-rate`) and the textbook one (`height × 1.0`). That is a range,
and a range is exactly what Autochartist draws. Taking the two together —
Bulkowski's honest near target and the textbook far target as the two edges of
a forecast zone, time-boxed to the pattern's own duration — is the design that
falls out of the research, and it is what the spec adopts.

For flags and pennants the measure rule uses the **flagpole**, not the flag:
distance from the start to the end of the prior price swing, added to the
bottom of the flag.

## 7. What the patterns are worth

Two bodies of evidence, and unlike the candlestick literature they do not
entirely disagree.

**Lo, Mamaysky and Wang (2000)** is the strongest positive result in academic
technical analysis. Comparing the unconditional distribution of daily returns
to the distribution conditioned on an automatically-detected pattern, over
31 years of US stocks, they found that "several technical indicators do provide
incremental information and may have some practical value". That is a careful
sentence — *incremental information*, not *profits*. But it is a real,
replicated, peer-reviewed finding, and it is more than the candlestick
literature has (see the companion note, §3.2).

**Bulkowski's numbers** are the practitioner's counterweight: even the good
patterns fail 17–26% of the time outright, throwbacks hit the majority of
breakouts, and the popular patterns are the weak ones.

Put together, the defensible claim is: **chart patterns carry some information
about the distribution of future returns, conditional on a confirmed breakout,
and much less before one.** Enough to be worth learning to see. Not enough to
be worth drawing an arrow and a price.

## 8. The window problem

This is the finding that most constrains the simulator specifically, and it has
nothing to do with the algorithms.

The simulator shows **35 sessions** (`LOOKBACK = 35`) when you decide — about
seven calendar weeks. Against the durations in §5:

| Pattern | Typical duration | Fits 35 sessions? |
|---|---|---|
| Flag | < 3 weeks + ~11-day pole ≈ 26 sessions | **yes** |
| Pennant | ≤ 3 weeks + pole | **yes** |
| Rectangle / channel | any — a horizontal level is scale-free | **yes** (clipped) |
| Support / resistance level | n/a | **yes** |
| Wedge | 3 weeks – 3 months | short end only |
| Symmetrical / ascending triangle | ~1–3 months | short end only |
| Double top / bottom | bottoms weeks apart | borderline |
| Head-and-shoulders | ~2 months ≈ 42 sessions | **usually not** |
| Cup and handle | 3–6 months | **no** |

So a 35-session window is a *flag-and-level* window. Triangles and wedges will
appear only at their short end; head-and-shoulders will be rare; cup-and-handle
is impossible. That is not a reason to abandon the feature — flags, short
triangles, double bottoms and levels are most of what a swing trader reads —
but it is a reason to **measure the catalogue's hit rate before shipping it**,
and it makes the lookback constant a genuine product decision rather than an
implementation detail. The spec puts that decision up front.

## 9. How candlestick patterns fit in

The companion research note found that single-candle patterns are a vocabulary
for describing what just happened rather than a profitable signal: Bulkowski's
bullish engulfing reverses 63% of the time and then ranks 84th of 103 for what
follows, and the academic literature finds most reversal patterns generate no
statistically significant mean returns.

Chart patterns are the stronger claim — the Lo/Mamaysky/Wang result has no
candlestick equivalent. But single candles remain worth naming, for one
specific reason: **they mark the moment**. A bullish engulfing at the lower
trendline of an ascending triangle is the bar on which the pattern was
defended. The candle is not the signal; it is the timestamp on the signal.

The natural arrangement is therefore a **priority ladder**, not a merge:
geometry first, candle second, level third, nothing fourth. That preserves
one-pattern-per-chart while keeping the engulfing available when there is no
larger structure to talk about.

## 10. Conclusions for the simulator

1. **Build the pivot engine first.** Stage 1 determines everything downstream.
   One sensitivity constant decides whether the feature finds three patterns or
   three hundred, and it has to be calibrated against real data, not chosen.
2. **Forming is a first-class state, not an edge case.** A pivot cannot be
   confirmed until `N` bars have passed, so every pattern at the right edge is
   provisional by construction. Autochartist ships emerging patterns
   deliberately.
3. **Confirmation is the distinction that matters most** — 16% vs 64% failure
   on the same shape. If the annotation teaches one thing, teach that.
4. **Draw a forecast zone, time-boxed to the pattern's own length**, bounded by
   Bulkowski's statistical target and the textbook one. A zone is an
   expectation; a line is a promise the data does not support.
5. **Discard actively.** A pattern price has stopped respecting must leave the
   chart or change colour. TrendSpider treats this as a headline feature.
6. **Prefer ATR-relative tolerances** to the percentage tolerances in the
   literature. The same threshold has to work across 500 names.
7. **Ship the honest numbers alongside the good-looking ones.** The pennant
   fails more often than it works. A tool that draws it identically to an
   ascending triangle is teaching something false by omission.
8. **The 35-session window is a design input, not a constant.** Decide it
   before writing the catalogue.

## Sources

- [Pattern Forecast Calculations — Autochartist support](https://support.autochartist.com/en/knowledgebase/article/pattern-forecast-calculations)
- [What is Autochartist? — Admiral Markets](https://admiralmarkets.com/education/articles/trading-software/what-is-autochartist-and-how-to-use-it)
- [Automated Chart Pattern Recognition — TrendSpider](https://help.trendspider.com/kb/automated-technical-analysis/automated-chart-pattern-recognition)
- [Auto Chart Patterns [Trendoscope] — TradingView](https://www.tradingview.com/script/WZ8B1FIW-Auto-Chart-Patterns-Trendoscope/)
- [Auto chart patterns on TradingView](https://www.tradingview.com/support/solutions/43000690464-auto-chart-patterns-on-tradingview/)
- Lo, Mamaysky & Wang (2000), [*Foundations of Technical Analysis: Computational Algorithms, Statistical Inference, and Empirical Implementation*](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00265) — [NBER w7613](https://www.nber.org/papers/w7613) · [pattern definitions reproduced](https://systematicinvestor.wordpress.com/2012/05/22/classical-technical-patterns/)
- Bulkowski, *The Pattern Site*: [Ascending Triangles](https://thepatternsite.com/at.html) · [Symmetrical Triangles](https://thepatternsite.com/st.html) · [Flags](https://thepatternsite.com/flags.html) · [Pennants](https://thepatternsite.com/pennants.html) · [Rising Wedges](https://thepatternsite.com/risewedge.html) · [Double Bottom Types](https://www.thepatternsite.com/DoubleBottomTypes.html) · [Measure Rule](https://thepatternsite.com/measure.html) · [Failure Rate Study](https://thepatternsite.com/FailureRates.html)
- [Support & Resistance Zones Strength Classifier — LuxAlgo](https://www.luxalgo.com/library/indicator/support-resistance-zones-strength-classifier/)
- [Algorithmically Identifying Stock Price Support & Resistance in Python](https://medium.com/@crisvelasquez/algorithmically-identifying-stock-price-support-resistance-in-python-b9095f9aa279)
- [Bull/Bear Flag — LuxAlgo indicator library](https://www.luxalgo.com/library/indicator/bull-bear-flag/)
- [Flag Pattern: Components, Types, Identification — Strike](https://www.strike.money/technical-analysis/flag-pattern)
