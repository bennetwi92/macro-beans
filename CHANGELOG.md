# Changelog

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
