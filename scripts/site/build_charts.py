"""Build per-instrument chart data for the v2 cockpit.

Reads FULL daily history for each web-surface instrument from the DuckDB price
cache (via MarketStore — no yfinance) and writes one compact file per
instrument (so the chart page loads only what it draws) plus a small instrument
menu the chart's search box uses for type-ahead.

The cache is the single yfinance reader; seed/refresh it first (see
build_price_sheet.py):

    python -m src.data.refresh --surface web

Run:
    /usr/local/bin/python3 scripts/site/build_charts.py

Outputs:
    web/v2/data/instruments.json       {built_at, instruments:[{ticker,name,theme}]}
    web/v2/data/charts/<ticker>.json   {ticker, name, theme, bars:[[iso,close]]}
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `src` importable for the shared registry + price store.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import load_instruments_multi  # noqa: E402
from src.data.store import MarketStore  # noqa: E402

# Shared build helpers (compact-JSON writer, coverage gate).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BuildTally, write_json  # noqa: E402


def bars_all(df) -> list[list]:
    """Full history of a Date-indexed OHLCV frame as [iso, close] pairs."""
    return [
        [idx.strftime("%Y-%m-%d"), round(float(c), 4)]
        for idx, c in zip(df.index, df["Close"].values)
    ]


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "v2" / "data"
    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    instruments = load_instruments_multi("web", "cockpit")
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tally = BuildTally(len(instruments))
    menu = []

    try:
        store = MarketStore()  # read-only; raises if the cache hasn't been built
    except FileNotFoundError as exc:
        print(f"\n{exc}\nRun:  python -m src.data.refresh --full --surface web", file=sys.stderr)
        sys.exit(1)

    for inst in instruments:
        ticker = inst.web_ticker
        theme = inst.sublabel or inst.group or inst.category
        label = f"{inst.name} ({ticker})"
        print(f"  {label:<34s} ...", end=" ", flush=True)
        df = store.get_prices(ticker)
        if df.empty or len(df) < 2:
            print("NOT IN CACHE (run refresh --surface web)")
            tally.record_failure(label, RuntimeError("absent from price cache"))
            continue
        bars = bars_all(df)
        write_json(charts_dir / f"{ticker}.json",
                   {"ticker": ticker, "name": inst.name, "theme": theme, "bars": bars})
        menu.append({"ticker": ticker, "name": inst.name, "theme": theme})
        tally.record_ok()
        print(f"{len(bars):>5d} bars  ({bars[0][0]} .. {bars[-1][0]})")

    write_json(out_dir / "instruments.json", {"built_at": built_at, "instruments": menu})
    print(f"\nWrote {len(menu)} chart files + instruments.json ({len(menu)} entries)")
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
