"""``python -m portfolio_optimiser`` -> run the full report pipeline."""

from __future__ import annotations

import argparse

from .report.build_report import main

if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="portfolio_optimiser", description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch market data")
    args = ap.parse_args()
    main(refresh=args.refresh)
