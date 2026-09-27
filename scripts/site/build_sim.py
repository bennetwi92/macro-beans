"""Build the swing-trading simulator universe for the v2 cockpit.

The simulator drops you on a random S&P 500 name at a random date anywhere in
its history, shows 35 bars (daily, or weekly bars it resamples from these), and
asks you to trade it. That needs OHLCV (candles + volume), enough warm-up
history to seed the longest average, and enough forward history to run the
trade out — per ticker, fetched one file at a time by the browser, so a
session downloads one name's history rather than the whole universe.

Every bar the cache holds is shipped. A long-listed name (KO, IBM, GE) goes
back to 1962, which is ~16,000 bars and several hundred KB of JSON; that is
the price of dealing from every market regime rather than just the last one.

Reads the DuckDB price cache via MarketStore (no yfinance here — the cache is
the single reader). Seed/refresh it first:

    python -m src.data.refresh --tickers-file config/sp500.csv

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

import math
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

# Minimum bars for a ticker to be playable at all, on the daily chart: 200
# (SMA warm-up) + 35 (lookback window) + 62 (forward runway) + slack. Recent
# IPOs fall short and are skipped rather than shipped as a dead-end pick. The
# weekly chart needs ~465 daily bars; the browser checks that per deal
# (sim-timeframe.js), so a name between the two plays daily only.
MIN_BARS = 320

# Coverage gate, deliberately looser than the site-wide 90%. A deal is a random
# draw from whatever shipped, so 300-odd names train exactly as well as 503 —
# and a cold cache seeds this universe over several nightly runs. Failing the
# deploy (and with it the price sheet, scanner and charts) over a half-seeded
# simulator would be the wrong trade. A total yfinance outage still fails: the
# tally exits non-zero whenever nothing at all built.
MIN_COVERAGE = 0.6


def price_decimals(price: float) -> int:
    """Decimal places a price is kept to — the twin of sim-timeframe.js
    ``priceDecimals``.

    Two (cents) for anything a dollar or more. Below a dollar, enough places to
    keep four significant figures: split-adjusted history takes long-listed
    names down to cents and below (KO closed at $0.04 in 1962, adjusted), and
    at 2dp every candle there would round to the same flat line.
    """
    if not (price > 0) or price >= 1:
        return 2
    return min(8, 3 - math.floor(math.log10(price)))


def bars_ohlcv(df) -> list[list]:
    """A Date-indexed OHLCV frame as [iso, o, h, l, c, v] rows.

    Prices are rounded to cents, or finer under a dollar (``price_decimals``,
    one precision per bar so its four prices agree), and volume to a whole
    number of shares; a missing/zero open falls back to the close so the
    simulator's next-open entry can never divide by zero.
    """
    out = []
    for idx, o, h, l, c, v in zip(
        df.index,
        df["Open"].values,
        df["High"].values,
        df["Low"].values,
        df["Close"].values,
        df["Volume"].values,
    ):
        o, h, l, c = float(o), float(h), float(l), float(c)
        if not (o > 0):
            o = c
        dp = price_decimals(min(l, o, c) if min(l, o, c) > 0 else c)
        out.append(
            [
                idx.strftime("%Y-%m-%d"),
                round(o, dp),
                round(max(h, o, c), dp),
                round(min(l, o, c), dp),
                round(c, dp),
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
    tally = BuildTally(len(universe), min_ok_fraction=MIN_COVERAGE)
    menu = []

    try:
        store = MarketStore()  # read-only; raises if the cache hasn't been built
    except FileNotFoundError as exc:
        print(
            f"\n{exc}\nRun:  python -m src.data.refresh "
            f"--tickers-file config/sp500.csv",
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
