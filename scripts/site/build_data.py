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

import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

# Make `src` importable so we can read the shared instrument registry.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import load_instruments  # noqa: E402

# Shared build helpers (retry, compact-JSON writer, coverage gate).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BuildTally, fetch_with_retry, write_json  # noqa: E402

# Web instruments come from the unified registry (config/instruments.toml).
# (slug, web_ticker, name, sublabel, group) tuples, web surface only. `group`
# is the dropdown section heading; add/edit instruments in the TOML, not here.
INSTRUMENTS = [
    (i.slug, i.web_ticker, i.name, i.sublabel, i.group)
    for i in load_instruments("web")
]

START = "1990-01-01"


def fetch_bars(ticker: str) -> list[list]:
    raw = yf.download(ticker, start=START, progress=False, auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"no data for {ticker}")
    df = raw[["Open", "Close"]].copy()
    if hasattr(df.columns, "droplevel"):
        try:
            df.columns = df.columns.droplevel(1)
        except (ValueError, IndexError):
            pass
    # Close is the primary series; drop any bar without it.
    df = df[df["Close"].notna()]
    # Open is occasionally missing or zero on thin early bars. Fall back to the
    # close so the entry-at-open path never divides by zero downstream.
    bad_open = df["Open"].isna() | (df["Open"] <= 0)
    df.loc[bad_open, "Open"] = df.loc[bad_open, "Close"]
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
    tally = BuildTally(len(INSTRUMENTS))

    for slug, ticker, name, sublabel, group in INSTRUMENTS:
        label = f"{name} ({ticker})"
        print(f"  fetching {label:<28s} ...", end=" ", flush=True)
        try:
            bars = fetch_with_retry(lambda: fetch_bars(ticker))
        except Exception as exc:  # noqa: BLE001 — skip a bad ticker, keep the rest
            print(f"FAILED ({exc})")
            tally.record_failure(label, exc)
            continue
        payload = {
            "meta": {
                "slug": slug,
                "ticker": ticker,
                "name": name,
                "label": label,
                "sublabel": sublabel,
                "group": group,
                "first_date": bars[0][0],
                "last_date": bars[-1][0],
                "n_bars": len(bars),
                "built_at": built_at,
            },
            "bars": bars,
        }
        path = out_dir / f"{slug}.json"
        n_bytes = write_json(path, payload)
        print(f"{len(bars):>5d} bars  ->  {path.name} ({n_bytes / 1024:.0f} kB)")
        tally.record_ok()
        menu.append({
            "slug": slug,
            "name": name,
            "ticker": ticker,
            "label": label,
            "sublabel": sublabel,
            "group": group,
            "n_bars": len(bars),
            "first_date": bars[0][0],
            "last_date": bars[-1][0],
        })

    menu_payload = {"built_at": built_at, "instruments": menu}
    write_json(out_dir / "instruments.json", menu_payload)
    print(f"\nMenu written -> instruments.json ({len(menu)} entries)")
    print(f"Built at {built_at}")

    sys.exit(tally.report_and_exit_code())


if __name__ == "__main__":
    main()
