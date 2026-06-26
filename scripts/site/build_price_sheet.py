"""Build the v2 cockpit price-sheet snapshot.

Reads daily bars for each web-surface instrument from the **DuckDB price cache**
(via MarketStore — no yfinance here) and computes the price-sheet metrics
(latest/open/gap, period returns, RSI, price vs 200-day average, 45-day vol and
the vol ratio). Emits ONE compact JSON the grid loads directly — one row per
instrument, no bars shipped.

The cache is the single yfinance reader; this build only consumes it. Seed/
update it first (incremental after the first run, so we don't hammer yfinance):

    python -m src.data.refresh --surface web          # incremental top-up
    python -m src.data.refresh --full --surface web   # first time / full rebuild

Then:
    /usr/local/bin/python3 scripts/site/build_price_sheet.py

Output:
    web/v2/data/price-sheet.json   {built_at, rows:[{ticker,name,theme,...}]}

This is a latest-as-of snapshot. Historical as-of (the date picker) is a future
step and would need bars shipped per instrument; not built yet.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Make `src` importable for the shared registry + price store.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import load_instruments  # noqa: E402
from src.data.store import MarketStore  # noqa: E402

# Shared build helpers (compact-JSON writer, coverage gate).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BuildTally, write_json  # noqa: E402

TRADING_DAYS = 252
PERIODS = {"w1": 5, "m1": 21, "y1": TRADING_DAYS}  # 1-week / 1-month / 1-year lags


def _r(x, n):
    """Round to n places, passing through None/NaN as None (JSON null)."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def compute_rsi(close: pd.Series, period: int = 14):
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    v = rsi.iloc[-1]
    return float(v) if pd.notna(v) else None


def compute_metrics(df: pd.DataFrame) -> dict:
    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)
    n = len(close)
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if n >= 2 else None
    op = float(open_.iloc[-1])

    def pct_from_lag(lag: int):
        if n > lag:
            base = float(close.iloc[-1 - lag])
            return (last / base - 1) * 100 if base else None
        return None

    sma200 = float(close.iloc[-200:].mean()) if n >= 200 else None
    ret = np.log(close / close.shift(1)).dropna()
    vol45 = float(ret.iloc[-45:].std(ddof=0) * np.sqrt(TRADING_DAYS) * 100) if len(ret) >= 45 else None
    vol1y = float(ret.iloc[-TRADING_DAYS:].std(ddof=0) * np.sqrt(TRADING_DAYS) * 100) if len(ret) >= 200 else None

    return {
        "last": _r(last, 3),
        "open": _r(op, 3),
        "gap": _r((op / prev - 1) * 100 if prev else None, 2),
        "prev": _r(prev, 3),
        "d1": _r((last / prev - 1) * 100 if prev else None, 2),
        "w1": _r(pct_from_lag(PERIODS["w1"]), 2),
        "m1": _r(pct_from_lag(PERIODS["m1"]), 2),
        "y1": _r(pct_from_lag(PERIODS["y1"]), 2),
        "rsi": _r(compute_rsi(close), 1),
        "px200": _r(last / sma200 if sma200 else None, 3),
        "vol45": _r(vol45, 2),
        "volr": _r(vol45 / vol1y if (vol45 and vol1y) else None, 3),
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "v2" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    instruments = load_instruments("web")
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tally = BuildTally(len(instruments))
    rows = []

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
        metrics = compute_metrics(df)
        rows.append({"ticker": ticker, "name": inst.name, "theme": theme, **metrics})
        tally.record_ok()
        print(f"last={metrics['last']}  1d={metrics['d1']}%  rsi={metrics['rsi']}")

    payload = {"built_at": built_at, "rows": rows}
    n_bytes = write_json(out_dir / "price-sheet.json", payload)
    print(f"\nWrote price-sheet.json ({len(rows)} rows, {n_bytes / 1024:.0f} kB)")
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
