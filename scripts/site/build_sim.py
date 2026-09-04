"""Build the swing-trading simulator universe for the v2 cockpit.

The simulator drops you on a random S&P 500 name at a random date in the last
five years, shows 35 bars of history, and asks you to trade it. That needs
OHLCV (candles + volume), enough warm-up history to seed a 200-day SMA, and
enough forward history to run the trade out — per ticker, fetched one file at
a time by the browser so a session downloads ~70 KB, not the whole universe.

Reads the DuckDB price cache via MarketStore (no yfinance here — the cache is
the single reader). Seed/refresh it first:

    python -m src.data.refresh --tickers-file config/sp500.csv --start 2018-01-01

Run:
    /usr/local/bin/python3 scripts/site/build_sim.py

Outputs:
    web/v2/data/sim-universe.json    {built_at, tickers:[{t,n,s,b,f,l}]}
    web/v2/data/sim/<TICKER>.json    {ticker, name, sector, bars:[[iso,o,h,l,c,v]]}

Bars carry the full OHLC because the simulator needs each one: open is the
entry fill (you buy the morning after the decision), high/low decide whether
the stop was hit intraday, close is where discretionary exits fill.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `src` importable for the shared universe list + price store.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import SP500_CSV, load_ticker_csv  # noqa: E402
from src.data.store import MarketStore  # noqa: E402

# Shared build helpers (compact-JSON writer, coverage gate).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BuildTally, write_json  # noqa: E402

# History kept per ticker: ~6.5 years. The simulator picks decision dates from
# the last 5 years and needs 200 bars of warm-up before the earliest one plus
# room to run the trade forward, so anything beyond this is dead weight.
MAX_BARS = 1700

# Minimum bars for a ticker to be playable at all: 200 (SMA warm-up) + 35
# (lookback window) + 60 (forward runway) + slack. Recent IPOs fall short and
# are skipped rather than shipped as a dead-end pick.
MIN_BARS = 320


def bars_ohlcv(df) -> list[list]:
    """The tail of a Date-indexed OHLCV frame as [iso, o, h, l, c, v] rows.

    Prices are rounded to 2dp (cents — these are US listings) and volume to a
    whole number of shares; a missing/zero open falls back to the close so the
    simulator's next-open entry can never divide by zero.
    """
    tail = df.tail(MAX_BARS)
    out = []
    for idx, o, h, l, c, v in zip(
        tail.index,
        tail["Open"].values,
        tail["High"].values,
        tail["Low"].values,
        tail["Close"].values,
        tail["Volume"].values,
    ):
        o, h, l, c = float(o), float(h), float(l), float(c)
        if not (o > 0):
            o = c
        out.append(
            [
                idx.strftime("%Y-%m-%d"),
                round(o, 2),
                round(max(h, o, c), 2),
                round(min(l, o, c), 2),
                round(c, 2),
                int(v) if v == v else 0,  # NaN volume -> 0
            ]
        )
    return out


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "v2" / "data"
    sim_dir = out_dir / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)

    universe = load_ticker_csv(SP500_CSV)
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tally = BuildTally(len(universe))
    menu = []

    try:
        store = MarketStore()  # read-only; raises if the cache hasn't been built
    except FileNotFoundError as exc:
        print(
            f"\n{exc}\nRun:  python -m src.data.refresh "
            f"--tickers-file config/sp500.csv --start 2018-01-01",
            file=sys.stderr,
        )
        sys.exit(1)

    for row in universe:
        df = store.get_prices(row.ticker)
        if df.empty or len(df) < MIN_BARS:
            have = len(df)
            print(f"  {row.ticker:<6s} SKIP ({have} bars < {MIN_BARS})")
            tally.record_failure(row.ticker, RuntimeError(f"only {have} bars cached"))
            continue
        bars = bars_ohlcv(df)
        write_json(
            sim_dir / f"{row.ticker}.json",
            {
                "ticker": row.ticker,
                "name": row.name,
                "sector": row.sector,
                "bars": bars,
            },
        )
        menu.append(
            {
                "t": row.ticker,
                "n": row.name,
                "s": row.sector,
                "b": len(bars),
                "f": bars[0][0],
                "l": bars[-1][0],
            }
        )
        tally.record_ok()

    write_json(out_dir / "sim-universe.json", {"built_at": built_at, "tickers": menu})
    print(f"\nWrote {len(menu)} simulator files + sim-universe.json")
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
