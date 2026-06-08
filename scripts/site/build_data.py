"""Build static JSON files for the Macro Beans web app.

Fetches daily OHLC data for a small set of instruments via yfinance and writes
compact JSON files into web/data/ that the browser-side app consumes.

Run locally:
    /usr/local/bin/python3 scripts/site/build_data.py

Outputs:
    web/data/instruments.json       menu of available instruments
    web/data/<slug>.json            per-instrument: {meta, bars}

Bars are written as a list of [iso_date, open, close] triples to keep the
payload small. Dates are trading days only (whatever yfinance returns).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

INSTRUMENTS = [
    # slug,      yahoo,     label,                    sublabel
    ("spx",      "VUSA.L",  "S&P 500 (VUSA.L)",       "US Large Cap"),
    ("ndx",      "EQQQ.L",  "Nasdaq 100 (EQQQ.L)",    "US Tech"),
    ("ftse",     "ISF.L",   "FTSE 100 (ISF.L)",       "UK Large Cap"),
    ("gold",     "SGLN.L",  "Gold (SGLN.L)",          "Precious Metal"),
    ("silver",   "SSLN.L",  "Silver (SSLN.L)",        "Precious Metal"),
    ("brent",    "BRNT.L",  "Brent Oil (BRNT.L)",     "Energy"),
]

START = "1990-01-01"


def fetch_bars(ticker: str) -> list[list]:
    raw = yf.download(ticker, start=START, progress=False, auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"no data for {ticker}")
    df = raw[["Open", "Close"]].dropna()
    if hasattr(df.columns, "droplevel"):
        try:
            df.columns = df.columns.droplevel(1)
        except (ValueError, IndexError):
            pass
    bars = [
        [idx.strftime("%Y-%m-%d"), round(float(o), 4), round(float(c), 4)]
        for idx, o, c in zip(df.index, df["Open"].values, df["Close"].values)
    ]
    return bars


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    menu = []

    for slug, ticker, label, sublabel in INSTRUMENTS:
        print(f"  fetching {label:<22s} ...", end=" ", flush=True)
        bars = fetch_bars(ticker)
        payload = {
            "meta": {
                "slug": slug,
                "ticker": ticker,
                "label": label,
                "sublabel": sublabel,
                "first_date": bars[0][0],
                "last_date": bars[-1][0],
                "n_bars": len(bars),
                "built_at": built_at,
            },
            "bars": bars,
        }
        path = out_dir / f"{slug}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")))
        size_kb = path.stat().st_size / 1024
        print(f"{len(bars):>5d} bars  ->  {path.name} ({size_kb:.0f} kB)")
        menu.append({
            "slug": slug,
            "label": label,
            "sublabel": sublabel,
            "n_bars": len(bars),
            "first_date": bars[0][0],
            "last_date": bars[-1][0],
        })

    menu_payload = {"built_at": built_at, "instruments": menu}
    (out_dir / "instruments.json").write_text(
        json.dumps(menu_payload, separators=(",", ":"))
    )
    print(f"\nMenu written -> instruments.json ({len(menu)} entries)")
    print(f"Built at {built_at}")


if __name__ == "__main__":
    main()
