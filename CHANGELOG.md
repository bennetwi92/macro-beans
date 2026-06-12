# Changelog

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
