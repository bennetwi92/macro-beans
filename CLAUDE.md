# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Macro-beans is a Python-based repository for swing trading analysis and investigations. The project focuses on identifying opportunistic trading opportunities through ad-hoc analyses and scripts, with results presented via Streamlit apps.

## Environment Setup

**For Claude: use `/usr/local/bin/python3` directly** — it's Python 3.11 with the project deps already installed (yfinance, pandas, numpy, matplotlib, etc.). Conda is *not* on PATH on this machine, so `conda` commands and `conda run -n macro-beans ...` will fail. Do not search for conda envs — just call the interpreter directly:

```bash
/usr/local/bin/python3 scripts/your_script.py
```

To check whether a package is available before writing a script:
```bash
/usr/local/bin/python3 -c "import yfinance, pandas, numpy, matplotlib"
```

To install something missing:
```bash
/usr/local/bin/python3 -m pip install <pkg>
```

For human reference, the documented setup is conda-based (Python 3.11 per `environment.yml`):
```bash
conda env create -f environment.yml
conda activate macro-beans
```

## Repository Structure

Scripts, docs, and data are all organised by topic subdirectory:

```
scripts/
  mean_reversion/   # Scanner, walk-forward backtest, dashboard, training
  event_studies/    # Oil and copper event-study scripts
  vix_options/      # Streamlit calculator (pages/ subdir for multipage)
  storage_model/    # Gas storage dashboard
  tools/            # Generic market tools
  archive/          # Deprecated scripts
src/
  models/           # Mean-reversion model package
  storage_model/    # Gas storage valuation engine
  vix_analysis/     # VIX options analysis components
docs/
  mean_reversion/   event_studies/   reference/   vix_options/
data/
  event_studies/    backtests/   stock_history/
```

When adding new analyses:
- Drop the script into the matching topic subdir under `scripts/`. Use `Path(__file__).resolve().parents[2]` to resolve the repo root from inside any script.
- Write outputs to the matching topic subdir under `data/`.
- If reusable, factor library code into `src/<topic>/`.
- Document findings in the matching topic subdir under `docs/`.

## Development Workflow

- Scripts in `scripts/` are exploratory and investigation-focused.
- Streamlit apps present results; run from repo root, e.g. `streamlit run scripts/vix_options/vix_options_calculator.py`.
- Each analysis is self-contained and focused on a specific trading opportunity.

## Key Technologies

- **Language**: Python 3.11
- **Presentation**: Streamlit (for visualizing trading analysis results)
- **Environment**: Conda (documented) / system Python 3.11 (working)
