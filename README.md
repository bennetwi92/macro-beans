# Macro-beans

Python-based swing trading analysis for opportunistic trading opportunities.

## Current Focus: VIX Options Strategy

This repository contains tools for analyzing VIX call options strategies, focusing on entering positions when VIX is at low levels (15-16 range) and profiting from volatility spikes.

## Quick Start

```bash
# Create and activate conda environment
conda env create -f environment.yml
conda activate macro-beans

# Run the VIX options calculator
streamlit run scripts/vix_options_calculator.py
```

## Repository Structure

```
macro-beans/
├── scripts/
│   ├── vix_options_calculator.py    # Main interactive calculator
│   └── archive/                     # Deprecated scripts
├── src/
│   └── vix_analysis/               # Modular analysis components
│       ├── probability.py          # Spike/downside probability calculations
│       ├── options_pricing.py      # Options valuation and scenarios
│       ├── visualizations.py       # Chart generation
│       └── ui_components.py        # Streamlit UI components
├── docs/
│   └── vix_range_low/
│       ├── vix_range_low_strategy.md   # Strategy overview
│       └── GREEKS_GUIDE.md             # Guide to using options Greeks
└── environment.yml                  # Conda environment specification
```

## VIX Options Calculator

The interactive calculator provides:
- **Probability Analysis**: Historical probability of VIX reaching target levels
- **Scenario Modeling**: Multiple VIX spike scenarios with expected values
- **Greeks Integration**: Input actual Theta and Vega from options chain
- **Downside Risk Analysis**: Recency-weighted stop loss recommendations
- **Theta Decay Visualization**: Chart showing decay vs spike scenarios
- **Trade Recommendations**: Position sizing and exit strategies

## Technology Stack

- **Language**: Python 3.11
- **UI Framework**: Streamlit
- **Data**: yfinance (VIX historical data)
- **Visualization**: Plotly
- **Environment**: Conda
