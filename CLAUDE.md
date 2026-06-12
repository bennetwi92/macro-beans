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
config/
  instruments.toml  # Instrument registry (single source of truth)
  portfolios.toml   # Pair-portfolio registry (web)
scripts/
  mean_reversion/   # Scanner, walk-forward backtest, dashboard, training
  event_studies/    # Oil and copper event-study scripts
  vix_options/      # Streamlit calculator (pages/ subdir for multipage)
  storage_model/    # Gas storage dashboard
  site/             # Build scripts for the public web platform (see below)
  tools/            # Generic market tools (incl. seed_duckdb.py migration)
  archive/          # Deprecated scripts
src/
  data/             # Unified data layer: paths, registry, MarketStore, refresh
  models/           # Mean-reversion model package
  storage_model/    # Gas storage valuation engine
  vix_analysis/     # VIX options analysis components
docs/
  mean_reversion/   event_studies/   reference/   vix_options/
data/
  event_studies/    backtests/        # CSV/PNG analysis outputs (committed)
  market.duckdb                       # Price cache (gitignored, regenerable)
web/                # Public static site (Macro Beans web platform)
.github/workflows/  # CI/CD for the web platform (deploy.yml)
```

### Data layer (`src/data/`)

Market prices live in a single DuckDB file (`data/market.duckdb`), **not**
per-symbol CSVs. It is gitignored and regenerable — there is no precious
state. The instrument universe is defined once in `config/instruments.toml`.

- **Read prices:** `from src.data.store import MarketStore` →
  `MarketStore().get_prices("AAPL")` returns a Date-indexed OHLCV frame.
  Read-only; safe to call from many processes.
- **Write/refresh prices:** `python -m src.data.refresh [--full] [--tickers AAPL,MSFT]`
  is the *only* writer (single-writer, ACID). Default is an incremental update
  of the research universe from the registry.
- **Paths:** `from src.data.paths import REPO_ROOT, DATA_DIR, CONFIG_DIR, DB_PATH`
  instead of recomputing `Path(__file__).resolve().parents[2]`.
- **Registry:** `from src.data.registry import load_instruments, load_portfolios`
  (stdlib `tomllib` only — no duckdb, so the web build can use it). Add an
  instrument = one `[[instrument]]` block in `config/instruments.toml`.
- **First-time / fresh clone:** build the cache with
  `python -m src.data.refresh --full`. (`scripts/tools/seed_duckdb.py` was the
  one-off migration from the legacy CSVs.)

When adding new analyses:
- Drop the script into the matching topic subdir under `scripts/`. Use
  `src.data.paths` for repo/data locations and `MarketStore` for prices.
- Write CSV/PNG outputs to the matching topic subdir under `data/`.
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
