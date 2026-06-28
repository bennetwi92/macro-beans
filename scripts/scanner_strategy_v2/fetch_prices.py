"""Fetch OHLC + FX history for the Scanner strategy v2 backtest.

This is the v1 ``scripts/scanner_strategy/fetch_prices.py`` extended in two ways
the v2 methodology needs:

  * **High / low**, not just open / close. v2 checks stops and take-profit
    targets *intraday* against the day's range, so it needs the full daily bar.
  * **FX series** (GBPUSD, GBPEUR). The account is a GBP ISA, but ~37% of the
    universe (and the IWDA benchmark itself) is quoted in USD/EUR. v2 translates
    every fill to GBP and charges Trading 212's FX conversion fee, so it needs
    the daily cross rates over the same span.

Prices are split/dividend-adjusted exactly as the live data layer is
(auto_adjust=True): OHLC scaled by adjclose/close, then a reverse-split repair
for the leveraged ETPs whose Yahoo history bakes in un-flagged reverse splits.

Run:
    /usr/local/bin/python3 scripts/scanner_strategy_v2/fetch_prices.py

Outputs (gitignored, regenerable):
    data/scanner_strategy_v2/prices_ohlc.parquet
        long frame: ticker, date, open, high, low, close, lev, name, theme, currency
    data/scanner_strategy_v2/fx.parquet
        date, gbpusd, gbpeur   (units of USD/EUR per 1 GBP)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from src.data.registry import load_instruments_multi  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "scanner_strategy_v2"
PRICES_PATH = OUT_DIR / "prices_ohlc.parquet"
FX_PATH = OUT_DIR / "fx.parquet"
CCY_PATH = REPO_ROOT / "config" / "instrument_currency.json"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"
RANGE = "10y"


def fetch_one(ticker: str, session: requests.Session, fx: bool = False) -> pd.DataFrame:
    """One series' daily OHLC from Yahoo, split/dividend-adjusted, with backoff.

    For FX crosses Yahoo reports no adjclose; we keep the raw quote.
    """
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
                if not ts or "close" not in quote:
                    return pd.DataFrame()
                df = pd.DataFrame({
                    "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize(),
                    "open": quote.get("open"),
                    "high": quote.get("high"),
                    "low": quote.get("low"),
                    "close": quote["close"],
                    "adjclose": adj.get("adjclose", quote["close"]),
                })
                df = df.dropna(subset=["close"])
                if fx:
                    return df.drop(columns=["adjclose"]).reset_index(drop=True)
                # auto_adjust: scale the whole bar by adjclose/close (splits+divs)
                factor = (df["adjclose"] / df["close"]).where(df["close"] > 0, 1.0)
                for col in ("open", "high", "low"):
                    df[col] = df[col] * factor
                df["close"] = df["adjclose"]
                # missing open/high/low fall back to close so nothing divides by 0
                for col in ("open", "high", "low"):
                    df[col] = df[col].where(df[col] > 0, df["close"])
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
    currencies = json.loads(CCY_PATH.read_text()) if CCY_PATH.exists() else {}

    instruments = load_instruments_multi("web", "cockpit")
    print(f"Fetching {len(instruments)} instruments + 2 FX series (range={RANGE}) ...")

    session = requests.Session()

    # ---- FX first (the account currency machinery depends on it) ----
    fx_frames = {}
    for cross, col in [("GBPUSD=X", "gbpusd"), ("GBPEUR=X", "gbpeur")]:
        f = fetch_one(cross, session, fx=True)
        if f.empty:
            print(f"  !! FX {cross} empty — aborting", file=sys.stderr)
            sys.exit(1)
        fx_frames[col] = f.set_index("date")["close"].rename(col)
        print(f"  FX {cross}: {len(f)} rows ({f['date'].iloc[0].date()} .. {f['date'].iloc[-1].date()})")
    fx = pd.concat(fx_frames.values(), axis=1).sort_index().ffill()
    fx.reset_index().to_parquet(FX_PATH, index=False)
    print(f"  Wrote {FX_PATH}")

    # ---- instruments ----
    frames = []
    ok = 0
    for i, inst in enumerate(instruments, 1):
        ticker = inst.web_ticker
        if not ticker:
            continue
        lev = inst.category == "Leveraged & Inverse"
        df = fetch_one(ticker, session)
        if df.empty or len(df) < 250:
            print(f"  [{i:>3}/{len(instruments)}] {ticker:<8} SKIP ({len(df)} rows)")
            continue
        df["ticker"] = ticker
        df["name"] = inst.name
        df["theme"] = inst.sublabel or inst.group or inst.category
        df["lev"] = lev
        df["currency"] = currencies.get(ticker) or ("GBp" if ticker.endswith(".L") else "GBP")
        frames.append(df)
        ok += 1
        print(f"  [{i:>3}/{len(instruments)}] {ticker:<8} {len(df):>5} rows "
              f"({df['date'].iloc[0].date()} .. {df['date'].iloc[-1].date()}) "
              f"{df['currency'].iloc[0]:<4}{'  ⚡' if lev else ''}")
        time.sleep(0.4)

    if not frames:
        print("No data fetched.", file=sys.stderr)
        sys.exit(1)

    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(PRICES_PATH, index=False)
    print(f"\nWrote {ok}/{len(instruments)} instruments -> {PRICES_PATH}")
    print(f"Rows: {len(out):,}  Span: {out['date'].min().date()} .. {out['date'].max().date()}")


if __name__ == "__main__":
    main()
