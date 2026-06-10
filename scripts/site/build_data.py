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

# Each entry: slug, Yahoo ticker (LSE ETF), display name, sublabel, group.
# `group` is the dropdown section heading on the strategy page; pick liquid
# LSE-listed ETFs so the strategy is tradable (see the macro-beans-site skill).
# The set spans major macro themes (regions, rates, credit, commodities) and
# microeconomic themes (US sectors, single-theme baskets).
INSTRUMENTS = [
    # ---- Stock Markets (broad equity indices + regions) ----
    ("spx",        "VUSA.L",  "S&P 500",             "US Large Cap",          "Stock Markets"),
    ("ndx",        "EQQQ.L",  "Nasdaq 100",          "US Tech",               "Stock Markets"),
    ("ftse",       "ISF.L",   "FTSE 100",            "UK Large Cap",          "Stock Markets"),
    ("ftse250",    "MIDD.L",  "FTSE 250",            "UK Mid Cap",            "Stock Markets"),
    ("world",      "IWDA.L",  "MSCI World",          "Global Equity",         "Stock Markets"),
    ("em",         "EIMI.L",  "MSCI Emerging Mkts",  "Emerging Markets",      "Stock Markets"),
    ("japan",      "IJPA.L",  "MSCI Japan",          "Japan Equity",          "Stock Markets"),
    ("estoxx",     "CSX5.L",  "Euro Stoxx 50",       "Europe Equity",         "Stock Markets"),
    ("china",      "FXC.L",   "China Large Cap",     "China Equity",          "Stock Markets"),
    ("india",      "NDIA.L",  "India",               "India Equity",          "Stock Markets"),
    ("asiaxjp",    "CPXJ.L",  "Asia Pacific",        "ex-Japan",              "Stock Markets"),
    # ---- US Sectors (microeconomic / sector-rotation themes) ----
    ("us_tech",    "IUIT.L",  "US Technology",       "Technology",            "US Sectors"),
    ("us_fins",    "IUFS.L",  "US Financials",       "Financials",            "US Sectors"),
    ("us_energy",  "IUES.L",  "US Energy",           "Energy",                "US Sectors"),
    ("us_health",  "IUHC.L",  "US Health Care",      "Health Care",           "US Sectors"),
    ("us_staples", "IUCS.L",  "US Cons. Staples",    "Consumer Staples",      "US Sectors"),
    ("us_discr",   "IUCD.L",  "US Cons. Discretionary","Consumer Discretionary","US Sectors"),
    ("us_util",    "IUUS.L",  "US Utilities",        "Utilities",             "US Sectors"),
    ("us_indus",   "IUIS.L",  "US Industrials",      "Industrials",           "US Sectors"),
    # ---- Themes (single-theme baskets) ----
    ("cleanenergy","INRG.L",  "Clean Energy",        "Global Clean Energy",   "Themes"),
    ("robotics",   "RBOT.L",  "Automation & Robotics","Robotics & Automation", "Themes"),
    ("semis",      "SEMI.L",  "Semiconductors",      "Global Chipmakers",     "Themes"),
    ("goldminers", "SPGP.L",  "Gold Miners",         "Gold Producers",        "Themes"),
    ("ai",         "AIAG.L",  "AI & Big Data",       "Artificial Intelligence","Themes"),
    # ---- Bonds & Credit (rates + credit macro themes) ----
    ("ustreas",    "IDTL.L",  "US Treasuries 20Y+",  "US Long Bonds",         "Bonds & Credit"),
    ("gilts",      "IGLT.L",  "UK Gilts",            "UK Government Bonds",    "Bonds & Credit"),
    ("tips",       "ITPS.L",  "US Inflation Bonds",  "US Inflation-Linked",   "Bonds & Credit"),
    ("hyield",     "IHYU.L",  "US High Yield",       "USD High-Yield Credit", "Bonds & Credit"),
    ("igcorp",     "LQDE.L",  "US Corp Bonds",       "USD Investment Grade",  "Bonds & Credit"),
    ("embd",       "SEMB.L",  "EM Bonds",            "Emerging-Market Debt",  "Bonds & Credit"),
    ("tbills",     "IBTL.L",  "US T-Bills",          "Cash / 0-1Y Treasuries","Bonds & Credit"),
    # ---- Commodities ----
    ("gold",       "SGLN.L",  "Gold",                "Precious Metal",        "Commodities"),
    ("silver",     "SSLN.L",  "Silver",              "Precious Metal",        "Commodities"),
    ("copper",     "COPA.L",  "Copper",              "Industrial Metal",      "Commodities"),
    ("brent",      "BRNT.L",  "Brent Oil",           "Energy",                "Commodities"),
    ("wti",        "CRUD.L",  "WTI Crude",           "Energy",                "Commodities"),
    ("natgas",     "NGAS.L",  "Natural Gas",         "Energy",                "Commodities"),
    ("broadcomm",  "ICOM.L",  "Broad Commodities",   "Diversified Basket",    "Commodities"),
    # ---- Property ----
    ("reit_dev",   "IWDP.L",  "Global Property",     "Developed REITs",       "Property"),
    ("reit_uk",    "IUKP.L",  "UK Property",         "UK REITs",              "Property"),
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

    for slug, ticker, name, sublabel, group in INSTRUMENTS:
        label = f"{name} ({ticker})"
        print(f"  fetching {label:<28s} ...", end=" ", flush=True)
        bars = fetch_bars(ticker)
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
        path.write_text(json.dumps(payload, separators=(",", ":")))
        size_kb = path.stat().st_size / 1024
        print(f"{len(bars):>5d} bars  ->  {path.name} ({size_kb:.0f} kB)")
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
    (out_dir / "instruments.json").write_text(
        json.dumps(menu_payload, separators=(",", ":"))
    )
    print(f"\nMenu written -> instruments.json ({len(menu)} entries)")
    print(f"Built at {built_at}")


if __name__ == "__main__":
    main()
