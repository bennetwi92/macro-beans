# The Weekly Review — scorecards, strategy and portfolio construction

> Status: **built** (2026-09-27): all phases, with the changes recorded in
> [§0 As built](#0-as-built--decisions-assumptions-and-what-the-evidence-changed).
> §1 onwards is the original design, kept for its reasoning. Where it and §0
> disagree, §0 is what shipped. This supersedes
> `docs/web_v2/ROADMAP.md`, whose v2 page inventory is now largely built. It
> defines the *consolidation* of the v2 cockpit around a single weekly routine.
> Engineering decisions that are not settled are collected in
> [§10 Open decisions](#10-open-decisions) rather than guessed at.

## 0. As built — decisions, assumptions, and what the evidence changed

The owner asked for the build to proceed on assumptions rather than
questions. Every one is recorded here, so any can be overturned with a
one-line change.

### 0.1 What shipped

| Piece | Where |
|---|---|
| The strategy's rules: series, stage, setups, stop, trade replay, like-week analogues | `web/v2/js/strategy.js` |
| The scorecard: blocks, per-setup weights, vetoes, headline | `web/v2/js/scorecard.js` |
| Fundamentals graded within sector | `web/v2/js/fundamental-score.js` |
| TAPE: breadth and the weekly risk budget | `web/v2/js/tape.js` |
| Portfolio construction and managing real holdings | `web/v2/js/construct.js` |
| The five-step weekly review | `tape.html` → `shortlist.html` → `card.html` → `book.html` → `orders.html` (`js/rv-*.js`, shared `js/review.js`) |
| Site build (Node, running the browser's own modules) | `scripts/site/build_scorecards.mjs` → `scorecards.json`, `fundamentals.json`, `earnings.json` |
| Fundamentals snapshots and the earnings calendar (committed) | `src/data/fundamentals.py` → `data/fundamentals/` |
| Forward-evidence ledger (committed) and its grader | `data/scorecard/ledger/`, `scripts/scorecard/grade_ledger.mjs` |
| Backtest, calibration, controls | `scripts/scorecard/backtest.mjs` → `docs/scorecard/weekly_strategy_backtest.md` |
| Weekly CI (snapshot, ledger, commit, redeploy) | `.github/workflows/fundamentals.yml` |
| Tests | `tests/web/strategy.test.js`, `scorecard.test.js`, `weekly-book.test.js` |

### 0.2 Assumptions made in place of questions

1. **The book is a small cash ISA** (`docs/reference/small-account-reality-check.md`, `docs/portfolio/isa_*`). It is **long-only**: an ISA can't short single stocks, so shorts are a non-goal rather than a later phase. A Stage 4 tape is answered with cash.
2. **US single stocks are bought directly, in USD, with fractional shares** (Trading 212 ISA). Costs are 0.15% FX each way and no commission. This settles §10.4.
3. **Scorecards are built in Node from the browser's modules**, as `pattern_census.mjs` already does. This settles §10.1.
4. **The price sheet and scanner survive** as the LSE ETF surface, listed after the review steps in the app bar. The unbuilt Instruments and Systems links (which 404'd) are dropped. This settles §10.2.
5. **Analogues use the name's own history, conditioned on the setup.** They are the strategy's own replayed trades on that name, shrunk towards the universe's expectancy by n/(n+20), the Scanner's constant. This settles §10.3.
6. **Fundamentals are percentiles within GICS sector, from the latest snapshot.** Ranking is cross-sectional, so no history is needed. This settles §10.5.
7. **Structural caps:** 10 positions, 20% per position, 3 per sector, correlation cap 0.85, and a £100 minimum order.
8. **Earnings are an entry veto, not a hold veto.** Every 26-week hold spans a report, so the rule is no new entry inside 14 days of one.

### 0.3 Where the evidence overturned the design

Full numbers are in `docs/scorecard/weekly_strategy_backtest.md`.

- **Setups alone don't beat a random entry** under the same exits. The expectancy (about +0.3R a trade) comes from the exits plus the universe's survivorship drift. The scorecard therefore has to earn its place by ranking.
- **No block reliably ranks setups within a week.** Every IC is under 0.05, and most flip sign between the in-sample and out-of-sample years. **The weights are the priors below, deliberately not fitted.** Fitted weights turned negative out of sample.
- **Even momentum doesn't rank this universe**, and losers match winners. That's survivorship: every stock in today's S&P 500 that fell hard later recovered. A survivor-only universe is biased against momentum and quality, and nothing available removes that bias. Hence **the ledger**, which is forward evidence free of it.
- **The stop floor moved from 0.5 to 1 ATR.** It was chosen from 0.5, 1, 1.5 and 2 ATR in-sample, and held out of sample. At 0.5 ATR the R:R block measured stop tightness and ranked outcomes backwards.
- **Stops fill on the daily bars inside the week.** A Wednesday gap fills at Wednesday's open. The weekly-bar fill hid exactly the gap losses the earnings veto guards against.
- **The risk side is robust.** The TAPE budget cuts max drawdown by about two-fifths (−44% → −28%). The earnings veto cuts gap losses about threefold. The R:R veto helps once the stop is sensible.
- **Chart patterns carry no weight.** The weekly census puts tier 1 at 18.4%, under its 20% band, and their IC was negative in both halves. Candles are excluded outright, because their trend gate was calibrated on daily bars.
- **Liquidity is dropped as a block.** S&P 500 membership already guarantees it, and anything finer (spreads, depth, broker availability) is point-in-time data we don't have.
- **News is the earnings surprise.** It's dated, machine-readable and has 12 years of history. Headlines were aggregator noise.
- **BREAKOUT was tightened twice by definition, not by fitting.** The cleared high must be at least 4 weeks old (a base, not a grind). A flat-line "Stage 3" range that breaks out counts, as Weinstein's continuation base.
- **A RESET rule was added.** A holding the rules would exit that is also a fresh BUY this week is kept under the new stop, not sold and bought back.
- **Breadth thresholds come from its history.** FULL needs the median (44% in Stage 2) or more. DEFENSIVE is the bottom fifth (under 25%).

### 0.4 Shipped weights (priors)

| Block | PULLBACK | BREAKOUT | REVERSAL |
|---|---|---|---|
| Market & sector | 20 | 20 | 15 |
| Trend / stage | 15 | 10 | 10 |
| Relative strength | 15 | 20 | 10 |
| Structure (R:R) | 15 | 10 | 15 |
| Pattern | 0 | 0 | 0 |
| Momentum | 10 | 10 | 10 |
| Like-week | 5 | 5 | 5 |
| Earnings | 15 | 20 | 15 |
| Fundamental | 5 | 5 | 20 |

The ledger is what should move these. Grade it after a year:
`node scripts/scorecard/grade_ledger.mjs`.

## 1. What this is

The v2 cockpit today is nine pages that each answer a different question well
and do not add up to a decision. Meanwhile the **simulator** — built as a
training game — quietly accumulated a complete, unit-tested weekly analytical
engine: Weinstein stage analysis, market and sector confluence scoring, price
structure, chart patterns, candlesticks, indicators, trade accounting.

This spec does one thing: **lift that engine out of the game, point it at the
real universe as of this week, and make every style of analysis contribute a
graded block to one scorecard per stock — then roll the scorecards up into a
target portfolio.**

The objective is not more analysis. It is **a strategy the owner can fully
engage with**: one sitting a week, a fixed routine, and at the end of it a
specific list of orders with sizes and stops, each traceable to why.

### Scope

- **Universe**: the 503 S&P 500 constituents (`config/sp500.csv`), already
  cached with full history for the simulator. The LSE ETFs of
  `config/instruments.toml` remain the *execution vehicle* surface (price
  sheet), not a scored surface — stage analysis and chart patterns on a 3x
  inverse ETF are not meaningful reads.
- **Frequency**: weekly. Decide on Friday's close, fill at Monday's open. This
  is the cadence `sim-timeframe.js` `WEEKLY` already models.
- **Generation**: this is v2 **consolidated**, not a v3. New pages live in
  `web/v2/`, reuse `cockpit.css`, and the flow is expressed by reordering
  `PAGES` in `nav.js`.

## 2. The strategy

The owner named three instincts that sound contradictory: *buy low sell high*,
*buy into strong trends*, *buy dips and reversals*. They are not contradictory,
and reconciling them is the whole strategy:

> **You only ever buy low relative to a rising line.**

Absolute cheapness is not an edge — it is the single most reliable way to buy
something that keeps falling. The edge is buying a **temporary discount inside a
durable uptrend**, or buying **the moment a durable base resolves upward**. Both
are "buy low, sell high"; neither requires predicting a bottom. This is
trend-following at the higher timeframe and mean-reversion at the entry — which
is exactly what a weekly chart with a 30-week and a 10-week average is for.

### 2.1 Three setup archetypes

A scorecard **never scores a stock in the abstract**. It scores it *as* a
candidate for one named setup, on one named side. (`sim-market.js` already
enforces the side half of this rule: "a bear tape is worth the full 20 points to
a short".) Extend it: the score is for a **side and a setup**.

| Setup | The idea | Stage gate | Entry trigger | Phase |
|---|---|---|---|---|
| **PULLBACK** | Buy a discount in an established advance | Stage 2 | Price into rising 10-week SMA or an S/R shelf; weekly RSI cooled (not oversold); reversal confirmation | 0 |
| **BREAKOUT** | Buy the resolution of a base or continuation | Stage 1→2, or Stage 2 continuation | Weekly close through pattern boundary / resistance, volume expansion | 0 |
| **REVERSAL** | Buy a downtrend that has stopped going down | Stage 4→1 | Basing above a long shelf, momentum divergence, fundamentals that justify survival | 3 |

REVERSAL is deliberately last and deliberately the most gated: it is the setup
that empties accounts, and it is the one that most needs the fundamental block
(§3.7) to exist first. Shorts are the mirror of PULLBACK and BREAKOUT in a
Stage 4 tape; the block math is already side-aware, so shorts cost little extra
once longs work.

### 2.2 Weights differ by setup

A single fixed weighting cannot serve all three, and pretending otherwise is how
a scorecard becomes decoration. A breakout fails in a bad tape, so market
tailwinds dominate it. A pullback lives or dies on where support actually is, so
structure dominates it. A reversal is a bet on survival, so fundamentals
dominate it.

| Block | PULLBACK | BREAKOUT | REVERSAL |
|---|---|---|---|
| Market & sector | 20 | 25 | 10 |
| Trend / stage | 20 | 15 | 10 |
| Structure (R:R) | 25 | 15 | 20 |
| Pattern | 10 | 20 | 10 |
| Momentum | 10 | 10 | 15 |
| Like-week analogues | 10 | 10 | 10 |
| Fundamental | 5 | 5 | 25 |
| **Total** | **100** | **100** | **100** |

These are a starting hypothesis, not a result. They are declared in one frozen
object per archetype (the `sim-timeframe.js` profile pattern) so that changing
one is a one-line diff with a test, never a hunt through a page module.

### 2.3 Gates before score

Score ranks survivors; it never rescues a disqualified name. Hard vetoes:

- **Stage wrong for the setup** (a PULLBACK in Stage 4 is a falling knife).
- **Liquidity below floor** (§3.9) — or not tradeable from the owner's account.
- **Reward:risk below minimum** — if resistance is nearer than the stop, there
  is no trade at any score.
- **Earnings inside the intended hold** (§3.8) — a binary event is not a
  technical setup. Flag, and veto for pattern-led entries.
- **Market tailwinds below `STRICT_MIN`** for BREAKOUT only.

This mirrors the simulator's existing LEARN / STRICT modes, and the two should
share the constant.

### 2.4 Exits are part of the strategy, not an afterthought

Defined up front, because "sell high" needs a definition:

- **Stop**: `defaultStop(WEEKLY, …)` — one tick under the decision week's low,
  falling back to 0.5 ATR. A resting order for the week. Ratchets one way only
  (`moveStop` already refuses to widen).
- **Target**: the next resistance level from the structure block. This is what
  makes R:R computable *before* entry.
- **Time**: `WEEKLY.maxHold`. A setup that has not worked in its horizon is
  wrong, not early.
- **Thesis**: the weekly re-score. If the block that justified the entry has
  broken (stage lost, tailwind flipped), exit regardless of price. This is what
  the BOOK step (§4.4) is for, and it is the discipline a weekly cadence buys.

## 3. The scorecard

One card per stock per setup. Every block is **graded independently**, carries
its **evidence**, and **fails open** — an unavailable block is excluded from the
composite and rescales it rather than scoring zero (`compositePct` in
`sim-market.js` already does exactly this). A build failure must never look like
a bearish signal.

```
AAPL  Consumer electronics                      78/100  ● PULLBACK · LONG
────────────────────────────────────────────────────────────────────────────
MARKET & SECTOR   28/35   SPY bull(w) · XLK rank 2/11 · RS13w +4.1% · VIX 17
TREND / STAGE     STAGE 2  above rising 30wk (11 wks) · +6.2% over 10wk
STRUCTURE         ●●●○     supp 4.8% below · res 9.1% above · R:R 1.9
PATTERN           FLAG     forming, 6 wks · tier 1
MOMENTUM          RSI 58   MACD+ · vol45/1y 0.82 · 13wk +11%
LIKE-WEEK         +2.1%    54% win · n=41 · edge vs drift +1.3% · MAE −3.4%
FUNDAMENTAL       B+       rev +16% · ROE 149% · D/E 78 · FCF+ · PE 39 (rich)
EVENTS            ⚠        earnings 2026-10-29 (in 4 wks)
LIQUIDITY         ✓        ADV $3.1bn · mcap $4.98tn
FIT               ⚠        0.71 corr to MSFT (held) · tech 34% of book
```

### 3.1 Market & sector — *exists*

`sim-market.js`, unchanged: index trend daily + weekly, sector ETF rank of
eleven, relative strength vs SPY, VIX haircut, side-aware, out of 35. The one
change is the caller: `asOf` becomes *this* Friday instead of a dealt date.

### 3.2 Trend / stage — *mostly exists*

Weinstein stage from the 10- and 30-week SMAs already in `WEEKLY.lines`.
Grade on: stage identity, slope of the 30-week, weeks in stage, and distance
above it. New pure module `stage.js`; the numbers come from existing indicators.

### 3.3 Structure — *exists*

`sim-structure.js`: pivots, ZigZag, fitted trendlines, clustered S/R. The block
grades the **geometry of the trade**: depth to nearest support below, headroom
to nearest resistance above, touch counts (level quality), and the resulting
**R:R**. This is where "buy low" is made measurable rather than felt.

### 3.4 Pattern — *exists, needs calibration*

`sim-patterns.js` + `sim-candles.js`, the three-tier ladder, `null` a normal
outcome. **Blocked on a weekly census**: the skill is explicit that the
bar-counted constants were calibrated on daily bars and weekly runs S/R-only
(`detect.tiers: [3]`) until `scripts/tools/pattern_census.mjs` has been run on
weekly bars against the bands in `chart_pattern_spec.md` §13. Do that before
this block claims tiers 1–2.

### 3.5 Momentum — *trivial from existing*

Weekly RSI against `WEEKLY` bands (40/60), MACD state, `vol45/1y` regime,
distance from the 10-week, and 1/4/13/52-week rate of change. All present in
`sim-indicators.js` and `price-metrics.js`.

### 3.6 Like-week analogues — *new, generalises v1's engine*

The owner's "like-day" block, on a weekly clock. v1's `strategy-engine.js`
answers "when this *one trigger* fired historically, what happened next?" This
generalises it: build a feature vector for the current week (stage, RSI band,
distance from 10-week, vol regime, sector rank, pattern id), find the *k* most
similar prior weeks, and report the forward distribution over `maxHold`:
median return, win rate, MAE, **edge versus the name's own drift baseline**,
and *n* — shrunk by sample size, exactly as the scanner already ranks.

Two disciplines, non-negotiable:

- **No look-ahead.** Nothing past the decision week enters the vector or the
  baseline. Mandatory test, same standing as the pattern and market rules.
- **This is the most over-fittable block in the spec.** Similarity search over
  six features across 503 names will always find *something*. It must be
  validated walk-forward before its weight is trusted — `src/models/` and the
  existing mean-reversion walk-forward backtest are the precedent, and the
  honest initial weight is low.

Search scope is an open decision (§10.3): the name's own history is honest but
thin (~1,800 weekly bars at best, often far fewer); pooling cross-sectionally
buys sample size at the cost of assuming names are interchangeable.

### 3.7 Fundamental — *new data layer*

Verified available from yfinance for every S&P name: revenue and earnings
growth, gross/operating/profit margins, ROE, ROA, debt/equity, current ratio,
free cash flow, market cap, P/E, forward P/E, P/B, EV/EBITDA, beta, sector,
industry. Graded as **two** sub-scores, because they answer different questions:

- **Quality** — growth, margins, returns, balance sheet, cash generation. This
  is the "am I buying a discount or a melting ice cube" gate, and it is what
  makes REVERSAL survivable.
- **Value** — valuation against the name's *own* history and against its
  **sector median** (an absolute P/E screen just sorts by sector).

> **Time-sensitive.** `.info` is a **snapshot with no history**. You can score
> today with it and you can never reconstruct it backwards. Any backtest or
> like-week analogue that touches fundamentals is therefore impossible until a
> history exists — which only starts accumulating once we begin writing weekly
> snapshots. **Stand the table up in Phase 0 even though the block lands in
> Phase 2**, and append a dated row every build. In a year it is an asset; if we
> defer it, in a year it is still nothing.

`industry` also supplies the **theme** label the old roadmap wanted per
instrument, for free.

### 3.8 Events — *new, and this is the honest version of "news"*

Earnings dates are available, dated and machine-readable
(`get_earnings_dates`), as are dividend/ex-div dates. That is a real signal: a
binary event inside the hold window changes the trade, and it is the veto in
§2.3. Index adds/drops are a cheap addition.

### 3.9 Liquidity & tradeability — *new, cheap, and the owner didn't ask for it*

Added deliberately. ADV in dollars, market cap, and a spread proxy from the
bars — plus **can this actually be traded from a UK account**. A 90-scoring
name the owner cannot buy is wasted screen space, and the floor is a veto
rather than a score.

### 3.10 Portfolio fit — *new, belongs to the portfolio layer*

Not a property of the stock alone: correlation to what is already held, and the
theme/sector concentration a purchase would create. It sits on the card because
it changes the decision, but it is computed by §5.

### 3.11 News / narrative — *deferred, with a caveat*

`Ticker.news` returns ten headlines, but the sample is aggregator noise
("Does the S&P 500 Have a 'Magnificent Seven' Problem?") — not a scoreable
signal, and turning it into one with a sentiment model would manufacture
precision that isn't there. Recommendation: **Phase 4, and as context you
read rather than a scored block**, unless a real source (a licensed feed, or an
LLM pass over primary filings) is worth paying for. §3.8 carries the part of
"news" that is actually reliable.

### 3.12 Seasonality — *optional, low weight*

Week-of-year historical drift, free from existing bars. Listed for
completeness; trivially over-fitted; not weighted in §2.2.

## 4. The weekly flow

The consolidation. Navigation stops being a menu of tools and becomes **five
steps of one routine**, in order. `PAGES` in `nav.js` is reordered to read as
the flow.

### 4.1 TAPE — what is the tide?
Market context on one screen: index trends daily and weekly, all eleven sector
ranks, VIX, breadth. Ends with a **risk budget for the week** — how much heat
is allowed (§5). Replaces nothing; this read is currently buried in the
simulator's one-line strip.

### 4.2 SHORTLIST — what qualifies?
The ranked grid: one row per surviving candidate, one sortable column per
block, filtered by setup archetype and side. This is the screening surface, and
it is where **the price sheet and the scanner fold in** — their metrics become
blocks (§3.5) and their live strategy signals become the pattern and like-week
blocks. The scanner's edge-vs-baseline framing is carried into §3.6 explicitly
so it is not lost in the merge.

### 4.3 CARD — is this one a trade?
One name, all blocks with evidence, and **the proposed trade made concrete**:
entry at Monday's open, stop from `defaultStop`, target at the structure block's
resistance, size from §5, and the resulting R. The existing chart page becomes
the drill-in from here.

### 4.4 BOOK — does what I hold still stand?
Every held position re-scored against the block that justified it: **intact /
degraded / broken**. Stops to trail, theses to exit. Reads the Neon
trades/positions already built; `book.js` already does average-cost GBP
accounting.

### 4.5 ORDERS — what do I actually do?
The diff between the target portfolio and the real book: buys, trims, exits,
each with size, stop and the one-line reason. This is the artefact the week
produces, and the thing that makes the routine finishable.

The **simulator stays**, and gains a role: it becomes the practice rig for this
exact strategy — the same blocks, the same gates, the same fills, on historical
hands. Training and trading stop being different systems.

## 5. Portfolio construction

Full construction, per the owner's choice: scorecards produce a **target
portfolio**, and the week's orders are the diff against reality.

- **Candidate ranking** — surviving scorecards by setup-weighted score.
- **Sizing** — risk-first: each position risks a fixed fraction of equity from
  entry to stop, so size falls out of the stop distance, not conviction alone.
  Score then modulates within a band.
- **Portfolio heat** — total open risk (sum of R at risk) capped, with the cap
  set by the TAPE risk budget. A bad tape shrinks the book automatically.
- **Concentration** — caps per sector and per theme (`industry`), informed by
  the correlation read in §3.10.
- **Rebalance** — a weekly diff, with a no-trade band so the book does not churn
  on noise. `src/rebalancing/` (engine, policies, metrics, stats, validate) just
  landed and should back this rather than a second implementation.

Cash is a position. A week where nothing qualifies produces no orders, and the
flow has to make that feel like a result rather than a failure.

## 6. Architecture

### 6.1 Scorecards are built in Node, from the browser's own modules

The decision that matters. 503 names × nine blocks, with pattern detection over
90 bars each, is too much for a phone on page load — but reimplementing the
math in Python would fork it away from the tested modules and guarantee drift.

**`scripts/site/build_scorecards.mjs` runs in Node and imports
`web/v2/js/sim-*.js` directly**, exactly as `scripts/tools/pattern_census.mjs`
already does ("no port, no reimplementation, no drift"). Node is already in CI
for the engine tests.

This stays inside the hard rules — computation is at **build time**, emitted as
JSON, with no app server. The browser still computes everything interactive:
re-weighting, what-if, and as-of dates within the shipped window.

Outputs:

```
web/v2/data/
  scorecards.json           {built_at, week, rows:[{t, setup, side, total, blocks:{…}, vetoes:[…]}]}
  scorecards/<TICKER>.json  full per-block evidence for the CARD
  tape.json                 the TAPE read + risk budget
  fundamentals.json         latest snapshot per name (from the new table)
```

### 6.2 Fundamentals go through the data layer, not around it

yfinance is Python, and `src.data.refresh` is the single writer. Add a
`fundamentals` table (dated rows, appended weekly — §3.7) written by a new
`src/data/fundamentals.py` behind a refresh subcommand, then a
`scripts/site/build_fundamentals.py` that emits the JSON. 503 `.info` calls is
a few minutes of CI and needs rate-limit tolerance and the `BuildTally`
coverage gate, not a hard failure on a flaky name.

### 6.3 Everything analytical stays pure and tested

New pure modules, no DOM and no fetch, each with `tests/web/*.test.js` in the
same commit: `scorecard.js` (blocks, weights, gates, composite), `stage.js`,
`analogues.js`, `fundamental-score.js`, `sizing.js`. The archetype weightings
and gates live in **one frozen profile object per archetype**, the
`sim-timeframe.js` pattern, so the strategy is a diff and not an excavation.

## 7. Phasing

Each phase ends with something usable on a Sunday.

- **Phase 0 — the spine.** Weekly pattern census. `scorecard.js` + `stage.js` +
  the Node build. Blocks that already exist: market & sector, stage, structure,
  momentum, liquidity. SHORTLIST + CARD pages, PULLBACK and BREAKOUT.
  **Also: stand up the fundamentals table and start snapshotting** (§3.7).
  → *A ranked, evidenced weekly shortlist with real stops and R:R.*
- **Phase 1 — evidence.** Like-week analogues, walk-forward validated. TAPE
  page and the risk budget.
- **Phase 2 — quality.** Fundamental quality + value blocks from the
  accumulating table. Events block and the earnings veto.
- **Phase 3 — the book.** BOOK re-scoring, sizing, heat, correlation and
  concentration, ORDERS diff against Neon on `src/rebalancing/`. REVERSAL
  archetype. Shorts.
- **Phase 4 — the rest.** News/narrative if a real source justifies it,
  seasonality, simulator retuned to train this strategy.

## 8. What would make this fail

Stated plainly, so it is checkable later:

1. **Over-fitting the like-week block.** Six features and 503 names will always
   find a pattern. Walk-forward or it does not get weight.
2. **Uncalibrated weekly patterns.** Loosening a gate by eye is how the feature
   becomes wallpaper (`chart_pattern_spec.md` §13 exists for this reason).
3. **Fundamental look-ahead.** Scoring today with today's `.info` is fine;
   backtesting with it is not, and the distinction has to be enforced in code,
   not remembered.
4. **A total that hides its blocks.** If the headline is what gets used, the
   nine blocks are theatre. The CARD has to be the thing that decides.
5. **A routine too long to actually do.** Five steps, one sitting. If Phase 3
   makes Sunday take two hours, the strategy has failed on the only metric the
   owner named: full engagement.

## 9. Existing assets — what gets reused

| Need | Already exists |
|---|---|
| Weekly bars, profile, default stop | `sim-timeframe.js` (`WEEKLY`, `toWeekly`, `defaultStop`) |
| Market & sector block | `sim-market.js` (score /35, side-aware, weekly variant, fail-open) |
| Structure / S/R / R:R | `sim-structure.js` (pivots, ZigZag, `levels`) |
| Pattern block | `sim-patterns.js`, `sim-candles.js`, tier ladder |
| Indicators | `sim-indicators.js` (EMA/SMA/MACD/RSI/ATR, Wilder) |
| As-of metrics | `price-metrics.js` |
| Edge vs baseline, shrinkage ranking | v1 `web/js/strategy-engine.js` (shared, tested) |
| Fills, stops, P&L in % and R | `sim-engine.js` |
| Position accounting (GBP, average cost) | `book.js` + Neon trades/positions |
| Rebalancing engine | `src/rebalancing/` |
| Node-runs-browser-modules precedent | `scripts/tools/pattern_census.mjs` |
| Universe, full history, cached | `config/sp500.csv`, `build_sim.py`, `sim/<TICKER>.json` |

The genuinely new work is: the scorecard composition layer, the analogue search,
the fundamentals data layer, and the portfolio construction layer. Everything
else is a caller change.

## 10. Open decisions

1. **Scorecard computation site.** §6.1 proposes a Node build step importing the
   browser modules. It is within the hard rules and has precedent, but it is the
   first Node step in `deploy.yml` outside tests. Confirm before building.
2. **Does the price sheet die?** §4.2 folds its metrics into SHORTLIST, but the
   price sheet is the only surface for the LSE ETF execution vehicles, which are
   *not* scored. Likely answer: it survives as the execution surface, demoted.
3. **Analogue search scope.** Own history (honest, thin) vs pooled
   cross-sectional (larger sample, assumes interchangeability) vs pooled within
   sector. Affects whether §3.6 can carry real weight.
4. **Tradeability of US singles from the owner's account.** The scored universe
   is S&P 500; the owner's documented style is LSE ETFs. If US singles are not
   directly tradeable, §3.9 needs a mapping to a tradeable vehicle, and that
   changes what ORDERS can even say.
5. **Fundamental grading curve.** Absolute thresholds vs percentile within
   sector. Percentile needs the snapshot history that Phase 0 starts building.
6. **Shorts.** The block math is side-aware, but the book, sizing and the LSE
   inverse-ETF vehicle question make shorting a different operational problem.
7. **Where REVERSAL's fundamentals come from** before the snapshot history is
   deep enough to percentile-rank.

---

*Next step: settle §10.1 and §10.2, then Phase 0.*
