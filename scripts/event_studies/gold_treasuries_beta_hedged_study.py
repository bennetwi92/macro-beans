"""Long gold / short US 10Y Treasuries portfolio, via LSE 3x LETPs.

Pure beta-hedging breaks here: gold-vs-bond correlation flips between safe-
haven (positive beta) and inflation-surprise (negative beta) regimes.
Negative beta + (w1+w2=1) constraint sends weights to +/- infinity. We
therefore clip beta to [0.1, 2.0] for sizing purposes — weights stay in
[0.33, 0.91] for 3GOL and [0.09, 0.67] for 3TYS. Days where natural beta
falls outside that range are flagged via the `beta_clipped` column.

Underlying construction:
  r_under[t]  = r_gold[t] - beta_clip[t] * r_zn[t]
  beta_raw[t] = cov(r_gold, r_zn over t-LOOKBACK..t-1) / var(r_zn over same)
  beta_clip[t] = clip(beta_raw[t], 0.1, 2.0)

Single-day LETF expression:
  Long  3GOL.L  (WisdomTree Gold 3x Daily Leveraged)         -> +3 * r_gold
  Long  3TYS.L  (WisdomTree US Treasuries 10Y 3x Daily Short) -> -3 * r_zn

Sizing (clipped):
  w1 = 1 / (1 + beta_clip),  w2 = beta_clip / (1 + beta_clip)
  r_letf[t] = w1 * 3 * r_gold[t] - w2 * 3 * r_zn[t]

Captures: CPI/PCE prints, FOMC meetings, debt-ceiling / fiscal shocks,
Fed-credibility events, real-yield repricing, geopolitical safe-haven
bids that affect gold but not bonds equally.

Outputs:
  data/event_studies/gold_treasuries_beta_hedged_daily.csv     full daily series
  data/event_studies/gold_treasuries_beta_hedged_extremes.csv  top 25 LETF winners / losers
  data/event_studies/gold_treasuries_beta_hedged.png           equity curve + histogram
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

LOOKBACK = 60
TOP_N = 25
START = "2002-01-02"
BETA_LO, BETA_HI = 0.1, 2.0   # clip to keep weights in a practical range


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch_closes() -> pd.DataFrame:
    raw = yf.download(["GC=F", "ZN=F"], start=START, progress=False, auto_adjust=True)
    closes = raw["Close"].dropna().copy()
    closes.columns = ["gold" if c == "GC=F" else "zn" for c in closes.columns]
    return closes[["gold", "zn"]]


def build_portfolio(closes: pd.DataFrame) -> pd.DataFrame:
    rets = closes.pct_change().dropna()
    cov = rets["gold"].rolling(LOOKBACK).cov(rets["zn"])
    var = rets["zn"].rolling(LOOKBACK).var()
    beta_raw = (cov / var).shift(1)
    beta_clip = beta_raw.clip(BETA_LO, BETA_HI)
    clipped_flag = (beta_raw < BETA_LO) | (beta_raw > BETA_HI)

    r_under = rets["gold"] - beta_clip * rets["zn"]
    w_3gol = 1.0 / (1.0 + beta_clip)
    w_3tys = beta_clip / (1.0 + beta_clip)
    r_letf = w_3gol * 3.0 * rets["gold"] + w_3tys * (-3.0) * rets["zn"]

    out = pd.DataFrame({
        "r_gold":     rets["gold"],
        "r_zn":       rets["zn"],
        "beta_raw":   beta_raw,
        "beta_clip":  beta_clip,
        "clipped":    clipped_flag,
        "w_3gol":     w_3gol,
        "w_3tys":     w_3tys,
        "r_under":    r_under,
        "r_letf":     r_letf,
    }).dropna()
    return out


def summarise(df: pd.DataFrame) -> None:
    pct_clipped = df["clipped"].mean() * 100
    print(f"\nSample: {df.index[0].date()} -> {df.index[-1].date()}  (n={len(df)})")
    print(f"Beta raw:   mean={df['beta_raw'].mean():.3f}  median={df['beta_raw'].median():.3f}  "
          f"p05={df['beta_raw'].quantile(0.05):.3f}  p95={df['beta_raw'].quantile(0.95):.3f}")
    print(f"Beta clip:  bounds=[{BETA_LO},{BETA_HI}]  "
          f"clipped on {pct_clipped:.1f}% of days "
          f"(below={(df['beta_raw'] < BETA_LO).mean()*100:.1f}%  "
          f"above={(df['beta_raw'] > BETA_HI).mean()*100:.1f}%)")
    print(f"Sizing:    w_3GOL median={df['w_3gol'].median():.2f}  "
          f"w_3TYS median={df['w_3tys'].median():.2f}  "
          f"(LETF amplification ~ {df['r_letf'].std()/df['r_under'].std():.2f}x underlying)")
    for name, col in (("Underlying", "r_under"), ("LETF wrapper", "r_letf")):
        ann_mean = df[col].mean() * 252 * 100
        ann_vol = df[col].std() * np.sqrt(252) * 100
        sharpe = ann_mean / ann_vol if ann_vol else np.nan
        print(f"{name:14s} ann mean={ann_mean:+.2f}%  ann vol={ann_vol:.2f}%  "
              f"Sharpe={sharpe:.2f}  daily min={df[col].min()*100:+.2f}%  "
              f"max={df[col].max()*100:+.2f}%")


def extremes(df: pd.DataFrame, n: int) -> pd.DataFrame:
    winners = df.nlargest(n, "r_letf").copy()
    losers = df.nsmallest(n, "r_letf").copy()
    winners["side"] = "WIN"
    losers["side"] = "LOSE"
    table = pd.concat([winners, losers])
    table["r_letf_pct"] = (table["r_letf"] * 100).round(2)
    table["r_under_pct"] = (table["r_under"] * 100).round(2)
    table["r_gold_pct"] = (table["r_gold"] * 100).round(2)
    table["r_zn_pct"] = (table["r_zn"] * 100).round(2)
    table["beta_raw"] = table["beta_raw"].round(2)
    table["beta_clip"] = table["beta_clip"].round(2)
    table["w_3gol"] = table["w_3gol"].round(2)
    table["w_3tys"] = table["w_3tys"].round(2)
    return table[["side", "r_letf_pct", "r_under_pct", "r_gold_pct",
                  "r_zn_pct", "beta_raw", "beta_clip", "w_3gol", "w_3tys"]]


def plot(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    (1 + df["r_under"]).cumprod().plot(ax=axes[0], color="C0", label="Underlying (1x pair)")
    (1 + df["r_letf"]).cumprod().plot(ax=axes[0], color="C3", alpha=0.8,
                                      label="LETF wrapper (3GOL+3TYS)")
    axes[0].set_title(f"Beta-hedged Long Gold / Short UST 10Y — cumulative "
                      f"(lookback={LOOKBACK}d, daily reset)")
    axes[0].set_ylabel("Equity ($1 start, no costs)")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.3)

    axes[1].hist(df["r_letf"] * 100, bins=120, color="C3", alpha=0.7, label="LETF daily %")
    axes[1].hist(df["r_under"] * 100, bins=120, color="C0", alpha=0.5, label="Underlying daily %")
    axes[1].set_title("Daily return distribution (%)")
    axes[1].axvline(0, color="black", lw=0.8)
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"Chart saved -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "data" / "event_studies"
    out_dir.mkdir(parents=True, exist_ok=True)

    closes = fetch_closes()
    df = build_portfolio(closes)
    summarise(df)

    daily_path = out_dir / "gold_treasuries_beta_hedged_daily.csv"
    df.to_csv(daily_path)
    print(f"\nDaily saved -> {daily_path}")

    ext = extremes(df, TOP_N)
    ext_path = out_dir / "gold_treasuries_beta_hedged_extremes.csv"
    ext.to_csv(ext_path)
    print(f"Extremes saved -> {ext_path}\n")

    print(f"=== Top {TOP_N} LETF winners (long-gold/short-UST10Y beta-hedged) ===")
    print(ext[ext["side"] == "WIN"].to_string())
    print(f"\n=== Top {TOP_N} LETF losers ===")
    print(ext[ext["side"] == "LOSE"].to_string())

    plot(df, out_dir / "gold_treasuries_beta_hedged.png")


if __name__ == "__main__":
    main()
