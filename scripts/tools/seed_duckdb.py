"""One-off migration: seed the DuckDB price cache from the legacy CSV cache.

Reads every ``data/stock_history/*.csv`` and upserts it into
``data/market.duckdb`` so the long histories already on disk are preserved
(no immediate re-fetch from yfinance). After this runs and parity is verified,
the CSV directory can be untracked from git -- the DuckDB file becomes the
source of truth, kept current by ``python -m src.data.refresh``.

Run:
    /usr/local/bin/python3 scripts/tools/seed_duckdb.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

# Make `src` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.paths import DATA_DIR, DB_PATH  # noqa: E402
from src.data.refresh import ensure_schema, normalize_ohlcv, upsert_prices  # noqa: E402

LEGACY_CSV_DIR = DATA_DIR / "stock_history"


def main() -> int:
    csvs = sorted(LEGACY_CSV_DIR.glob("*.csv"))
    if not csvs:
        print(f"No CSVs found in {LEGACY_CSV_DIR}; nothing to seed.")
        return 1

    print(f"Seeding {DB_PATH} from {len(csvs)} CSVs in {LEGACY_CSV_DIR}")
    con = duckdb.connect(str(DB_PATH), read_only=False)
    try:
        ensure_schema(con)
        for i, path in enumerate(csvs, 1):
            ticker = path.stem
            raw = pd.read_csv(path, index_col=0, parse_dates=True)
            tidy = normalize_ohlcv(raw, ticker)
            total = upsert_prices(con, ticker, tidy)
            print(f"[{i:>2}/{len(csvs)}] {ticker:<7} {len(tidy):>6} rows -> total {total}")
    finally:
        con.close()

    print("\nSeed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
