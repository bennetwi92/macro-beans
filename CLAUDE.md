# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Macro-beans is a personal trading-research repository. It contains:

- **Research scripts** in Python that investigate specific trading
  opportunities — event studies, beta-hedged pair backtests, mean-reversion
  scanners, gas-storage valuation, VIX options analysis. Results land in
  `data/<topic>/` and are sometimes wrapped in Streamlit dashboards.
- **A public website** — the Macro Beans web platform at
  https://bennetwi92.github.io/macro-beans/ — a beginner-friendly,
  arcade-styled site that exposes a small set of these analyses to
  retail traders.

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
  site/             # Build scripts for the public web platform (see below)
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
web/                # Public static site (Macro Beans web platform)
.github/workflows/  # CI/CD for the web platform (deploy.yml)
```

When adding new analyses:
- Drop the script into the matching topic subdir under `scripts/`. Use `Path(__file__).resolve().parents[2]` to resolve the repo root from inside any script.
- Write outputs to the matching topic subdir under `data/`.
- If reusable, factor library code into `src/<topic>/`.
- Document findings in the matching topic subdir under `docs/`.

## Development Workflow

Work in this repo falls into two broad tracks. Identify which one a
request belongs to before starting:

1. **Research / studies** — exploratory scripts in `scripts/<topic>/`
   that fetch data, compute, and write outputs (CSV / PNG) into
   `data/<topic>/`. Self-contained Python, often paired with a docs
   note under `docs/<topic>/`. Streamlit apps may present results.
2. **Public web platform** — the static site under `web/` (sources),
   `scripts/site/` (build scripts), and `.github/workflows/deploy.yml`
   (CI/CD), served at https://bennetwi92.github.io/macro-beans/. A
   beginner-friendly arcade-styled analytics site.

A change usually belongs to exactly one track. If you're tempted to
straddle both, stop and split the work.

## Project skills

Skill files in `.claude/skills/` document specific workflows in depth.
**Always consult the relevant skill before starting work in its area** —
treat its rules as binding even if the prompt doesn't mention them.
Skills auto-activate for relevant prompts, but the catalog below makes
the mapping explicit.

| Skill | Read it when |
|-------|--------------|
| [`macro-beans-site`](.claude/skills/macro-beans-site/SKILL.md) | Touching anything under `web/`, `scripts/site/`, or `.github/workflows/`; adding an instrument / portfolio / strategy page; deploying the site; or changing the public site's design, copy, or data pipeline. |

More skills may be added over time (e.g. for producing event
studies / research). Check `.claude/skills/` for the current set.

## Key Technologies

- **Language**: Python 3.11
- **Internal presentation**: Streamlit (for ad-hoc analysis dashboards)
- **Public presentation**: static HTML/CSS/vanilla-ES-module JS site under `web/`, served via GitHub Pages
- **Environment**: Conda (documented) / system Python 3.11 (working)
