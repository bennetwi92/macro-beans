"""Fetch daily price history for the Scanner universe.

The Scanner (web/v2) studies the same instruments the public site and cockpit
surface — the union of the ``web`` and ``cockpit`` surfaces in
``config/instruments.toml``. This script pulls full daily open/close history for
every one of them and caches it as a single parquet so the strategy backtest can
replay the Scanner offline.

Why not yfinance / MarketStore? In this environment yfinance's curl_cffi TLS
backend fails behind the egress proxy, and the DuckDB cache is built by that same
yfinance path. So we hit Yahoo's public chart endpoint directly with ``requests``
(which honours the proxy CA bundle) and keep only [date, open, close] — exactly
the fields ``scripts/site/build_charts.py`` emits for the Scanner.

Run:
    /usr/local/bin/python3 scripts/scanner_strategy/fetch_prices.py

Output (gitignored, regenerable):
    data/scanner_strategy/prices.parquet   long frame: ticker, date, open, close, lev
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from src.data.registry import load_instruments_multi  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "scanner_strategy"
OUT_PATH = OUT_DIR / "prices.parquet"

# A browser UA keeps Yahoo from throttling as aggressively; the proxy CA bundle
# is what makes plain `requests` work where yfinance's TLS backend does not.
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
RANGE = "10y"  # plenty of pre-roll for the 200-day SMA + 5y track record


def fetch_one(ticker: str, session: requests.Session) -> pd.DataFrame:
    """One instrument's daily [date, open, close] from Yahoo, with backoff."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": RANGE, "interval": "1d"}
    last_err = None
    for attempt in range(6):
        try:
            r = session.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 200:
                res = r.json()["chart"]["result"]
                if not res:
                    return pd.DataFrame()
                res = res[0]
                ts = res.get("timestamp")
                ind = res.get("indicators", {})
                quote = ind.get("quote", [{}])[0]
                adj = (ind.get("adjclose") or [{}])[0]
                if not ts or "open" not in quote:
                    return pd.DataFrame()
                df = pd.DataFrame({
                    "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize(),
                    "open": quote["open"],
                    "close": quote["close"],
                    "adjclose": adj.get("adjclose", quote["close"]),
                })
                df = df.dropna(subset=["close"])
                # Match the live data layer (yfinance auto_adjust=True): scale OHLC
                # by adjclose/close so splits AND dividends are handled. Leveraged
                # ETPs reverse-split often — without this their prices jump and the
                # backtest sees fake ±90% moves.
                factor = (df["adjclose"] / df["close"]).where(df["close"] > 0, 1.0)
                df["close"] = df["adjclose"]
                df["open"] = df["open"] * factor
                # A missing/zero open falls back to the close so next-open entry
                # never divides by zero downstream (matches build_charts).
                df["open"] = df["open"].where(df["open"] > 0, df["close"])
                df = df.drop(columns=["adjclose"]).dropna(subset=["close"])
                return df.reset_index(drop=True)
            last_err = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(1.5 * (attempt + 1))
    print(f"    !! {ticker}: giving up ({last_err})")
    return pd.DataFrame()


def main() -> None:
    os.environ.setdefault("REQUESTS_CA_BUNDLE", CA_BUNDLE)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    instruments = load_instruments_multi("web", "cockpit")
    print(f"Fetching {len(instruments)} instruments (range={RANGE}) ...")

    session = requests.Session()
    frames = []
    ok = 0
    for i, inst in enumerate(instruments, 1):
        ticker = inst.web_ticker
        lev = inst.category == "Leveraged & Inverse"
        df = fetch_one(ticker, session)
        if df.empty or len(df) < 250:
            print(f"  [{i:>3}/{len(instruments)}] {ticker:<8} SKIP ({len(df)} rows)")
            continue
        df["ticker"] = ticker
        df["name"] = inst.name
        df["theme"] = inst.sublabel or inst.group or inst.category
        df["lev"] = lev
        frames.append(df)
        ok += 1
        print(f"  [{i:>3}/{len(instruments)}] {ticker:<8} {len(df):>5} rows "
              f"({df['date'].iloc[0].date()} .. {df['date'].iloc[-1].date()})"
              f"{'  ⚡' if lev else ''}")
        time.sleep(0.4)  # be polite

    if not frames:
        print("No data fetched.", file=sys.stderr)
        sys.exit(1)

    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(OUT_PATH, index=False)
    print(f"\nWrote {ok}/{len(instruments)} instruments -> {OUT_PATH}")
    print(f"Rows: {len(out):,}  Date span: {out['date'].min().date()} .. {out['date'].max().date()}")


if __name__ == "__main__":
    main()
