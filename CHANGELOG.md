# Changelog

## 2026-09-09 - Chart Patterns on the Simulator (v2)

Implements `docs/web_v2/chart_pattern_spec.md`. At most **one** pattern is
annotated per deal, found once at deal time and then played out as the hand
does. `null` is the common outcome and draws nothing at all.

### Added
- `web/v2/js/sim-structure.js` — pivots (strict local extrema over `PIVOT_K`
  bars either side), a ZigZag reduction filtered by an ATR-relative swing
  threshold, least-squares trendline fitting, and touch-weighted
  support/resistance clustering. Pure, no DOM, no fetch.
- `web/v2/js/sim-patterns.js` — the catalogue and everything above it: one
  classification table covering the eight two-line families (ascending /
  descending / symmetrical triangles, rising and falling wedges, rectangles,
  ascending and descending channels), flags and pennants off a pole, double
  tops and bottoms, Lo/Mamaysky/Wang head-and-shoulders with ATR-relative
  tolerances, the three-tier selection ladder, Bulkowski-bounded forecast
  zones, and the seven-state machine (`forming` → `broken-out` ⇄ `throwback`
  → `confirmed` / `failed` / `expired` / `abandoned`).
- `web/v2/js/sim-candles.js` — tier 2: the 17-entry candlestick catalogue on
  TA-Lib's relative-threshold system, with the trend gate TA-Lib leaves to its
  caller. Consulted only when no chart pattern is found.
- `tests/web/sim-structure.test.js`, `sim-patterns.test.js`,
  `sim-candles.test.js` and the `_sim-bars.js` fixture builder — 145 new tests,
  every fixture stated as the lines or turning points it is supposed to be so a
  failure localises to one clause.
- `scripts/tools/pattern_census.mjs` — the calibration harness. Imports the
  browser modules directly, runs detection at every eligible decision index and
  resolves each hit to the end of its runway. Not wired into CI.

### Changed
- `web/v2/js/simulator.js` — five hooks: detect once in `newSession()`, resolve
  on every `render()`, draw the shape / zone / breakout mark in `renderChart()`,
  and an unconditional eight-slot forward gutter so a forecast zone has
  somewhere to go. `?p=<id>` deals a chosen pattern, `?p=0` turns the feature
  off, `window.__sim.pattern()` inspects the live one.
- `web/v2/css/cockpit.css` — the pattern art, in three layers (geometry, bias
  colour, state) whose selector specificity is load-bearing.
- The decision divider's label moved to the foot of the price panel and the
  off-scale 200SMA note to the top right. The forward gutter pulled the divider
  eight slots in from the right edge, into the corner those labels shared; the
  200SMA note had also been overprinting the moving-average legend whenever the
  average sat above the window, which predates this change.

### Notes
- **The 35-session window is a display budget, not a detection one.** The chart
  still shows 35 bars because that is what reads on a phone; the detector reads
  back 90, and a shape that starts before the left edge is clipped there. This
  reverses the spec's §0.1 assumption that the two are the same number, and it
  is what makes head-and-shoulders and multi-month channels findable at all.
- **The census caught a detector that was far too loose.** The spec's constants
  were derived for a 35-bar window; at 90 bars the detector tries ~80 candidate
  spans per deal, and the first run put a chart pattern on **72.6%** of decision
  points against a 20-45% band. Eleven constants were tightened — the touch
  tolerance, the two-line touch rule (3+2 → 3+3), both neckline families' shape
  tolerances, and the S/R clustering — bringing it to 25.0%. The reasoning and
  the full output are appended to the spec under `## Calibration results`.
- **The two-line touch test is close to circular** and this is the thing to
  remember when tuning: a trendline is fitted *through* the pivots and then
  checked *against* those same pivots, so its threshold is doing far more work
  than it looks like it is.
- **Run against random-walk series, not real prices.** Yahoo Finance is
  unreachable from the environment this shipped from, so the simulator JSON
  could not be built. A random walk under-produces every pattern that needs
  price to respect a line, so the bands must be re-checked against real data;
  what it does prove is the direction that mattered here, since nothing about
  real data makes a loose detector tighter.
- Deviations from the spec, each with its reasoning in the code: flags are
  triggered off their drawn envelope rather than their extreme high (the drawn
  boundary and the stated trigger must be the same object); flag-vs-pennant is
  decided on envelope width rather than a raw range test (which is biased,
  because a flag's first half always inherits the drop off the pole); tier 2
  drops its own "forming" candidates and shares tier 1's states and renderer.
- `build_sim.py`, `deploy.yml`, `.gitignore` and `nav.js` are untouched.

## 2026-09-09 - Chart Pattern Recognition: Research + Spec (v2 simulator)

### Added
- `docs/web_v2/chart_pattern_research.md` — how Autochartist, TrendSpider and
  the TradingView auto-pattern scripts actually detect and draw **chart**
  patterns (triangles, wedges, flags, channels, double bottoms,
  head-and-shoulders, support/resistance); the four-stage pipeline they all
  share; Lo/Mamaysky/Wang's formal pattern definitions over local extrema;
  Bulkowski's failure, throwback and target-hit rates; and the 35-session
  window problem specific to this simulator.
- `docs/web_v2/chart_pattern_spec.md` — an implementation spec: a pivot/ZigZag
  engine, one classification table covering eight two-line patterns, flags and
  pennants, double tops/bottoms, Lo/Mamaysky/Wang head-and-shoulders with
  ATR-relative tolerances, clustered support/resistance levels, a three-tier
  selection ladder, a seven-state machine, Autochartist-style forecast zones,
  the SVG and CSS, a test plan and a calibration script with pass/fail bands.
- `docs/web_v2/candlestick_pattern_research.md` and
  `docs/web_v2/candlestick_pattern_spec.md` — single-candle patterns
  (engulfings, hammers, stars), now scoped as **tier 2** of the above: a
  17-entry catalogue on TA-Lib's relative-threshold system, a mandatory trend
  gate, and a six-state machine.

### Notes
- Documents only — no code changes. All four live under `docs/web_v2/`, which
  `build_reports.py` excludes from the public research library.
- **Pivot detection decides everything.** Every implementation surveyed is the
  same pipeline — pivots, trendlines, geometry, validity — so one sensitivity
  constant (`PIVOT_K`) determines whether the feature finds three patterns or
  three hundred. The spec makes it the first thing built and the first thing
  calibrated.
- **`forming` is structural, not an edge case.** A pivot cannot be confirmed
  until N bars have passed, so every pattern touching the right edge is
  provisional by construction.
- **Confirmation is the largest effect in the literature.** Double bottoms fail
  ~64% of the time unconfirmed and ~16% once price closes past the neckline —
  the same shape, a four-fold difference. That gap is bigger than the gap
  between the best and worst patterns, so the state machine matters more than
  the catalogue.
- The spec draws a forecast **zone** — bounded by Bulkowski's statistical target
  and the textbook measured move, time-boxed to the pattern's own length —
  rather than a target line. A zone is an expectation; a line is a promise the
  data does not support.
- Two decisions are put to the owner up front: whether to keep `LOOKBACK = 35`
  (which makes this a flag-and-level window) and the unconditional forward
  gutter the forecast zone needs.

## 2026-09-05 - Trailing Stops in the Simulator (v2 cockpit)

### Added
- The simulator's stop stays draggable **after** the entry, so a trade that has
  run in your favour can have its stop trailed up behind it and the gain banked
  — the move the simulator previously made impossible.
- A `B/E` button (keyboard `e`) in the trade action bar trails the stop to the
  entry price exactly, the one level worth a tap. It disables itself once the
  stop is already past the entry or the price has not moved far enough.
- `moveStop` / `stopMoveAllows` / `stopOutStats` in `web/v2/js/sim-engine.js`,
  with eight new cases in `tests/web/sim-engine.test.js` (82 tests total).

### Changed
- The trade-mode `STOP` chip now reads what the stop is *worth*
  (`STOP 94.47 (+0.68R)`) instead of the static entry-to-stop risk, and the stop
  line and chip turn green once trailing has carried them past the entry.
- The chart's drag headroom is applied only while deciding; once the trade is
  open the drag is fenced between the stop and the current close, both already
  on the scale, so the candles keep their range.

### Notes
- The stop only travels **towards** the price — up for a long, down for a short
  — and may never be dragged through it. Widening a stop to dodge a loss is the
  one habit the simulator refuses to teach, so the engine rejects the move
  rather than the page hiding it.
- `R` stays pinned to the entry-to-**original**-stop distance (`initialStop` is
  frozen at `openTrade`), so trailing never retroactively rescales a trade's
  result. A stop trailed to +0.62R that then fills reports exactly +0.62R.

## 2026-09-04 - Swing-Trading Simulator (v2 cockpit)

### Added
- `web/v2/simulator.html` + `web/v2/js/simulator.js` — a chart-reading trainer:
  a random S&P 500 name on a random date in the last five years, 35 sessions of
  candles with 9EMA / 22EMA / 200SMA / volume / MACD(12,26,9) histogram /
  RSI(14), a stop you drag onto the chart, then buy, short or pass. Entry fills
  at the next open, discretionary exits (half or all) at the close, the stop
  fills intraday. One mobile screen, no scrolling, nothing scored or stored.
- `web/v2/js/sim-indicators.js` and `web/v2/js/sim-engine.js` — the indicator
  math and the trade accounting as pure modules, with
  `tests/web/sim-indicators.test.js` and `tests/web/sim-engine.test.js`
  (22 tests) checking them against independently computed values.
- `config/sp500.csv` — the 503-name constituent universe (Wikipedia snapshot),
  read by `src.data.registry.load_ticker_csv`.
- `scripts/site/build_sim.py` — cache -> `web/v2/data/sim/<TICKER>.json`
  (OHLCV, ~7 years) + `sim-universe.json`, wired into `deploy.yml`.

### Changed
- `src.data.refresh` takes `--tickers-file` (a ticker CSV universe) and
  `--start` (a history floor applied only when a ticker has nothing cached),
  so seeding 500 names does not pull decades per ticker.
- `ci.yml` also runs the engine tests when `web/v2/js/**` changes.

### Notes
- The stop is live rather than decorative: a bar that trades through it closes
  the position at the stop, or at the open when the bar gapped past it. Results
  are quoted in percent and in R (result / entry-to-stop distance).

## 2026-08-05 - Portfolio Rebalancing Study

### Added
- `src/rebalancing/` — typed library for a multi-asset rebalancing study:
  data layer with committed CSV cache, validation gate, pluggable policy
  objects, a single-code-path backtest engine (plus a vectorised batch path
  for the bootstrap), metrics with a return/risk decomposition, block
  bootstrap, and figures.
- `scripts/rebalancing/run_study.py` — reproduces every table and chart in
  one command; `scripts/rebalancing/requirements.txt` pins the versions.
- `docs/rebalancing/{PLAN,report,README}.md`, `data/rebalancing/{cache,results,charts}/`.
- `tests/rebalancing/test_engine.py` — 20 tests, including exact
  cross-validation of the engine against analytic constant-mix and
  buy-and-hold, and of the batch path against the single path.

### Findings
- The hypothesis that rebalancing more often pays after a gold flight-to-safety
  crash does **not** survive. Event-triggered rebalancing beat monthly in four
  of eight crashes at the 3-year horizon, and lost in 2003 and 2009 — the two
  episodes the hypothesis says should be its best cases.
- Every investable policy lands within ~48bps/yr over 34.8 years, and none of
  the gaps is distinguishable from noise in a 2,000-replicate block bootstrap.
  The only distinguishable result is negative: daily rebalancing loses 215bps
  a year to costs.
- Unhedged sterling exposure added ~0.80%/yr to every asset — roughly twenty
  times the spread between the best and worst policies.

### Notes
- This study does **not** use the DuckDB `MarketStore`. It needs FRED macro
  series, LBMA fixings and spliced total-return indices that the instrument
  registry does not model, so it carries a self-contained committed CSV cache
  (2.7 MB) instead. It does use `src.data.paths`.

## 2026-06-12 - Data Persistence Upgrade

### Major Changes

**Unified data layer (`src/data/`) with a single DuckDB price cache**
- Prices moved from 54 per-symbol CSVs (`data/stock_history/`) to one
  DuckDB file (`data/market.duckdb`) — gitignored and regenerable.
- New `src/data/` package: `paths` (canonical locations), `registry`
  (instrument/portfolio source of truth, stdlib `tomllib`), `store`
  (`MarketStore` read API → pandas), `refresh` (the single ACID writer).
- `config/instruments.toml` + `config/portfolios.toml` — one place to define
  every instrument. The web build (`build_data.py` / `build_portfolios.py`)
  and the research universe now read from the registry.

### Why
- Removes 3 duplicated price loaders, two hardcoded absolute paths, and
  ~10 path-resolution boilerplate sites; collapses 4 scattered instrument
  lists into one registry. Scales to many instruments with fewer failure
  points (single writer, regenerable cache, no precious state).

### Migration / usage
- Fresh clone or CI: build the cache with `python -m src.data.refresh --full`.
- `scripts/tools/seed_duckdb.py` performed the one-off CSV → DuckDB migration.
- Added `duckdb>=1.0` to `environment.yml`. Web CI is unchanged (registry is
  stdlib-only).

## 2024-12-15 - Multi-Page Reorganization

### Major Changes

**Reorganized VIX Options Calculator into Multi-Page App**
- Transformed monolithic 881-line single-page app into 4-page workflow
- Created clear decision-making flow: Dashboard → Probability → Risk → Trade Plan
- Improved UX with focused, purpose-driven pages

### New Structure

**Page 1: Dashboard** (`scripts/vix_options_calculator.py`)
- Quick overview and trade verdict
- Key metrics snapshot
- Market context (VIX percentile, recent history)
- Navigation guide

**Page 2: Probability & Scenarios** (`scripts/pages/1_📈_Probability_&_Scenarios.py`)
- Historical spike probability analysis
- Time-to-spike distribution
- Multiple outcome scenarios
- Expected value breakdown

**Page 3: Risk Analysis** (`scripts/pages/2_⚠️_Risk_Analysis.py`)
- Theta decay visualization
- Daily/weekly/monthly decay impact
- Downside probability analysis
- Stop loss recommendations

**Page 4: Trade Plan** (`scripts/pages/3_💡_Trade_Plan.py`)
- Kelly Criterion position sizing
- Entry checklist with validation
- Profit target and stop loss strategies
- Execution tips

### New Modules

**Shared State Management** (`src/vix_analysis/shared_state.py`)
- Session state helpers for multi-page data sharing
- Custom CSS styling
- Utility functions (formatting, data loading)

### Bug Fixes

- Fixed `KeyError: 'gain_pct'` in Probability page by accessing original dataframe for highlighting logic

### Repository Cleanup

**Removed ETF-Related Scripts:**
- `vix_etf_strategy_analysis.py`
- `vix_decay_analysis.py`
- `vix_strategy_dashboard.py`

**Removed Exploratory Scripts** (functionality integrated into calculator):
- `vix_low_entry_analysis.py`
- `vix_spike_probability.py`
- `vix_risk_reward.py`
- `vix_regime_context.py`
- `vix_spike_duration_analysis.py`
- `vix_downside_analyzer.py`

**Archived:**
- Original monolithic calculator moved to `scripts/archive/`

### Documentation

**New Documentation:**
- `scripts/README.md` - App usage and structure guide
- `scripts/archive/README.md` - Archive explanation
- `docs/vix_range_low/APP_STRUCTURE.md` - Detailed architecture documentation

**Updated:**
- Main `README.md` - Updated with current focus and quick start

### Technical Improvements

- **Modular Architecture**: Clean separation of concerns
- **Session State**: Calculate once, use everywhere
- **Performance**: No redundant calculations across pages
- **Maintainability**: ~250 lines per page vs 881 monolithic
- **Scalability**: Easy to add new pages or features

### Migration Notes

The old monolithic version is preserved at `scripts/archive/vix_options_calculator.py` for reference.

To run the new multi-page app:
```bash
conda activate macro-beans
streamlit run scripts/vix_options_calculator.py
```

---

## Previous Updates

### 2024-12-15 - Refactoring to Modular Components

- Created `src/vix_analysis/` package with modular components:
  - `probability.py` - Probability calculations
  - `options_pricing.py` - Options valuation
  - `visualizations.py` - Chart generation
  - `ui_components.py` - Streamlit UI elements
- Replaced monolithic calculator with modular version

### 2024-12-15 - Downside Risk Analysis

- Added recency-weighted downside risk analysis
- Implemented stop loss recommendations
- Created `vix_downside_analyzer.py` standalone script
- Integrated downside section into calculator

### 2024-12-15 - Greeks Integration

- Added optional Greeks input (Theta, Vega)
- Updated calculations to use actual Greeks when provided
- Fixed Vega precision to 3 decimal places
- Created `GREEKS_GUIDE.md` documentation

### 2024-12-15 - VIX Spike Duration Analysis

- Created `vix_spike_duration_analysis.py`
- Analyzed median spike duration (5-7 days)
- Confirmed premium expansion strategy validity

### 2024-12-15 - Initial Calculator

- Created `vix_options_calculator.py` - Comprehensive Streamlit calculator
- Probability analysis, scenario modeling, expected value calculations

### 2024-12-15 - Pivot from ETFs to Options

- Analyzed VIX ETF contango decay issue
- Decided to focus on VIX call options instead of ETFs
- Created ETF analysis scripts for reference

### 2024-12-15 - Initial Research

- Created initial VIX low-entry strategy analysis scripts
- Developed probability, risk/reward, and regime analysis tools
