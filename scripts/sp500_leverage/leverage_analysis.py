"""S&P 500 monthly-return probability analysis for LSE leveraged products.

Builds synthetic NAV series for 1x, 2x daily, and 3x daily leveraged S&P 500
trackers using daily compounding with realistic TER + financing costs, then
computes:
  - probability of positive monthly returns,
  - distribution stats and worst/best months,
  - DCA (GBP 100/month) terminal-value distribution over rolling windows.

Run from repo root:
    /usr/local/bin/python3 scripts/sp500_leverage/leverage_analysis.py
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data" / "sp500_leverage"
OUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Product:
    name: str
    leverage: float
    ter: float          # annual expense ratio (decimal)
    swap_spread: float  # extra annual financing spread on the borrowed leg


# Representative LSE-listed S&P 500 trackers.
# CSPX: iShares Core S&P 500 UCITS (1x).
# 2USL / SP5L: 2x daily leveraged S&P 500 ETPs (e.g. WisdomTree).
# 3USL / 3LUS: 3x daily leveraged S&P 500 ETPs (e.g. WisdomTree).
PRODUCTS = [
    Product("1x  CSPX",         1.0, ter=0.0007, swap_spread=0.0),
    Product("2x  (e.g. 2USL)",  2.0, ter=0.0075, swap_spread=0.0040),
    Product("3x  (e.g. 3USL)",  3.0, ter=0.0099, swap_spread=0.0050),
]

TRADING_DAYS = 252


def fetch_data() -> pd.DataFrame:
    """Daily total-return index and 13-week T-bill yield, joined and clean."""
    tr = yf.Ticker("^SP500TR").history(period="max", auto_adjust=False)["Close"]
    tr.index = tr.index.tz_localize(None).normalize()
    tr = tr.rename("sp500tr")

    rf = yf.Ticker("^IRX").history(period="max", auto_adjust=False)["Close"]
    rf.index = rf.index.tz_localize(None).normalize()
    rf = rf.rename("rf_pct")

    df = pd.concat([tr, rf], axis=1).sort_index()
    df["rf_pct"] = df["rf_pct"].ffill()
    df = df.dropna(subset=["sp500tr"])
    df["ret"] = df["sp500tr"].pct_change()
    df = df.dropna()
    df["rf_daily"] = (df["rf_pct"].clip(lower=0) / 100.0) / TRADING_DAYS
    return df


def synth_nav(df: pd.DataFrame, p: Product) -> pd.Series:
    """Daily-compounded NAV for a leveraged product.

    daily NAV change = L * r - (L-1) * rf_daily - (L-1) * swap_spread/252 - TER/252
    """
    daily = (
        p.leverage * df["ret"]
        - (p.leverage - 1.0) * df["rf_daily"]
        - (p.leverage - 1.0) * p.swap_spread / TRADING_DAYS
        - p.ter / TRADING_DAYS
    )
    nav = (1.0 + daily).cumprod()
    nav.iloc[0] = 1.0
    return nav.rename(p.name)


def monthly_returns(nav: pd.Series) -> pd.Series:
    eom = nav.resample("ME").last()
    return eom.pct_change().dropna()


def summarise(monthly: pd.Series) -> dict:
    out = {
        "n_months": int(monthly.size),
        "p_positive_%": 100.0 * (monthly > 0).mean(),
        "mean_%": 100.0 * monthly.mean(),
        "median_%": 100.0 * monthly.median(),
        "std_%": 100.0 * monthly.std(),
        "skew": monthly.skew(),
        "kurtosis": monthly.kurtosis(),
        "best_month_%": 100.0 * monthly.max(),
        "worst_month_%": 100.0 * monthly.min(),
        "ann_return_%": 100.0 * ((1 + monthly.mean()) ** 12 - 1),
        "ann_vol_%": 100.0 * monthly.std() * np.sqrt(12),
    }
    cum = (1 + monthly).cumprod()
    dd = cum / cum.cummax() - 1
    out["max_drawdown_%"] = 100.0 * dd.min()
    out["cagr_%"] = 100.0 * (cum.iloc[-1] ** (12 / len(monthly)) - 1)
    return out


def rolling_p_positive(monthly: pd.Series, window: int) -> pd.Series:
    """Total return over a rolling N-month window, in % terms."""
    return (1 + monthly).rolling(window).apply(np.prod, raw=True) - 1


def dca_terminal_values(monthly: pd.Series, window_months: int, contribution: float = 100.0) -> pd.Series:
    """For each rolling start month, compute terminal value of contributing
    `contribution` GBP at the start of each month for `window_months` months,
    earning the realised monthly returns of the product."""
    r = monthly.values
    n = len(r)
    if n < window_months:
        return pd.Series(dtype=float)
    out = np.empty(n - window_months + 1)
    for i in range(out.size):
        bal = 0.0
        for k in range(window_months):
            bal = (bal + contribution) * (1 + r[i + k])
        out[i] = bal
    idx = monthly.index[window_months - 1 :]
    return pd.Series(out, index=idx, name=f"dca_{window_months}m")


def main() -> None:
    df = fetch_data()
    print(f"Data: {df.index.min().date()} -> {df.index.max().date()}, {len(df):,} daily obs")

    nav_frames = {p.name: synth_nav(df, p) for p in PRODUCTS}
    nav_df = pd.concat(nav_frames.values(), axis=1)
    nav_df.to_csv(OUT_DIR / "nav_series.csv")

    monthly_frames = {name: monthly_returns(nav) for name, nav in nav_frames.items()}
    monthly_df = pd.concat(monthly_frames.values(), axis=1)
    monthly_df.columns = list(nav_frames.keys())
    monthly_df.to_csv(OUT_DIR / "monthly_returns.csv")

    summary = pd.DataFrame({name: summarise(m) for name, m in monthly_frames.items()}).T
    summary = summary.round(3)
    summary.to_csv(OUT_DIR / "summary_stats.csv")
    print("\n=== Monthly return statistics ===")
    print(summary.to_string())

    # Rolling 12-month total return: probability of beating 0 over a year.
    print("\n=== Probability total return > 0 over rolling windows ===")
    rolling_rows = []
    for window in (1, 3, 6, 12, 24, 36, 60, 120):
        row = {"window_months": window}
        for name, m in monthly_frames.items():
            r = rolling_p_positive(m, window).dropna()
            row[name] = round(100.0 * (r > 0).mean(), 2) if not r.empty else np.nan
        rolling_rows.append(row)
    rolling_df = pd.DataFrame(rolling_rows).set_index("window_months")
    rolling_df.to_csv(OUT_DIR / "rolling_p_positive.csv")
    print(rolling_df.to_string())

    # DCA: GBP 100/month for 5/10/20 years; report distribution of terminal values.
    print("\n=== GBP 100/month DCA terminal values (rolling start months) ===")
    dca_rows = []
    for years in (5, 10, 20):
        window = years * 12
        invested = 100.0 * window
        for name, m in monthly_frames.items():
            tv = dca_terminal_values(m, window)
            if tv.empty:
                continue
            dca_rows.append({
                "years": years,
                "product": name,
                "n_windows": tv.size,
                "invested_gbp": invested,
                "p_beat_invested_%": round(100.0 * (tv > invested).mean(), 2),
                "median_terminal_gbp": round(float(tv.median()), 0),
                "p10_terminal_gbp": round(float(tv.quantile(0.10)), 0),
                "p90_terminal_gbp": round(float(tv.quantile(0.90)), 0),
                "min_terminal_gbp": round(float(tv.min()), 0),
                "max_terminal_gbp": round(float(tv.max()), 0),
            })
    dca_df = pd.DataFrame(dca_rows)
    dca_df.to_csv(OUT_DIR / "dca_terminal_values.csv", index=False)
    print(dca_df.to_string(index=False))

    print(f"\nOutputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
