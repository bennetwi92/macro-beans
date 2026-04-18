# VIX Options Calculator

Multi-page Streamlit application for analyzing VIX call options strategies.

## Running the App

```bash
# Ensure you're in the macro-beans environment
conda activate macro-beans

# Run from the repository root
streamlit run scripts/vix_options/vix_options_calculator.py
```

The app will open in your browser at http://localhost:8501

## Application Structure

The calculator is organized into 4 pages for a clear decision-making workflow:

### 📊 Dashboard (Home Page)
**File:** `vix_options_calculator.py`

Quick overview and trade verdict:
- Overall setup rating (Favorable/Moderate/Unfavorable)
- Key metrics at a glance
- Market context (VIX percentile, recent history)
- Navigation guide to other pages

**Use this page to:** Get a quick yes/no on whether the setup is worth pursuing.

---

### 📈 Probability & Scenarios (Page 2)
**File:** `pages/1_📈_Probability_&_Scenarios.py`

Detailed probability analysis:
- Historical spike probability
- Time-to-spike distribution
- Multiple outcome scenarios (VIX → 18, 20, 22, 25, 30)
- Expected value breakdown

**Use this page to:** Understand the likelihood of success and potential payoffs.

---

### ⚠️ Risk Analysis (Page 3)
**File:** `pages/2_⚠️_Risk_Analysis.py`

Risk management analysis:
- Theta decay visualization
- Daily/weekly/monthly decay impact
- Downside probability analysis
- Recommended stop losses
- Risk/reward summary

**Use this page to:** Understand what can go wrong and how to protect yourself.

---

### 💡 Trade Plan (Page 4)
**File:** `pages/3_💡_Trade_Plan.py`

Execution planning:
- Kelly Criterion position sizing
- Entry checklist
- Profit target strategy (scaling out)
- Stop loss recommendations
- Time-based exits
- Execution tips (spreads, timing)

**Use this page to:** Plan your exact entry, position size, and exit strategy.

---

## Shared Components

### Sidebar (Global)
Configure all inputs once in the sidebar, and they persist across all pages:
- Contract details (premium, DTE, strike, number of contracts)
- Greeks (optional: Theta, Vega from options chain)
- Market assumptions (entry VIX, target VIX)
- Exit strategy (profit target, stop loss)

### Modular Backend (`src/vix_analysis/`)
- `probability.py` - Spike and downside probability calculations
- `options_pricing.py` - Option valuation and scenario modeling
- `visualizations.py` - Plotly charts
- `ui_components.py` - Streamlit UI elements (sidebar, tables)
- `shared_state.py` - Session state management for multi-page app

## Data Flow

1. **Dashboard page** loads first
2. User configures inputs in **sidebar**
3. Dashboard **calculates all data** and stores in session state
4. Other pages **read from session state** (fast, no recalculation)
5. User navigates between pages to review different aspects

## Key Features

✅ **Single source of inputs:** Configure once, use everywhere
✅ **Fast navigation:** Data calculated once, cached in session state
✅ **Clear workflow:** Dashboard → Analysis → Risk → Execute
✅ **Modular code:** Easy to maintain and extend
✅ **Professional UI:** Clean, organized, mobile-friendly

## Archive

The `archive/` directory contains the original monolithic version of the calculator, kept for reference.

---

# Market Dashboard

A terminal-based daily market scanner that displays technical indicators for your stock universe.

## Setup

1. Make sure you have conda installed
2. Create/update the conda environment:

```bash
conda env create -f environment.yml
```

Or if the environment already exists:

```bash
conda env update -f environment.yml --prune
```

3. Activate the environment:

```bash
conda activate macro-beans
```

## Usage

Run the dashboard from the repository root:

```bash
python scripts/market_dashboard.py
```

Or make it executable and run directly:

```bash
./scripts/market_dashboard.py
```

## What It Shows

The dashboard displays a table organized into three tiers of stocks:

**Tier 1**: SPY, QQQ, TSLA, NVDA, AAPL
**Tier 2**: AMD, F, BAC, MSFT, AMZN
**Tier 3**: META, GM, SMCI, GOOGL, INTC, XOM, JPM, IWM, AVGO, SLV

For each stock, the dashboard shows:
- **Ticker & Company Name**: Stock symbol and full company name
- **Previous Day Close**: The closing price from the last complete trading day
- **20, 50, 200-day EMAs**: Exponential Moving Averages with color coding
- **RSI (14)**: Relative Strength Index
- **MACD Histogram**: MACD histogram value (12, 26, 9 settings)
- **ADX (14)**: Average Directional Index (trend strength)

Each indicator shows:
- Current value
- Direction arrow (↑ up, ↓ down, → unchanged from previous day)
- Color coding based on technical significance

## Color Guide

- **EMAs**: Green = price above EMA (bullish), Red = price below EMA (bearish)
- **RSI**: Red > 70 (overbought), Green < 30 (oversold), Yellow = neutral (30-70)
- **MACD Histogram**: Green > 0 (bullish momentum), Red < 0 (bearish momentum)
- **ADX**: Green > 25 (strong trend), Yellow ≤ 25 (weak trend)

## Notes

- Only complete trading days are included (market must be closed)
- If run during market hours, today's incomplete data is excluded
- Data is fetched fresh from Yahoo Finance on each run
- Perfect for starting your daily market research routine
