# VIX Options Calculator - Multi-Page Structure

## Overview

The VIX Options Calculator has been reorganized from a single monolithic page into a **4-page workflow** that guides you through the decision-making process.

## Page Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     📊 DASHBOARD                             │
│                    (Main Entry Point)                        │
│                                                              │
│  • Quick verdict: Favorable/Moderate/Unfavorable            │
│  • Key metrics snapshot                                     │
│  • Market context (VIX percentile)                          │
│  • Navigation hints                                         │
│                                                              │
│  Decision: Is this worth pursuing?                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              📈 PROBABILITY & SCENARIOS                      │
│                 (Decision Analysis)                          │
│                                                              │
│  • Historical spike probability                             │
│  • Time-to-spike distribution                               │
│  • Multiple scenario outcomes (VIX 18-30)                   │
│  • Expected value breakdown                                 │
│                                                              │
│  Decision: What are my chances and potential payoffs?       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                  ⚠️ RISK ANALYSIS                            │
│                 (Risk Management)                            │
│                                                              │
│  • Theta decay visualization                                │
│  • Daily decay impact                                       │
│  • Downside probabilities                                   │
│  • Recommended stop losses                                  │
│  • Risk/reward summary                                      │
│                                                              │
│  Decision: What can go wrong and how do I protect capital?  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   💡 TRADE PLAN                              │
│                   (Execution)                                │
│                                                              │
│  • Kelly Criterion position sizing                          │
│  • Entry checklist                                          │
│  • Profit target strategy                                   │
│  • Stop loss implementation                                 │
│  • Time-based exits                                         │
│  • Execution tips                                           │
│                                                              │
│  Decision: How much to risk and when to exit?               │
└─────────────────────────────────────────────────────────────┘
```

## Sidebar (Global Config)

The sidebar is visible on all pages and contains all inputs:

```
⚙️ Configuration
├── Contract Details
│   ├── Select Contract (Jan/Feb/Custom)
│   ├── Entry Premium
│   ├── Days to Expiration (DTE)
│   ├── Strike Price
│   └── Number of Contracts
│
├── Greeks (Optional)
│   ├── Use Actual Greeks [checkbox]
│   ├── Theta (Daily)
│   └── Vega
│
├── Market Assumptions
│   ├── Entry VIX Level
│   ├── Target VIX Level
│   ├── Monthly Theta Decay %
│   └── Analysis Window (days)
│
└── Exit Strategy
    ├── Profit Target %
    └── Stop Loss %
```

## Benefits of Multi-Page Structure

### ✅ Clear Mental Model
Each page has a specific purpose in your decision workflow:
1. **Dashboard** → Quick yes/no
2. **Probability** → Likelihood of success
3. **Risk** → What can go wrong
4. **Trade Plan** → How to execute

### ✅ Less Overwhelming
Instead of scrolling through 400+ lines of output, you get focused analysis on each page.

### ✅ Better Navigation
Jump directly to what you need:
- Quick check? → Dashboard
- Need probabilities? → Page 2
- Worried about risk? → Page 3
- Ready to trade? → Page 4

### ✅ Faster Performance
- Calculations happen once on Dashboard
- Results cached in session state
- Other pages just read cached data
- No redundant computations

### ✅ Easier Maintenance
- Each page is ~200-300 lines (vs 881 monolithic)
- Clear separation of concerns
- Easy to add new pages or features
- Modular backend (src/vix_analysis/)

## Technical Architecture

### Session State Management

```python
# Dashboard calculates and stores
set_calculated_data({
    'spike_prob': ...,
    'scenarios_df': ...,
    'downside_probs': ...,
    ...
})

# Other pages just read
calculated_data = get_calculated_data()
spike_prob = calculated_data['spike_prob']
```

### Modular Backend

```
src/vix_analysis/
├── __init__.py              # Package exports
├── probability.py           # Spike/downside calculations
├── options_pricing.py       # Option valuation models
├── visualizations.py        # Plotly charts
├── ui_components.py         # Streamlit UI elements
└── shared_state.py          # Session state helpers
```

### Page Independence

Each page is self-contained:
- Imports only what it needs
- Reads from session state
- No cross-page dependencies
- Can be developed/tested independently

## File Structure

```
scripts/
├── vix_options_calculator.py          # Main dashboard (home page)
├── pages/
│   ├── 1_📈_Probability_&_Scenarios.py
│   ├── 2_⚠️_Risk_Analysis.py
│   └── 3_💡_Trade_Plan.py
├── archive/
│   ├── vix_options_calculator.py      # Original monolithic version
│   └── README.md
└── README.md                           # This guide
```

## Migration from Old Version

**Old (Monolithic):**
- 881 lines in one file
- Scroll to find sections
- All calculations inline
- Hard to maintain

**New (Multi-Page):**
- ~200-300 lines per page
- Navigate via sidebar
- Calculations in shared modules
- Easy to extend

The old version is archived at `scripts/archive/vix_options_calculator.py` for reference.

## Running the App

```bash
conda activate macro-beans
streamlit run scripts/vix_options/vix_options_calculator.py
```

Streamlit automatically discovers pages in the `pages/` directory and creates navigation in the sidebar.

## Future Enhancements

Possible additions (easy with multi-page structure):

- **📊 Historical Backtests** page - backtest the strategy
- **📝 Trade Journal** page - log and track trades
- **🔔 Alerts** page - set VIX alerts
- **📚 Education** page - explain VIX, Greeks, etc.

Each new page is just a new file in `pages/` directory!
