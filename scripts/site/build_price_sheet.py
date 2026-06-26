"""Build the v2 cockpit price-sheet data.

Reads daily bars for each web-surface instrument from the **DuckDB price cache**
(via MarketStore — no yfinance here) and ships a compact slice of recent bars
per instrument. The browser computes every metric (latest/open/gap, period
returns, RSI, price vs 200-day average, vols) AS OF the date picked on the page
— see web/v2/js/price-metrics.js — so the date picker recomputes the whole
sheet without a rebuild.

The cache is the single yfinance reader; this build only consumes it. Seed/
update it first (incremental after the first run, so we don't hammer yfinance):

    python -m src.data.refresh --surface web          # incremental top-up
    python -m src.data.refresh --full --surface web   # first time / full rebuild

Then:
    /usr/local/bin/python3 scripts/site/build_price_sheet.py

Output:
    web/v2/data/price-sheet.json
        {built_at, instruments:[{ticker, name, theme, bars:[[iso,close]]}]}

Bars are [iso_date, close] pairs (open is not shipped — the LAST/OPEN/GAP
columns are hidden for overnight/EOD data). N_BARS controls how far back the
date picker can reach: ~252 trading days of history before a chosen date are
needed for the 1-year / 200-day / vol metrics, so N_BARS bars allow as-of
dates within roughly the most recent (N_BARS - 252) trading days.
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

N_BARS = 800  # ~3.2y of trading days -> ~2y of pickable as-of dates


def bars_from(df) -> list[list]:
    """Last N_BARS rows of a Date-indexed OHLCV frame as [iso, close]."""
    tail = df.tail(N_BARS)
    return [
        [idx.strftime("%Y-%m-%d"), round(float(c), 4)]
        for idx, c in zip(tail.index, tail["Close"].values)
    ]


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "v2" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    instruments = load_instruments_multi("web", "cockpit")
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tally = BuildTally(len(instruments))
    out = []

    try:
        store = MarketStore()  # read-only; raises if the cache hasn't been built
    except FileNotFoundError as exc:
        print(f"\n{exc}\nRun:  python -m src.data.refresh --full --surface web", file=sys.stderr)
        sys.exit(1)

    for inst in instruments:
        ticker = inst.web_ticker
        # Provisional theme: the registry has no theme field yet, so use the
        # sublabel (most descriptive) and fall back to group/category.
        theme = inst.sublabel or inst.group or inst.category
        label = f"{inst.name} ({ticker})"
        print(f"  {label:<34s} ...", end=" ", flush=True)
        df = store.get_prices(ticker)
        if df.empty or len(df) < 2:
            print("NOT IN CACHE (run refresh --surface web)")
            tally.record_failure(label, RuntimeError("absent from price cache"))
            continue
        bars = bars_from(df)
        out.append({"ticker": ticker, "name": inst.name, "theme": theme, "bars": bars})
        tally.record_ok()
        print(f"{len(bars):>4d} bars  ({bars[0][0]} .. {bars[-1][0]})")

    payload = {"built_at": built_at, "instruments": out}
    n_bytes = write_json(out_dir / "price-sheet.json", payload)
    print(f"\nWrote price-sheet.json ({len(out)} instruments, {n_bytes / 1024:.0f} kB)")
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
