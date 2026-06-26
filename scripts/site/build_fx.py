"""Build the daily FX rates the cockpit uses to value non-GBP instruments in GBP.

Writes web/v2/data/fx.json with units-per-GBP rates (e.g. gbpusd = USD per GBP),
so a USD price -> GBP is price / gbpusd. GBp (pence) is a fixed /100 and needs
no rate. Two yfinance calls; cheap to run daily.

Run:
    /usr/local/bin/python3 scripts/site/build_fx.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import fetch_with_retry, write_json  # noqa: E402

PAIRS = {"gbpusd": "GBPUSD=X", "gbpeur": "GBPEUR=X"}


def latest(ticker: str) -> float:
    df = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"no FX data for {ticker}")
    close = df["Close"].dropna()
    val = float(close.iloc[-1].iloc[0] if hasattr(close.iloc[-1], "iloc") else close.iloc[-1])
    return round(val, 6)


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "web" / "v2" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    rates = {}
    for key, tkr in PAIRS.items():
        try:
            rates[key] = fetch_with_retry(lambda t=tkr: latest(t))
        except Exception as exc:  # noqa: BLE001 — a missing rate just leaves it absent
            print(f"  {tkr} FAILED ({exc})")
    payload = {"built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **rates}
    write_json(out_dir / "fx.json", payload)
    print(f"Wrote fx.json: {rates}")


if __name__ == "__main__":
    main()
