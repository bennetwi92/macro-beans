"""Build the market-context feed for the swing-trading simulator.

The simulator deals a random S&P 500 chart on a random past date and asks you
to trade it. This file is what lets it also answer "and what was the market
doing that day?" — the trend of SPY / QQQ / IWM, where the stock's sector ETF
ranked against the other ten, and whether the VIX was spiking.

One file, not fifteen: it is fetched once per session and read at every bar,
so a per-ticker split would cost fourteen extra round trips to save nothing.
Closes only (~200 KB) — the market panel draws no candles.

Every series is reindexed onto SPY's trading calendar and forward-filled, so
`dates[i]` addresses every symbol at once and the browser never has to align
two calendars mid-render. A leading gap (an ETF that listed later than the
window starts) stays `null` and the browser treats it as "no reading".

Reads the DuckDB price cache via MarketStore (no yfinance here — the cache is
the single reader). Seed/refresh it first:

    python -m src.data.refresh --tickers-file config/market_context.csv --start 2018-01-01

Run:
    /usr/local/bin/python3 scripts/site/build_sim_market.py

Outputs:
    web/v2/data/sim-market.json
      {built_at, dates:[iso], close:{SYM:[float|null]}, sectors:{GICS: ETF}}
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `src` importable for the shared universe list + price store.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.paths import CONFIG_DIR  # noqa: E402
from src.data.registry import load_ticker_csv  # noqa: E402
from src.data.store import MarketStore  # noqa: E402

# Shared build helpers (compact-JSON writer, coverage gate).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BuildTally, write_json  # noqa: E402

UNIVERSE_CSV = CONFIG_DIR / "market_context.csv"

# Same window the simulator itself keeps (~6.5 years): decision dates come from
# the last five, and the weekly 50-week average behind the earliest of them
# needs about a year of run-up.
MAX_BARS = 1700

# Sector column values that are not GICS sectors, so never part of the map.
NON_SECTORS = {"Benchmark", "Volatility"}

# The benchmark defines the calendar and the whole feature: without it there is
# no market context to publish, so a missing SPY fails this build rather than
# shipping a file the browser would have to second-guess.
BENCHMARK = "SPY"

# The VIX is `^VIX` upstream; `^` in a JSON key is needless friction.
KEY = {"^VIX": "VIX"}

# Coverage gate. Fifteen of the most liquid tickers listed — if three are
# missing something is wrong upstream. Below this the file is still written
# (the browser degrades a short ranking gracefully) but the build says so
# loudly; the deploy only fails when the benchmark itself is gone.
MIN_COVERAGE = 0.8


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "v2" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    universe = load_ticker_csv(UNIVERSE_CSV)
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tally = BuildTally(len(universe), min_ok_fraction=MIN_COVERAGE)

    try:
        store = MarketStore()  # read-only; raises if the cache hasn't been built
    except FileNotFoundError as exc:
        print(
            f"\n{exc}\nRun:  python -m src.data.refresh "
            f"--tickers-file config/market_context.csv --start 2018-01-01",
            file=sys.stderr,
        )
        sys.exit(1)

    frames = {}
    for row in universe:
        df = store.get_prices(row.ticker)
        if df.empty or "Close" not in df:
            print(f"  {row.ticker:<6s} SKIP (nothing cached)")
            tally.record_failure(row.ticker, RuntimeError("nothing cached"))
            continue
        frames[row.ticker] = df["Close"].tail(MAX_BARS).astype(float)
        tally.record_ok()

    if BENCHMARK not in frames:
        print(f"\n{BENCHMARK} is not in the cache — no market context to build.", file=sys.stderr)
        sys.exit(1)

    # SPY's sessions are the calendar. Everything else is reindexed onto it and
    # forward-filled: a sector ETF that missed a print reads as unchanged, which
    # is what a chart would show, rather than shifting every later bar by one.
    dates = frames[BENCHMARK].index
    close = {}
    for ticker, series in frames.items():
        aligned = series.reindex(dates).ffill()
        close[KEY.get(ticker, ticker)] = [
            None if v != v else round(float(v), 2) for v in aligned.values
        ]

    sectors = {
        row.sector: row.ticker
        for row in universe
        if row.sector and row.sector not in NON_SECTORS and row.ticker in frames
    }

    size = write_json(
        out_dir / "sim-market.json",
        {
            "built_at": built_at,
            "dates": [d.strftime("%Y-%m-%d") for d in dates],
            "close": close,
            "sectors": sectors,
        },
    )
    print(
        f"\nWrote sim-market.json — {len(close)} series x {len(dates)} sessions, "
        f"{len(sectors)} sectors mapped, {size / 1024:.0f} KB"
    )
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
