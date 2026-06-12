"""Unified data layer for macro-beans.

Single source of truth for:
  * paths        -- repo/data/config locations (paths.py)
  * the registry -- every instrument & portfolio (registry.py)
  * price reads  -- MarketStore, DuckDB -> pandas (store.py)
  * price writes -- refresh from yfinance (refresh.py)

The price cache lives in a single DuckDB file (``data/market.duckdb``) that
is gitignored and regenerable: corruption or staleness is always recoverable
by re-running ``python -m src.data.refresh``. Only ``refresh.py`` opens the
DB read-write; everything else reads it read-only.

This package ``__init__`` deliberately imports **only stdlib-backed modules**
(paths, registry). The duckdb/pandas-backed ``store`` and ``refresh`` modules
are imported explicitly (``from src.data.store import MarketStore``) so the
public web build can use the registry without pulling in duckdb.
"""

from src.data.paths import REPO_ROOT, DATA_DIR, CONFIG_DIR, DB_PATH
from src.data.registry import (
    Instrument,
    Portfolio,
    PortfolioLeg,
    load_instruments,
    load_portfolios,
    research_tickers,
)

__all__ = [
    "REPO_ROOT",
    "DATA_DIR",
    "CONFIG_DIR",
    "DB_PATH",
    "Instrument",
    "Portfolio",
    "PortfolioLeg",
    "load_instruments",
    "load_portfolios",
    "research_tickers",
]
