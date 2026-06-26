"""refresh.py -- the single writer for the DuckDB price cache.

Usage:
    python -m src.data.refresh                 # incremental update, research universe
    python -m src.data.refresh --full          # re-fetch full history
    python -m src.data.refresh --tickers AAPL,MSFT
    python -m src.data.refresh --full --tickers AAPL

The cache is a derived, regenerable artifact. This module is the only place
that opens the DB read-write, and each ticker's upsert runs in its own ACID
transaction -- an interrupted run rolls back cleanly rather than leaving a
half-written file. Read access goes through ``src.data.store.MarketStore``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd

from src.data.paths import DB_PATH
from src.data.registry import surface_tickers

# How many days of overlap to re-fetch on an incremental update, so late
# corrections to recent bars get picked up.
INCREMENTAL_OVERLAP_DAYS = 7

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prices (
    ticker  VARCHAR NOT NULL,
    date    DATE    NOT NULL,
    open    DOUBLE,
    high    DOUBLE,
    low     DOUBLE,
    close   DOUBLE,
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS meta (
    ticker     VARCHAR PRIMARY KEY,
    first_date DATE,
    last_date  DATE,
    n_rows     BIGINT,
    fetched_at TIMESTAMP
);
"""


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create the prices/meta tables if they don't exist."""
    con.execute(_SCHEMA_SQL)


def normalize_ohlcv(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Coerce a yfinance / cached frame into the DuckDB price schema.

    Accepts the typical yfinance ``history()`` frame (tz-aware DatetimeIndex,
    columns Open/High/Low/Close/Volume plus extras) and returns a tidy frame
    with columns: ticker, date, open, high, low, close, volume.
    """
    df = raw.copy()
    # Index -> a plain date column.
    if df.index.name is None:
        df.index.name = "Date"
    df = df.reset_index()
    date_col = df.columns[0]

    cols = {c.lower(): c for c in df.columns}
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"{ticker}: source missing columns {missing}")

    out = pd.DataFrame(
        {
            "ticker": ticker,
            "date": pd.to_datetime(df[date_col], utc=True).dt.tz_localize(None).dt.normalize(),
            "open": pd.to_numeric(df[cols["open"]], errors="coerce"),
            "high": pd.to_numeric(df[cols["high"]], errors="coerce"),
            "low": pd.to_numeric(df[cols["low"]], errors="coerce"),
            "close": pd.to_numeric(df[cols["close"]], errors="coerce"),
            "volume": pd.to_numeric(df[cols["volume"]], errors="coerce"),
        }
    )
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out


def upsert_prices(con: duckdb.DuckDBPyConnection, ticker: str, df: pd.DataFrame) -> int:
    """Upsert one ticker's tidy OHLCV frame and refresh its meta row.

    Runs in a single transaction. Returns the number of rows now held for the
    ticker. Safe to call repeatedly -- existing (ticker, date) rows are
    overwritten, not duplicated.
    """
    tidy = df if "ticker" in df.columns else normalize_ohlcv(df, ticker)
    if tidy.empty:
        return con.execute(
            "SELECT count(*) FROM prices WHERE ticker = ?", [ticker]
        ).fetchone()[0]

    con.execute("BEGIN TRANSACTION")
    try:
        con.register("incoming", tidy)
        con.execute(
            """
            INSERT INTO prices (ticker, date, open, high, low, close, volume)
            SELECT ticker, date, open, high, low, close, volume FROM incoming
            ON CONFLICT (ticker, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume
            """
        )
        con.unregister("incoming")
        con.execute(
            """
            INSERT INTO meta (ticker, first_date, last_date, n_rows, fetched_at)
            SELECT ticker, min(date), max(date), count(*), ?
            FROM prices WHERE ticker = ? GROUP BY ticker
            ON CONFLICT (ticker) DO UPDATE SET
                first_date = excluded.first_date,
                last_date  = excluded.last_date,
                n_rows     = excluded.n_rows,
                fetched_at = excluded.fetched_at
            """,
            [datetime.now(timezone.utc), ticker],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return con.execute(
        "SELECT count(*) FROM prices WHERE ticker = ?", [ticker]
    ).fetchone()[0]


def _fetch_yfinance(ticker: str, start: str | None) -> pd.DataFrame:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    if start is None:
        return tk.history(period="max", auto_adjust=True)
    return tk.history(start=start, auto_adjust=True)


def _last_date(con: duckdb.DuckDBPyConnection, ticker: str):
    row = con.execute(
        "SELECT last_date FROM meta WHERE ticker = ?", [ticker]
    ).fetchone()
    return row[0] if row else None


def refresh(tickers: list[str], full: bool = False, db_path=DB_PATH) -> None:
    """Fetch ``tickers`` from yfinance and upsert into the cache."""
    db_path = str(db_path)
    con = duckdb.connect(db_path, read_only=False)
    try:
        ensure_schema(con)
        n = len(tickers)
        for i, ticker in enumerate(tickers, 1):
            start = None
            if not full:
                last = _last_date(con, ticker)
                if last is not None:
                    start = (last - timedelta(days=INCREMENTAL_OVERLAP_DAYS)).strftime(
                        "%Y-%m-%d"
                    )
            mode = "full" if start is None else f"since {start}"
            print(f"[{i}/{n}] {ticker:<7} ({mode}) ...", end=" ", flush=True)
            try:
                raw = _fetch_yfinance(ticker, start)
            except Exception as exc:  # network / ticker errors shouldn't abort the run
                print(f"FETCH ERROR: {exc}")
                continue
            if raw is None or raw.empty:
                print("no data")
                continue
            tidy = normalize_ohlcv(raw, ticker)
            total = upsert_prices(con, ticker, tidy)
            print(f"+{len(tidy):>5} rows  (total {total})")
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refresh the DuckDB price cache.")
    ap.add_argument("--full", action="store_true", help="re-fetch full history")
    ap.add_argument(
        "--surface",
        choices=["research", "web", "all"],
        default="research",
        help="which registry surface to refresh (ignored if --tickers given)",
    )
    ap.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="comma-separated tickers (default: the --surface universe from registry)",
    )
    args = ap.parse_args(argv)

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    elif args.surface == "all":
        # union of every surface, dedup preserving order
        tickers = list(dict.fromkeys(surface_tickers("research") + surface_tickers("web")))
    else:
        tickers = surface_tickers(args.surface)

    if not tickers:
        print("No tickers to refresh.", file=sys.stderr)
        return 1

    print(f"Refreshing {len(tickers)} tickers into {DB_PATH} "
          f"({'full' if args.full else 'incremental'})")
    refresh(tickers, full=args.full)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
