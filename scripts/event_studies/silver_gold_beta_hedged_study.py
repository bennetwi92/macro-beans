"""Beta-hedged long silver / short gold portfolio, expressed via LSE 3x LETPs.

Underlying construction:
  r_under[t] = r_silver[t] - beta[t] * r_gold[t]
  beta[t]    = cov(r_silver, r_gold over t-LOOKBACK..t-1) / var(r_gold over same)

Single-day LETF expression (intraday-to-1d swing trades, no decay over 1 day):
  Long  3SIL.L  (WisdomTree Silver 3x Daily Leveraged)  -> +3 * r_silver
  Long  3GOS.L  (WisdomTree Gold 3x Daily Short)        -> -3 * r_gold

Beta-hedged sizing solves 3*w1*beta = 3*w2 with w1+w2=1, giving
  w1 = 1 / (1 + beta),  w2 = beta / (1 + beta)
  r_letf[t] = (3 / (1 + beta[t])) * r_under[t]

i.e. the LETF wrapper amplifies the beta-hedged underlying by ~1.7x at the
sample-mean silver-vs-gold beta (~0.75). Hedge recomputed daily from prior
60-day window (no look-ahead). Pair captures the gold/silver ratio dynamic:
silver is the high-beta industrial precious metal, gold the safe-haven.
Long-silver/short-gold expresses pro-cyclical / reflationary view.

Outputs:
  data/event_studies/silver_gold_beta_hedged_daily.csv     full daily series
  data/event_studies/silver_gold_beta_hedged_extremes.csv  top 25 LETF winners / losers
  data/event_studies/silver_gold_beta_hedged.png           equity curve + histogram
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

LOOKBACK = 60
TOP_N = 25
START = "2000-08-30"


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch_closes() -> pd.DataFrame:
    raw = yf.download(["SI=F", "GC=F"], start=START, progress=False, auto_adjust=True)
    closes = raw["Close"].dropna().copy()
    closes.columns = ["gold" if c == "GC=F" else "silver" for c in closes.columns]
    return closes[["silver", "gold"]]


def build_portfolio(closes: pd.DataFrame) -> pd.DataFrame:
    rets = closes.pct_change().dropna()
    cov = rets["silver"].rolling(LOOKBACK).cov(rets["gold"])
    var = rets["gold"].rolling(LOOKBACK).var()
    beta = (cov / var).shift(1)
    r_under = rets["silver"] - beta * rets["gold"]

    # LETF wrapper: long 3SIL (+3x silver) + long 3GOS (-3x gold), beta-hedged
    w_3sil = 1.0 / (1.0 + beta)
    w_3gos = beta / (1.0 + beta)
    r_letf = w_3sil * 3.0 * rets["silver"] + w_3gos * (-3.0) * rets["gold"]

    out = pd.DataFrame({
        "r_silver": rets["silver"],
        "r_gold":   rets["gold"],
        "beta":     beta,
        "w_3sil":   w_3sil,
        "w_3gos":   w_3gos,
        "r_under":  r_under,
        "r_letf":   r_letf,
    }).dropna()
    return out


def summarise(df: pd.DataFrame) -> None:
    print(f"\nSample: {df.index[0].date()} -> {df.index[-1].date()}  (n={len(df)})")
    print(f"Beta 60d:  mean={df['beta'].mean():.3f}  median={df['beta'].median():.3f}  "
          f"p05={df['beta'].quantile(0.05):.3f}  p95={df['beta'].quantile(0.95):.3f}")
    print(f"Sizing:    w_3SIL median={df['w_3sil'].median():.2f}  "
          f"w_3GOS median={df['w_3gos'].median():.2f}  "
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
    table["r_silver_pct"] = (table["r_silver"] * 100).round(2)
    table["r_gold_pct"] = (table["r_gold"] * 100).round(2)
    table["beta"] = table["beta"].round(2)
    table["w_3sil"] = table["w_3sil"].round(2)
    table["w_3gos"] = table["w_3gos"].round(2)
    return table[["side", "r_letf_pct", "r_under_pct", "r_silver_pct",
                  "r_gold_pct", "beta", "w_3sil", "w_3gos"]]


def plot(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    (1 + df["r_under"]).cumprod().plot(ax=axes[0], color="C0", label="Underlying (1x pair)")
    (1 + df["r_letf"]).cumprod().plot(ax=axes[0], color="C3", alpha=0.8,
                                      label="LETF wrapper (3SIL+3GOS)")
    axes[0].set_title(f"Beta-hedged Long Silver / Short Gold — cumulative "
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

    daily_path = out_dir / "silver_gold_beta_hedged_daily.csv"
    df.to_csv(daily_path)
    print(f"\nDaily saved -> {daily_path}")

    ext = extremes(df, TOP_N)
    ext_path = out_dir / "silver_gold_beta_hedged_extremes.csv"
    ext.to_csv(ext_path)
    print(f"Extremes saved -> {ext_path}\n")

    print(f"=== Top {TOP_N} LETF winners (long-silver/short-gold beta-hedged) ===")
    print(ext[ext["side"] == "WIN"].to_string())
    print(f"\n=== Top {TOP_N} LETF losers ===")
    print(ext[ext["side"] == "LOSE"].to_string())

    plot(df, out_dir / "silver_gold_beta_hedged.png")


if __name__ == "__main__":
    main()
