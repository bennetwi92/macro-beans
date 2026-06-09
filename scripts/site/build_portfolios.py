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
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

LOOKBACK = 60
START = "2000-01-01"

PORTFOLIOS = [
    {
        "slug":  "silver-gold",
        "name":  "Silver / Gold",
        "blurb": "Long silver, short gold. Silver is the higher-beta industrial precious metal; gold is the safe-haven. Expresses a pro-cyclical, reflationary view — gains when growth expectations rise faster than risk-off demand.",
        "long":  {"underlying": "SI=F", "letf": "3SIL.L", "label": "Silver",   "lev": 3},
        "short": {"underlying": "GC=F", "letf": "3GOS.L", "label": "Gold",     "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "gold-treasuries",
        "name":  "Gold / 10Y Treasuries",
        "blurb": "Long gold, short 10-year US Treasuries. Captures real-yield repricing and inflation surprises — gold rallies when real yields fall, but the bond leg drags when nominal yields move. Beta is clipped to [0.1, 2.0] because gold-vs-bond correlation flips between regimes.",
        "long":  {"underlying": "GC=F", "letf": "3GOL.L", "label": "Gold",     "lev": 3},
        "short": {"underlying": "ZN=F", "letf": "3TYS.L", "label": "10Y UST",  "lev": 3},
        "beta_clip": [0.1, 2.0],
    },
    {
        "slug":  "ftse250-ftse100",
        "name":  "FTSE 250 / FTSE 100",
        "blurb": "Long UK mid-caps (domestic-revenue heavy), short UK large-caps (international-revenue heavy, GBP-sensitive). Expresses a positive view on UK domestic activity / sterling. Note the asymmetric leverage: 2x long mid via 2MCL.L, 3x short large via 3UKS.L.",
        "long":  {"underlying": "^FTMC", "letf": "2MCL.L", "label": "FTSE 250", "lev": 2},
        "short": {"underlying": "^FTSE", "letf": "3UKS.L", "label": "FTSE 100", "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "ndx-spx",
        "name":  "Nasdaq 100 / S&P 500",
        "blurb": "Long Nasdaq 100, short S&P 500. Both 3x. Expresses a positive view on the tech-vs-broad-market dispersion. Will outperform when mega-cap tech leads, underperform when leadership broadens to value/cyclicals.",
        "long":  {"underlying": "^NDX",  "letf": "QQQ3.L", "label": "Nasdaq 100", "lev": 3},
        "short": {"underlying": "^GSPC", "letf": "3USS.L", "label": "S&P 500",    "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "copper-gold",
        "name":  "Copper / Gold",
        "blurb": "Long copper, short gold. Both 3x. Copper — 'Dr Copper' — climbs when global industry is busy; gold climbs when investors are scared. The copper-to-gold ratio is a classic growth-vs-fear gauge: this pair gains when the market prices in faster growth and fades when fear takes over. Beta is clipped to [0.05, 2.0] because the copper-vs-gold correlation drifts between regimes.",
        "long":  {"underlying": "HG=F", "letf": "3HCL.L", "label": "Copper", "lev": 3},
        "short": {"underlying": "GC=F", "letf": "3GOS.L", "label": "Gold",   "lev": 3},
        "beta_clip": [0.05, 2.0],
    },
    {
        "slug":  "crude-gold",
        "name":  "Crude Oil / Gold",
        "blurb": "Long WTI crude, short gold. Both 3x. Both are real assets that tend to rise with inflation, but crude is driven by demand and the economic cycle while gold is the haven of choice when growth stalls. Expresses a commodity-reflation view — gains when energy demand and inflation run hot relative to safe-haven flows. Beta is clipped to [0, 2.0] because the crude-gold link is loose and shifts with the cycle.",
        "long":  {"underlying": "CL=F", "letf": "3LOI.L", "label": "WTI Crude", "lev": 3},
        "short": {"underlying": "GC=F", "letf": "3GOS.L", "label": "Gold",      "lev": 3},
        "beta_clip": [0.0, 2.0],
    },
    {
        "slug":  "eurostoxx-spx",
        "name":  "EURO STOXX 50 / S&P 500",
        "blurb": "Long the EURO STOXX 50, short the S&P 500. Both 3x. A bet that Europe's biggest companies outperform America's — the reverse of the 'US exceptionalism' trade that has dominated the last decade. Gains when European equities close the gap; bleeds when US mega-caps keep leading.",
        "long":  {"underlying": "^STOXX50E", "letf": "3EUL.L", "label": "EURO STOXX 50", "lev": 3},
        "short": {"underlying": "^GSPC",     "letf": "3USS.L", "label": "S&P 500",       "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "dax-ftse100",
        "name":  "DAX 40 / FTSE 100",
        "blurb": "Long Germany's DAX 40, short the UK's FTSE 100. Both 3x. The DAX is packed with exporters and industrials; the FTSE 100 leans on energy, miners and banks that earn most of their revenue abroad. Expresses a view that Eurozone industry outperforms UK large-caps — sensitive to the euro, German manufacturing and global trade.",
        "long":  {"underlying": "^GDAXI", "letf": "3DEL.L", "label": "DAX 40",   "lev": 3},
        "short": {"underlying": "^FTSE",  "letf": "3UKS.L", "label": "FTSE 100", "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "brent-wti",
        "name":  "Brent / WTI Crude",
        "blurb": "Long Brent crude, short WTI. Both 3x. Brent is the global oil benchmark; WTI is the US landlocked grade. The gap between them — the Brent-WTI spread — widens when US supply is plentiful or world supply is tight, and narrows when the reverse holds. A focused bet on that spread rather than the direction of oil itself.",
        "long":  {"underlying": "BZ=F", "letf": "3BLR.L", "label": "Brent Crude", "lev": 3},
        "short": {"underlying": "CL=F", "letf": "3OIS.L", "label": "WTI Crude",   "lev": 3},
        "beta_clip": None,
    },
]


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

    # Winsorize raw daily returns. Guards against bad ticks and futures
    # artifacts (e.g. the 2020-04-20 WTI front-month print of -$37, a
    # ~-306% "daily return") that a real daily-rebalanced LETF wrapper
    # could never realize — and which would otherwise flip the cumulative
    # equity curve through zero or inflate it spuriously. The band is wide
    # enough never to touch legitimate index/metal moves.
    rets = rets.clip(lower=-0.5, upper=1.0)

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
