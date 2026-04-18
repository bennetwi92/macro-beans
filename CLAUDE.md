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

- `scripts/` - Ad-hoc investigation scripts for trading opportunities
- `src/` - Source code for reusable components and utilities
- `docs/` - Documentation files

## Development Workflow

Since this is a project for ad-hoc trading analyses:
- Scripts in `scripts/` are expected to be exploratory and investigation-focused
- Streamlit apps should be used to present analysis results
- Each analysis should be self-contained and focused on specific trading opportunities

## Key Technologies

- **Language**: Python 3.11
- **Presentation**: Streamlit (for visualizing trading analysis results)
- **Environment**: Conda
