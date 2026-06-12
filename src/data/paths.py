"""Canonical filesystem locations for the repo.

Import these instead of recomputing ``Path(__file__).resolve().parents[N]``
in every script. This module has no third-party dependencies so it is safe to
import from anywhere (including the web build, which must stay duckdb-free).
"""

from __future__ import annotations

from pathlib import Path

# src/data/paths.py -> parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = REPO_ROOT / "data"
CONFIG_DIR = REPO_ROOT / "config"

# The single DuckDB price cache. Gitignored and regenerable; see refresh.py.
DB_PATH = DATA_DIR / "market.duckdb"

__all__ = ["REPO_ROOT", "DATA_DIR", "CONFIG_DIR", "DB_PATH"]
