# Macro-beans

Python-based swing trading analysis. Personal research repo for opportunistic trade ideas — mean-reversion scanning, event studies, VIX options, gas storage modelling.

## Quick start

```bash
# Conda environment (per environment.yml)
conda env create -f environment.yml
conda activate macro-beans

# Or use the system Python 3.11 directly (deps already installed)
/usr/local/bin/python3 scripts/event_studies/copper_event_study.py
```

## Repository structure

```
macro-beans/
├── scripts/
│   ├── mean_reversion/      # Production mean-reversion scanner + backtest + dashboard
│   ├── event_studies/       # One-off macro/geopolitical event studies (oil, copper)
│   ├── vix_options/         # VIX options calculator (Streamlit multipage app)
│   ├── storage_model/       # Gas storage model dashboard
│   ├── tools/               # General market tools (data download, dashboards)
│   └── archive/             # Deprecated scripts
├── src/
│   ├── models/              # Mean-reversion model package (config, features, model)
│   ├── storage_model/       # Gas storage valuation engine
│   └── vix_analysis/        # VIX options analysis components
├── docs/
│   ├── mean_reversion/      # Strategy guide and backtest writeups
│   ├── event_studies/       # Event-study reports + trade records
│   ├── reference/           # Reference docs (LSE ETF universe, project setup)
│   └── vix_options/         # VIX options strategy docs
├── data/
│   ├── event_studies/       # Output CSVs and charts from event-study scripts
│   ├── backtests/           # Backtest results CSVs
│   └── stock_history/       # Cached yfinance OHLCV data
├── models/                  # Pickled trained models
├── environment.yml
├── CLAUDE.md                # Guidance for Claude Code (Python interpreter, conventions)
└── README.md
```

## Active strategies / components

- **Mean reversion** (`scripts/mean_reversion/`, `src/models/`) — scan mega-cap tech for mean-reversion setups; walk-forward backtested. See `docs/mean_reversion/mean_reversion_strategy_guide.md`.
- **Event studies** (`scripts/event_studies/`, `docs/event_studies/`) — analyse historical reactions to oil/copper geopolitical events to inform LSE inverse/leveraged ETF pair trades. See `docs/event_studies/event_driven_trading_framework.md`.
- **LSE inverse/leveraged ETF universe** — reference for relative-value pair-trade construction. See `docs/reference/lse_inverse_leveraged_etf_universe.md`.
- **VIX options calculator** (`scripts/vix_options/`) — Streamlit multipage app for sizing VIX call positions. Run with `streamlit run scripts/vix_options/vix_options_calculator.py`.
- **Gas storage model** (`scripts/storage_model/`, `src/storage_model/`) — replica of a real gas storage valuation model.

## Tech stack

Python 3.11 · pandas / numpy · yfinance · matplotlib / plotly · Streamlit
