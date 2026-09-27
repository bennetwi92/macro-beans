"""fundamentals.py -- weekly fundamentals snapshots + the earnings calendar.

Usage:
    python -m src.data.fundamentals                    # snapshot the S&P 500
    python -m src.data.fundamentals --tickers AAPL,MSFT
    python -m src.data.fundamentals --no-earnings      # skip the calendar refresh
    python -m src.data.fundamentals --earnings-only    # refresh only the calendar

Why this is not a DuckDB table like prices
------------------------------------------
yfinance's ``Ticker.info`` is a snapshot with **no history**: it says what the
P/E is today and nothing about what it was last year. Prices can be re-fetched
from scratch at any time, which is why the price cache is a disposable file. A
fundamentals history cannot: the only way to have one is to have written it
down every week, and a week that was not written is gone for good.

So the snapshots are plain CSVs under ``data/fundamentals/`` that are
**committed to the repo** (by the weekly ``fundamentals.yml`` workflow), not
rows in the gitignored price cache. CI's rolling DuckDB cache can be evicted
without warning, and losing the fundamentals history with it would lose the
one thing this module exists to accumulate.

Outputs
-------
    data/fundamentals/snapshots/<YYYY-MM-DD>.csv   one row per ticker, dated
    data/fundamentals/earnings.csv                 ticker,date,eps_est,eps_act,surprise_pct

Earnings dates, unlike ``.info``, DO have history: ``get_earnings_dates``
returns past reports -- with the consensus estimate, the reported EPS and the
surprise -- as well as the next scheduled one (estimate only). The calendar is
merged on every run, so it only ever grows, and a scheduled row is filled in
once the report lands. It is the scorecard's news block: the earnings surprise
is the one piece of news that is dated, machine-readable and has a decade of
history to test against (post-earnings-announcement drift).

A report is dated by its calendar day in exchange time. Most land after the
close (16:00 ET), so a consumer must treat a report as known only on a date
STRICTLY after it -- the scorecard does.

A snapshot is dated by the day it was taken, and must only ever be read as of
that day or later -- ``latest_snapshot(as_of)`` enforces this. Scoring the
present with today's snapshot is honest; scoring 2019 with it is look-ahead.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from src.data.paths import DATA_DIR
from src.data.registry import SP500_CSV, load_ticker_csv

FUND_DIR = DATA_DIR / "fundamentals"
SNAP_DIR = FUND_DIR / "snapshots"
EARNINGS_CSV = FUND_DIR / "earnings.csv"

# The .info fields kept, in column order. Everything the scorecard's quality
# and value grades read, plus the identity fields the cards display. Kept
# deliberately narrow: a field nobody grades is a field nobody checks.
FIELDS = [
    "sector",
    "industry",
    "marketCap",
    "totalRevenue",
    "revenueGrowth",
    "earningsGrowth",
    "grossMargins",
    "operatingMargins",
    "profitMargins",
    "returnOnEquity",
    "returnOnAssets",
    "debtToEquity",
    "currentRatio",
    "freeCashflow",
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "enterpriseToEbitda",
    "beta",
]

# How many past earnings reports to ask for. Forty quarters is ten years,
# comfortably more than the backtest's use of the calendar needs.
EARNINGS_LIMIT = 40

# yfinance throttles bursts. A short pause per name and a few retries turn a
# rate-limit into a slow run instead of a hole in the snapshot.
PAUSE_S = 0.25
RETRIES = 3


def _retry(fn, what: str):
    delay = 2.0
    for attempt in range(RETRIES):
        try:
            return fn()
        except Exception as exc:  # yfinance raises a zoo of types
            if attempt == RETRIES - 1:
                print(f"    {what}: {type(exc).__name__}: {exc}", file=sys.stderr)
                return None
            time.sleep(delay)
            delay *= 2
    return None


def fetch_info(ticker: str) -> dict | None:
    import yfinance as yf

    info = _retry(lambda: yf.Ticker(ticker).info, f"{ticker} info")
    if not info or not isinstance(info, dict):
        return None
    row = {k: info.get(k) for k in FIELDS}
    # An .info payload with no market cap is a delisted / renamed shell.
    return row if row.get("marketCap") else None


EARN_COLS = ["eps_est", "eps_act", "surprise_pct"]


def fetch_earnings(ticker: str) -> dict[str, dict]:
    """``{date: {eps_est, eps_act, surprise_pct}}``; empty strings for unknowns."""
    import yfinance as yf

    df = _retry(
        lambda: yf.Ticker(ticker).get_earnings_dates(limit=EARNINGS_LIMIT),
        f"{ticker} earnings",
    )
    if df is None or len(df) == 0:
        return {}
    out: dict[str, dict] = {}
    # The index is a tz-aware timestamp in exchange time; the calendar day is
    # what matters (a 16:00 report belongs to that session's close).
    for ts, row in df.iterrows():
        out[ts.strftime("%Y-%m-%d")] = {
            "eps_est": _clean(row.get("EPS Estimate")),
            "eps_act": _clean(row.get("Reported EPS")),
            "surprise_pct": _clean(row.get("Surprise(%)")),
        }
    return out


def _clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN
        return ""
    return v


def write_snapshot(rows: dict[str, dict], day: str) -> Path:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{day}.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", *FIELDS])
        for t in sorted(rows):
            w.writerow([t, *(_clean(rows[t].get(k)) for k in FIELDS)])
    return path


def read_earnings() -> dict[str, dict[str, dict]]:
    """``{ticker: {date: {eps_est, eps_act, surprise_pct}}}`` from the CSV.

    Tolerates the original dates-only layout, whose rows come back with empty
    values and are filled in by the next fetch.
    """
    out: dict[str, dict[str, dict]] = {}
    if not EARNINGS_CSV.exists():
        return out
    with EARNINGS_CSV.open() as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["ticker"], {})[r["date"]] = {k: r.get(k, "") or "" for k in EARN_COLS}
    return out


def merge_earnings(cal: dict[str, dict[str, dict]], ticker: str, fresh: dict[str, dict]) -> None:
    """Upsert, never erase: a known value is only replaced by another known one."""
    have = cal.setdefault(ticker, {})
    for d, vals in fresh.items():
        row = have.setdefault(d, {k: "" for k in EARN_COLS})
        for k in EARN_COLS:
            if vals.get(k, "") != "":
                row[k] = vals[k]


def write_earnings(cal: dict[str, dict[str, dict]]) -> None:
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    with EARNINGS_CSV.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "date", *EARN_COLS])
        for t in sorted(cal):
            for d in sorted(cal[t]):
                w.writerow([t, d, *(cal[t][d].get(k, "") for k in EARN_COLS)])


def snapshot_dates() -> list[str]:
    return sorted(p.stem for p in SNAP_DIR.glob("*.csv"))


def latest_snapshot(as_of: str | None = None) -> tuple[str, dict[str, dict]] | None:
    """The newest snapshot dated ON OR BEFORE ``as_of`` (default: newest).

    The ``<=`` is the no-look-ahead rule: a snapshot taken on 2026-09-27 says
    nothing about any earlier week.
    """
    days = [d for d in snapshot_dates() if as_of is None or d <= as_of]
    if not days:
        return None
    day = days[-1]
    rows: dict[str, dict] = {}
    with (SNAP_DIR / f"{day}.csv").open() as fh:
        for r in csv.DictReader(fh):
            rows[r.pop("ticker")] = r
    return day, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tickers", help="comma-separated tickers (default: config/sp500.csv)")
    ap.add_argument("--no-earnings", action="store_true", help="skip the earnings calendar")
    ap.add_argument("--earnings-only", action="store_true", help="refresh only the earnings calendar")
    args = ap.parse_args(argv)

    tickers = (
        [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        if args.tickers
        else [r.ticker for r in load_ticker_csv(SP500_CSV)]
    )
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cal = read_earnings()
    rows: dict[str, dict] = {}
    n_cal = 0
    for k, t in enumerate(tickers, 1):
        info = None if args.earnings_only else fetch_info(t)
        if info:
            rows[t] = info
        n_new = 0
        if not args.no_earnings:
            fresh = fetch_earnings(t)
            if fresh:
                merge_earnings(cal, t, fresh)
                n_cal += 1
                n_new = len(fresh)
        print(f"[{k}/{len(tickers)}] {t:<6s} info={'ok' if info else '--'} earnings={n_new}")
        time.sleep(PAUSE_S)

    if args.earnings_only:
        if n_cal < 0.8 * len(tickers):
            print(f"Only {n_cal}/{len(tickers)} calendars fetched; not writing.", file=sys.stderr)
            return 1
        write_earnings(cal)
        print(f"Earnings calendar refreshed for {n_cal} names")
        return 0

    # Coverage gate: a snapshot that is mostly holes is worse than none,
    # because the sector percentiles it feeds would be ranked over a fragment.
    if len(rows) < 0.8 * len(tickers):
        print(f"Only {len(rows)}/{len(tickers)} names fetched; not writing a snapshot.", file=sys.stderr)
        return 1
    path = write_snapshot(rows, day)
    if not args.no_earnings:
        write_earnings(cal)
    print(f"Wrote {path.relative_to(DATA_DIR.parent)} ({len(rows)} names); "
          f"earnings calendar refreshed for {n_cal} names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
