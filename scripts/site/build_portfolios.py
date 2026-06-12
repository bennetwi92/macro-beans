"""Build pair-portfolio equity-curve JSON for the Macro Beans web app.

For each portfolio:
  * fetch the long-leg and short-leg underlying daily closes from yfinance
  * compute a rolling 60-day beta of long vs short (with 1-day lag, no
    look-ahead), optionally clipped to a [min, max] range
  * compute the beta-hedged 1x underlying daily return:
        r_under = r_long - beta * r_short
  * compute the LETF-wrapped daily return given the leverage factors of
    the two LETF legs (long leverage L_a, short leverage L_b):
        w_long  = L_b / (L_a * beta + L_b)
        w_short = L_a * beta / (L_a * beta + L_b)
        r_letf  = L_a * w_long * r_long  -  L_b * w_short * r_short
  * cumulate both to an equity curve starting at 1.0

Outputs:
  web/data/portfolios.json                menu (list of all portfolios)
  web/data/portfolios/<slug>.json         per-portfolio {meta, bars}
       bars: [[iso_date, equity_under, equity_letf], ...]

Run locally:
  /usr/local/bin/python3 scripts/site/build_portfolios.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Make `src` importable so we can read the shared portfolio registry.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.data.registry import load_portfolios  # noqa: E402

LOOKBACK = 60
START = "2000-01-01"


def _portfolio_to_dict(p) -> dict:
    """Registry Portfolio -> the dict shape this build script expects."""
    return {
        "slug": p.slug,
        "name": p.name,
        "blurb": p.blurb,
        "long": asdict(p.long),
        "short": asdict(p.short),
        "beta_clip": list(p.beta_clip) if p.beta_clip else None,
    }


# Pair portfolios come from the unified registry (config/portfolios.toml).
PORTFOLIOS = [_portfolio_to_dict(p) for p in load_portfolios()]


def fetch_closes(ticker: str) -> pd.Series:
    raw = yf.download(ticker, start=START, progress=False, auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"no data for {ticker}")
    close = raw["Close"].copy()
    if hasattr(close, "columns"):
        try:
            close = close.iloc[:, 0]
        except Exception:
            pass
    return close.dropna()


def build_portfolio(p: dict) -> tuple[list[list], dict]:
    """Returns (bars, summary_meta)."""
    long_close  = fetch_closes(p["long"]["underlying"])
    short_close = fetch_closes(p["short"]["underlying"])

    # Align on common dates
    closes = pd.DataFrame({"long": long_close, "short": short_close}).dropna()
    rets = closes.pct_change().dropna()

    cov = rets["long"].rolling(LOOKBACK).cov(rets["short"])
    var = rets["short"].rolling(LOOKBACK).var()
    beta = (cov / var).shift(1)
    if p["beta_clip"] is not None:
        lo, hi = p["beta_clip"]
        beta = beta.clip(lower=lo, upper=hi)

    # 1x underlying beta-hedged return
    r_under = rets["long"] - beta * rets["short"]

    # LETF wrapper
    L_a = p["long"]["lev"]
    L_b = p["short"]["lev"]
    denom  = L_a * beta + L_b
    w_long  = L_b / denom
    w_short = (L_a * beta) / denom
    r_letf = L_a * w_long * rets["long"] - L_b * w_short * rets["short"]

    df = pd.DataFrame({"r_under": r_under, "r_letf": r_letf}).dropna()
    eq_under = (1.0 + df["r_under"]).cumprod()
    eq_letf  = (1.0 + df["r_letf"]).cumprod()

    bars = [
        [idx.strftime("%Y-%m-%d"), round(float(u), 6), round(float(l), 6)]
        for idx, u, l in zip(df.index, eq_under.values, eq_letf.values)
    ]
    meta = {
        "slug":  p["slug"],
        "name":  p["name"],
        "blurb": p["blurb"],
        "long":  p["long"],
        "short": p["short"],
        "beta_clip":  p["beta_clip"],
        "lookback":   LOOKBACK,
        "first_date": bars[0][0],
        "last_date":  bars[-1][0],
        "n_bars":     len(bars),
    }
    return bars, meta


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "web" / "data" / "portfolios"
    out_dir.mkdir(parents=True, exist_ok=True)

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    menu = []

    for p in PORTFOLIOS:
        print(f"  building {p['name']:<28s} ...", end=" ", flush=True)
        bars, meta = build_portfolio(p)
        meta["built_at"] = built_at
        payload = {"meta": meta, "bars": bars}
        path = out_dir / f"{p['slug']}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")))
        size_kb = path.stat().st_size / 1024
        print(f"{len(bars):>5d} bars  ->  {path.name} ({size_kb:.0f} kB)")
        menu.append({
            "slug":  p["slug"],
            "name":  p["name"],
            "blurb": p["blurb"],
            "long":  p["long"],
            "short": p["short"],
            "first_date": meta["first_date"],
            "last_date":  meta["last_date"],
            "n_bars":     meta["n_bars"],
        })

    menu_path = repo_root / "web" / "data" / "portfolios.json"
    menu_path.write_text(json.dumps(
        {"built_at": built_at, "portfolios": menu},
        separators=(",", ":")))
    print(f"\nMenu written -> {menu_path.name} ({len(menu)} entries)")
    print(f"Built at {built_at}")


if __name__ == "__main__":
    main()
