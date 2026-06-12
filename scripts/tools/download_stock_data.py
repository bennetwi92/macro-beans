"""Stock data download/refresh — compatibility shim.

The price cache moved from per-symbol CSVs to a single DuckDB file
(``data/market.duckdb``). This script now delegates to the unified writer in
``src.data.refresh`` and the read API in ``src.data.store``; the universe comes
from the registry (``config/instruments.toml``), not a hardcoded list here.

Usage:
    python scripts/tools/download_stock_data.py          - incremental update
    python scripts/tools/download_stock_data.py refresh  - full re-fetch
    python scripts/tools/download_stock_data.py recent    - incremental update
    python scripts/tools/download_stock_data.py info      - show cache catalog
    python scripts/tools/download_stock_data.py help

Prefer calling the new layer directly:
    python -m src.data.refresh [--full] [--tickers AAPL,MSFT]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.refresh import refresh  # noqa: E402
from src.data.registry import research_tickers  # noqa: E402
from src.data.store import MarketStore  # noqa: E402


def cache_info() -> None:
    """Show the per-ticker catalog from the DuckDB meta table."""
    store = MarketStore()
    meta = store.meta()
    if meta.empty:
        print("Cache is empty. Build it with: python -m src.data.refresh --full")
        return
    print(f"Cached tickers: {len(meta)}\n")
    print(meta.to_string(index=False))


def main(argv: list[str]) -> int:
    command = argv[1].lower() if len(argv) > 1 else "recent"

    if command in ("refresh", "full"):
        refresh(research_tickers(), full=True)
    elif command in ("recent", "update", "download"):
        refresh(research_tickers(), full=False)
    elif command == "info":
        cache_info()
    elif command == "help":
        print(__doc__)
    else:
        print(f"Unknown command: {command}\nRun with 'help' for usage.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
