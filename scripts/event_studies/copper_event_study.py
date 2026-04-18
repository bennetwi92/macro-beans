"""Copper event study — what events drive large moves in 3HCL.L / 3HCS.L?

Approach:
  1. Pull 3HCL.L (3x long copper ETP) since 2012 inception.
  2. Compute daily returns; rank top-20 up-days and top-20 down-days.
  3. Cross-check each against copper futures (HG=F) to confirm it's a copper-driven
     move, not an ETP tracking-error blip.
  4. Tag clusters (consecutive large-move days = same underlying event).

Outputs:
  data/copper_event_study_top_moves.csv      ranked top moves with HG=F return
  data/copper_event_study_chart.png          3HCL price + marked event dates

Annotations of *what* drove each top date are added by hand into
docs/copper_event_study.md after running this script.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "event_studies"
DATA.mkdir(parents=True, exist_ok=True)

TOP_N = 25  # top moves in each direction


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch(ticker: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period="max", auto_adjust=True)
    df = _flatten(df)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def main() -> None:
    print("Fetching 3HCL.L, 3HCS.L, HG=F ...")
    hcl = fetch("3HCL.L")
    hcs = fetch("3HCS.L")
    hg = fetch("HG=F")

    print(f"  3HCL.L : {len(hcl):>5} rows, {hcl.index.min().date()} -> {hcl.index.max().date()}")
    print(f"  3HCS.L : {len(hcs):>5} rows, {hcs.index.min().date()} -> {hcs.index.max().date()}")
    print(f"  HG=F   : {len(hg):>5} rows, {hg.index.min().date()} -> {hg.index.max().date()}")

    rets = pd.DataFrame({
        "3HCL_ret": hcl["Close"].pct_change(),
        "3HCS_ret": hcs["Close"].pct_change(),
        "HG_ret":   hg["Close"].pct_change(),
        "3HCL_close": hcl["Close"],
        "HG_close":   hg["Close"],
        "3HCL_volume": hcl["Volume"],
    }).dropna(subset=["3HCL_ret"])

    # Implied copper move from 3HCL (since 3x daily): copper_implied = 3HCL_ret / 3
    rets["copper_implied"] = rets["3HCL_ret"] / 3.0

    top_up = rets.nlargest(TOP_N, "3HCL_ret").copy()
    top_dn = rets.nsmallest(TOP_N, "3HCL_ret").copy()
    top_up["direction"] = "UP"
    top_dn["direction"] = "DOWN"
    top = pd.concat([top_up, top_dn]).sort_index()

    out = top.reset_index()
    out = out.rename(columns={out.columns[0]: "date"})
    out = out[["date", "direction", "3HCL_ret", "3HCS_ret", "HG_ret",
               "copper_implied", "3HCL_close", "HG_close", "3HCL_volume"]]
    # Format
    for c in ["3HCL_ret", "3HCS_ret", "HG_ret", "copper_implied"]:
        out[c] = (out[c] * 100).round(2)
    out["3HCL_close"] = out["3HCL_close"].round(2)
    out["HG_close"] = out["HG_close"].round(4)
    out["3HCL_volume"] = out["3HCL_volume"].astype(int)
    out["date"] = pd.to_datetime(out["date"]).dt.date

    csv_path = DATA / "copper_event_study_top_moves.csv"
    out.to_csv(csv_path, index=False)
    print(f"\nWrote {csv_path}")

    # Print to stdout for inspection / event annotation
    print("\n=== TOP UP MOVES (3HCL daily %) ===")
    print(out[out["direction"] == "UP"].sort_values("3HCL_ret", ascending=False).to_string(index=False))
    print("\n=== TOP DOWN MOVES (3HCL daily %) ===")
    print(out[out["direction"] == "DOWN"].sort_values("3HCL_ret").to_string(index=False))

    # Chart
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(hcl.index, hcl["Close"], color="navy", lw=1.0, label="3HCL.L close")
    ax1.set_yscale("log")
    ax1.set_ylabel("3HCL.L close (log)")
    ax1.set_title("Copper 3x ETP (3HCL.L) — top 25 up & down days marked")
    up_dates = top_up.index
    dn_dates = top_dn.index
    ax1.scatter(up_dates, hcl.loc[up_dates, "Close"], color="green", s=40, marker="^",
                zorder=5, label=f"top {TOP_N} up")
    ax1.scatter(dn_dates, hcl.loc[dn_dates, "Close"], color="red", s=40, marker="v",
                zorder=5, label=f"top {TOP_N} down")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    ax2.bar(rets.index, rets["3HCL_ret"] * 100, color="grey", width=1.0, alpha=0.6)
    ax2.scatter(up_dates, rets.loc[up_dates, "3HCL_ret"] * 100, color="green", s=30, marker="^", zorder=5)
    ax2.scatter(dn_dates, rets.loc[dn_dates, "3HCL_ret"] * 100, color="red", s=30, marker="v", zorder=5)
    ax2.set_ylabel("3HCL daily return (%)")
    ax2.axhline(0, color="black", lw=0.5)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    chart = DATA / "copper_event_study_chart.png"
    fig.savefig(chart, dpi=120)
    print(f"Wrote {chart}")

    # Distribution stats
    print("\n=== 3HCL daily return distribution ===")
    desc = (rets["3HCL_ret"] * 100).describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99])
    print(desc.round(2).to_string())


if __name__ == "__main__":
    main()
