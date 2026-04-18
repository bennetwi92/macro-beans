"""Beta-hedged long FTSE 250 / short FTSE 100 portfolio, expressed via LSE LETFs.

Underlying construction:
  r_under[t] = r_MCX[t] - beta[t] * r_FTSE[t]
  beta[t]    = cov(r_MCX, r_FTSE over t-LOOKBACK..t-1) / var(r_FTSE over same)

Single-day LETF expression (style: intraday-to-1d swing trades, no decay over 1 day):
  Long  2MCL.L  (WisdomTree FTSE 250 2x Leveraged Daily)  -> +2 * r_MCX
  Long  3UKS.L  (WisdomTree FTSE 100 3x Daily Short)      -> -3 * r_FTSE

Beta-hedged sizing solves 2*w1*beta = 3*w2 with w1+w2=1, giving
  w1 = 3 / (3 + 2*beta),  w2 = 2*beta / (3 + 2*beta)
  r_letf[t] = (6 / (3 + 2*beta[t])) * r_under[t]

i.e. the LETF wrapper amplifies the beta-hedged underlying by ~1.31x at the
sample-mean beta (0.79). Hedge recomputed daily from prior 60-day window
(no look-ahead). Pair reflects UK domestic cyclicals vs global earners, so
winners/losers cluster on UK-specific fiscal/political/BoE/sterling shocks.

Outputs:
  data/event_studies/ftse250_ftse100_beta_hedged_daily.csv   full daily series
  data/event_studies/ftse250_ftse100_beta_hedged_extremes.csv top 25 LETF winners / losers
  data/event_studies/ftse250_ftse100_beta_hedged.png          equity curve + histogram
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

LOOKBACK = 60          # trading days of beta estimation
TOP_N = 25             # how many extreme days to list each side
START = "1998-01-01"   # ~28 years back, covers dot-com, GFC, Brexit, Covid, LDI, etc.


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch_closes() -> pd.DataFrame:
    raw = yf.download(["^FTMC", "^FTSE"], start=START, progress=False, auto_adjust=True)
    closes = raw["Close"].dropna().copy()
    closes.columns = ["ftse100" if c == "^FTSE" else "ftse250" for c in closes.columns]
    return closes[["ftse250", "ftse100"]]


def build_portfolio(closes: pd.DataFrame) -> pd.DataFrame:
    rets = closes.pct_change().dropna()
    cov = rets["ftse250"].rolling(LOOKBACK).cov(rets["ftse100"])
    var = rets["ftse100"].rolling(LOOKBACK).var()
    beta = (cov / var).shift(1)                      # use yesterday's beta for today
    r_under = rets["ftse250"] - beta * rets["ftse100"]

    # LETF wrapper: long 2MCL (+2x FTSE 250) + long 3UKS (-3x FTSE 100), beta-hedged
    w_2mcl = 3.0 / (3.0 + 2.0 * beta)
    w_3uks = (2.0 * beta) / (3.0 + 2.0 * beta)
    r_letf = w_2mcl * 2.0 * rets["ftse250"] + w_3uks * (-3.0) * rets["ftse100"]

    out = pd.DataFrame({
        "r_ftse250": rets["ftse250"],
        "r_ftse100": rets["ftse100"],
        "beta": beta,
        "w_2mcl": w_2mcl,
        "w_3uks": w_3uks,
        "r_under": r_under,
        "r_letf":  r_letf,
    }).dropna()
    return out


def summarise(df: pd.DataFrame) -> None:
    print(f"\nSample: {df.index[0].date()} -> {df.index[-1].date()}  (n={len(df)})")
    print(f"Beta 60d:  mean={df['beta'].mean():.3f}  median={df['beta'].median():.3f}  "
          f"p05={df['beta'].quantile(0.05):.3f}  p95={df['beta'].quantile(0.95):.3f}")
    print(f"Sizing:    w_2MCL median={df['w_2mcl'].median():.2f}  "
          f"w_3UKS median={df['w_3uks'].median():.2f}  "
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
    table["r_ftse250_pct"] = (table["r_ftse250"] * 100).round(2)
    table["r_ftse100_pct"] = (table["r_ftse100"] * 100).round(2)
    table["beta"] = table["beta"].round(2)
    table["w_2mcl"] = table["w_2mcl"].round(2)
    table["w_3uks"] = table["w_3uks"].round(2)
    return table[["side", "r_letf_pct", "r_under_pct", "r_ftse250_pct",
                  "r_ftse100_pct", "beta", "w_2mcl", "w_3uks"]]


def plot(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    (1 + df["r_under"]).cumprod().plot(ax=axes[0], color="C0", label="Underlying (1x pair)")
    (1 + df["r_letf"]).cumprod().plot(ax=axes[0], color="C3", alpha=0.8,
                                      label="LETF wrapper (2MCL+3UKS)")
    axes[0].set_title(f"Beta-hedged Long FTSE 250 / Short FTSE 100 — cumulative "
                      f"(lookback={LOOKBACK}d, daily reset)")
    axes[0].set_ylabel("Equity ($1 start, no costs)")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.3)

    axes[1].hist(df["r_letf"] * 100, bins=120, color="C3", alpha=0.7,
                 label="LETF daily %")
    axes[1].hist(df["r_under"] * 100, bins=120, color="C0", alpha=0.5,
                 label="Underlying daily %")
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

    daily_path = out_dir / "ftse250_ftse100_beta_hedged_daily.csv"
    df.to_csv(daily_path)
    print(f"\nDaily saved -> {daily_path}")

    ext = extremes(df, TOP_N)
    ext_path = out_dir / "ftse250_ftse100_beta_hedged_extremes.csv"
    ext.to_csv(ext_path)
    print(f"Extremes saved -> {ext_path}\n")

    print(f"=== Top {TOP_N} winners (long-MCX/short-FTSE100 beta-hedged) ===")
    print(ext[ext["side"] == "WIN"].to_string())
    print(f"\n=== Top {TOP_N} losers ===")
    print(ext[ext["side"] == "LOSE"].to_string())

    plot(df, out_dir / "ftse250_ftse100_beta_hedged.png")


if __name__ == "__main__":
    main()
