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

# --- Trading 212 CFD cost model (for kind == "cfd" portfolios) ----------------
#
# T212 CFD accounts charge: zero commission, a dynamic spread (a per-trade cost,
# not modelled here because it depends on how often you trade the spread), and a
# nightly overnight-interest charge. There is NO currency-conversion fee for our
# pairs because both legs are London-listed GBP shares held on a GBP account.
#
# Overnight interest follows T212's published structure: a benchmark rate plus a
# fixed per-instrument markup. For a LONG you pay (benchmark + markup); for a
# SHORT you receive (benchmark - markup). Both are divided by 365 and applied per
# calendar night (so a Friday->Monday roll is charged for 3 nights — this is how
# T212's weekend "triple charge" shows up). Live per-instrument rates vary in the
# app; we use a transparent approximation:
#   * benchmark  = BoE Bank Rate, a close proxy for the GBP SONIA financing base
#   * markup     = MARKUP_ANNUAL, T212's static per-share markup (~3%/yr, i.e.
#                  ~0.0082%/day; corroborated by third-party fee breakdowns)
# On a balanced (beta ~= 1) pair the benchmark cancels between the long and short
# legs and the running cost is roughly twice the markup on gross exposure.
MARKUP_ANNUAL = 0.03

# BoE Bank Rate step history (effective date, rate). Forward-filled; SONIA proxy.
BANK_RATE_STEPS = [
    ("2000-01-01", 0.0575), ("2000-02-10", 0.0600), ("2001-02-08", 0.0575),
    ("2001-04-05", 0.0550), ("2001-05-10", 0.0525), ("2001-08-02", 0.0500),
    ("2001-09-18", 0.0475), ("2001-10-04", 0.0450), ("2001-11-08", 0.0400),
    ("2003-02-06", 0.0375), ("2003-07-10", 0.0350), ("2003-11-06", 0.0375),
    ("2004-02-05", 0.0400), ("2004-05-06", 0.0425), ("2004-06-10", 0.0450),
    ("2004-08-05", 0.0475), ("2005-08-04", 0.0450), ("2006-08-03", 0.0475),
    ("2006-11-09", 0.0500), ("2007-01-11", 0.0525), ("2007-05-10", 0.0550),
    ("2007-07-05", 0.0575), ("2007-12-06", 0.0550), ("2008-02-07", 0.0525),
    ("2008-04-10", 0.0500), ("2008-10-08", 0.0450), ("2008-11-06", 0.0300),
    ("2008-12-04", 0.0200), ("2009-01-08", 0.0150), ("2009-02-05", 0.0100),
    ("2009-03-05", 0.0050), ("2016-08-04", 0.0025), ("2017-11-02", 0.0050),
    ("2018-08-02", 0.0075), ("2020-03-11", 0.0025), ("2020-03-19", 0.0010),
    ("2021-12-16", 0.0025), ("2022-02-03", 0.0050), ("2022-03-17", 0.0075),
    ("2022-05-05", 0.0100), ("2022-06-16", 0.0125), ("2022-08-04", 0.0175),
    ("2022-09-22", 0.0225), ("2022-11-03", 0.0300), ("2022-12-15", 0.0350),
    ("2023-02-02", 0.0400), ("2023-03-23", 0.0425), ("2023-05-11", 0.0450),
    ("2023-06-22", 0.0500), ("2023-08-03", 0.0525), ("2024-08-01", 0.0500),
    ("2024-11-07", 0.0475), ("2025-02-06", 0.0450), ("2025-05-08", 0.0425),
    ("2025-08-07", 0.0400),
]

PORTFOLIOS = [
    {
        "slug":  "silver-gold",
        "name":  "Silver / Gold",
        "kind":  "letf",
        "blurb": "Long silver, short gold. Silver is the higher-beta industrial precious metal; gold is the safe-haven. Expresses a pro-cyclical, reflationary view — gains when growth expectations rise faster than risk-off demand.",
        "long":  {"underlying": "SI=F", "letf": "3SIL.L", "label": "Silver",   "lev": 3},
        "short": {"underlying": "GC=F", "letf": "3GOS.L", "label": "Gold",     "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "gold-treasuries",
        "name":  "Gold / 10Y Treasuries",
        "kind":  "letf",
        "blurb": "Long gold, short 10-year US Treasuries. Captures real-yield repricing and inflation surprises — gold rallies when real yields fall, but the bond leg drags when nominal yields move. Beta is clipped to [0.1, 2.0] because gold-vs-bond correlation flips between regimes.",
        "long":  {"underlying": "GC=F", "letf": "3GOL.L", "label": "Gold",     "lev": 3},
        "short": {"underlying": "ZN=F", "letf": "3TYS.L", "label": "10Y UST",  "lev": 3},
        "beta_clip": [0.1, 2.0],
    },
    {
        "slug":  "ftse250-ftse100",
        "name":  "FTSE 250 / FTSE 100",
        "kind":  "letf",
        "blurb": "Long UK mid-caps (domestic-revenue heavy), short UK large-caps (international-revenue heavy, GBP-sensitive). Expresses a positive view on UK domestic activity / sterling. Note the asymmetric leverage: 2x long mid via 2MCL.L, 3x short large via 3UKS.L.",
        "long":  {"underlying": "^FTMC", "letf": "2MCL.L", "label": "FTSE 250", "lev": 2},
        "short": {"underlying": "^FTSE", "letf": "3UKS.L", "label": "FTSE 100", "lev": 3},
        "beta_clip": None,
    },
    {
        "slug":  "ndx-spx",
        "name":  "Nasdaq 100 / S&P 500",
        "kind":  "letf",
        "blurb": "Long Nasdaq 100, short S&P 500. Both 3x. Expresses a positive view on the tech-vs-broad-market dispersion. Will outperform when mega-cap tech leads, underperform when leadership broadens to value/cyclicals.",
        "long":  {"underlying": "^NDX",  "letf": "QQQ3.L", "label": "Nasdaq 100", "lev": 3},
        "short": {"underlying": "^GSPC", "letf": "3USS.L", "label": "S&P 500",    "lev": 3},
        "beta_clip": None,
    },

    # --- LSE single-share pairs, traded as CFDs on Trading 212 ----------------
    # Same-sector UK names that move together, so the hedge strips out the sector
    # and leaves the gap between the two companies (a classic mean-reversion pair).
    # All GBP-listed, so no FX fee — the only running cost is overnight financing.
    {
        "slug":  "shell-bp",
        "name":  "Shell / BP",
        "kind":  "cfd",
        "blurb": "Long Shell, short BP — the two London-listed oil supermajors. Both rise and fall with the crude oil price, so hedging one against the other strips out the oil move and leaves the gap between the companies: relative strategy, production and trading results. A textbook mean-reversion pair. Both trade in pence on the LSE, so on a GBP Trading 212 account there is no currency-conversion fee — the only running cost is overnight CFD financing.",
        "long":  {"underlying": "SHEL.L", "ticker": "SHEL", "label": "Shell"},
        "short": {"underlying": "BP.L",   "ticker": "BP",   "label": "BP"},
        "beta_clip": [0.2, 3.0],
    },
    {
        "slug":  "lloyds-natwest",
        "name":  "Lloyds / NatWest",
        "kind":  "cfd",
        "blurb": "Long Lloyds, short NatWest — two UK-focused high-street banks. Both live or die on UK interest rates, mortgages and the domestic economy, so the hedge removes the sector move and isolates relative margins, capital returns and bank-specific news. Tight, liquid and GBP-denominated — no FX fee, just overnight financing.",
        "long":  {"underlying": "LLOY.L", "ticker": "LLOY", "label": "Lloyds"},
        "short": {"underlying": "NWG.L",  "ticker": "NWG",  "label": "NatWest"},
        "beta_clip": [0.2, 3.0],
    },
    {
        "slug":  "tesco-sainsburys",
        "name":  "Tesco / Sainsbury's",
        "kind":  "cfd",
        "blurb": "Long Tesco, short Sainsbury's — Britain's two largest listed supermarkets. Both track UK food inflation and the grocery market-share fight; hedging one against the other leaves the gap between the market leader and its smaller, thinner-margin rival. GBP shares, so no currency fee — only overnight financing.",
        "long":  {"underlying": "TSCO.L", "ticker": "TSCO", "label": "Tesco"},
        "short": {"underlying": "SBRY.L", "ticker": "SBRY", "label": "Sainsbury's"},
        "beta_clip": [0.2, 3.0],
    },
    {
        "slug":  "bat-imperial",
        "name":  "BAT / Imperial Brands",
        "kind":  "cfd",
        "blurb": "Long British American Tobacco, short Imperial Brands — the two UK-listed tobacco majors. Both are defensive, high-yield and move on regulation and the shift to next-generation products, so the hedge isolates the gap between them. Note both earn heavily in dollars, which can drive the spread. GBP-listed — no FX fee, only overnight financing.",
        "long":  {"underlying": "BATS.L", "ticker": "BATS", "label": "BAT"},
        "short": {"underlying": "IMB.L",  "ticker": "IMB",  "label": "Imperial"},
        "beta_clip": [0.2, 3.0],
    },
    {
        "slug":  "glencore-rio",
        "name":  "Glencore / Rio Tinto",
        "kind":  "cfd",
        "blurb": "Long Glencore, short Rio Tinto — two London-listed diversified miners geared to global commodity demand. Rio leans on iron ore; Glencore on copper, coal and commodity trading. Hedging the pair removes the broad mining move and leaves their differing commodity mix. History starts in 2011 when Glencore floated. GBP shares — no FX fee, only overnight financing.",
        "long":  {"underlying": "GLEN.L", "ticker": "GLEN", "label": "Glencore"},
        "short": {"underlying": "RIO.L",  "ticker": "RIO",  "label": "Rio Tinto"},
        "beta_clip": [0.2, 3.0],
    },
]


def bank_rate_series(index: pd.DatetimeIndex) -> pd.Series:
    """Forward-filled BoE Bank Rate (SONIA proxy) aligned to `index`."""
    steps = pd.Series(
        {pd.Timestamp(d): r for d, r in BANK_RATE_STEPS}
    ).sort_index()
    return steps.reindex(steps.index.union(index)).ffill().reindex(index)


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
    """Returns (bars, summary_meta).

    Column 1 of every bar is the gross beta-hedged spread (1x, no costs).
    Column 2 depends on the portfolio kind:
      * "letf" — the LSE leveraged-ETF wrapper return
      * "cfd"  — the same spread net of Trading 212 overnight financing
    """
    kind = p.get("kind", "letf")
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

    # 1x underlying beta-hedged return: £1 long the first leg, £beta short the second.
    r_under = rets["long"] - beta * rets["short"]

    if kind == "cfd":
        # Net of T212 overnight financing on £1 long + £beta short exposure.
        # Long  pays  (rate + markup)/365 per night on its £1 notional.
        # Short earns (rate - markup)/365 per night on its £beta notional.
        # Charge per calendar night, so a Fri->Mon gap is billed for 3 nights
        # (this reproduces T212's weekend "triple charge").
        rate = bank_rate_series(rets.index)
        nights = pd.Series(rets.index, index=rets.index).diff().dt.days.fillna(1.0)
        daily_long  = (rate + MARKUP_ANNUAL) / 365.0
        daily_short = (rate - MARKUP_ANNUAL) / 365.0
        fin = (-daily_long * 1.0 + daily_short * beta) * nights
        r_alt = r_under + fin
    else:
        # LETF wrapper
        L_a = p["long"]["lev"]
        L_b = p["short"]["lev"]
        denom  = L_a * beta + L_b
        w_long  = L_b / denom
        w_short = (L_a * beta) / denom
        r_alt = L_a * w_long * rets["long"] - L_b * w_short * rets["short"]

    df = pd.DataFrame({"r_under": r_under, "r_alt": r_alt}).dropna()
    eq_under = (1.0 + df["r_under"]).cumprod()
    eq_alt   = (1.0 + df["r_alt"]).cumprod()

    bars = [
        [idx.strftime("%Y-%m-%d"), round(float(u), 6), round(float(l), 6)]
        for idx, u, l in zip(df.index, eq_under.values, eq_alt.values)
    ]
    meta = {
        "slug":  p["slug"],
        "name":  p["name"],
        "kind":  kind,
        "blurb": p["blurb"],
        "long":  p["long"],
        "short": p["short"],
        "beta_clip":  p["beta_clip"],
        "lookback":   LOOKBACK,
        "first_date": bars[0][0],
        "last_date":  bars[-1][0],
        "n_bars":     len(bars),
    }
    if kind == "cfd":
        meta["markup_annual"] = MARKUP_ANNUAL
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
            "kind":  meta["kind"],
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
