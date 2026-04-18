"""Oil Friday-crash study.

Tests the hypothesis: when USO has a large down-Friday, does Monday mean-revert?

Specifically motivated by 2026-04-17: WTI closed -15.7%, USO closed similarly hard
on news that Iran reopened the Strait of Hormuz. That news reversed Saturday
(Iran re-closed, attacked tankers). Question: does Monday typically un-do
large down-Friday moves when catalyst news has flipped over the weekend?

We cannot separate catalyst-flip cases from non-catalyst cases in pure price
data, so this is a conditional distribution: given Friday was down >X%, what
did Monday do? Large down-Fridays in oil are predominantly news-driven, so
this is a reasonable proxy.

Output:
  data/oil_friday_crash_study.csv    every qualifying Friday + Mon/T+1/T+2
  Printed summary by Friday-return bucket
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


SYMBOL = "USO"
START = "2006-04-10"  # USO inception 2006-04-10
END = "2026-04-18"

BUCKETS = [
    ("all down Fridays",       lambda r: r < 0),
    ("Friday <= -3%",          lambda r: r <= -0.03),
    ("Friday <= -5%",          lambda r: r <= -0.05),
    ("Friday <= -8%",          lambda r: r <= -0.08),
    ("Friday <= -10%",         lambda r: r <= -0.10),
    ("Friday <= -15% (rare)",  lambda r: r <= -0.15),
]


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def load() -> pd.DataFrame:
    df = yf.download(SYMBOL, start=START, end=END, progress=False, auto_adjust=True)
    df = _flatten(df)
    df = df[df.index.dayofweek < 5]  # weekdays only
    df["ret"] = df["Close"].pct_change()
    return df


def find_fridays(df: pd.DataFrame) -> pd.DataFrame:
    fridays = df[df.index.dayofweek == 4].copy()
    out_rows = []
    dates = list(df.index)
    for dt, row in fridays.iterrows():
        fri_close = float(row["Close"])
        fri_ret = float(row["ret"]) if pd.notna(row["ret"]) else np.nan
        if pd.isna(fri_ret):
            continue
        # Find Monday (first trading day after Friday)
        idx = dates.index(dt)
        if idx + 1 >= len(dates):
            continue
        mon = df.iloc[idx + 1]
        mon_open = float(mon["Open"])
        mon_close = float(mon["Close"])
        t1_close = float(df.iloc[idx + 2]["Close"]) if idx + 2 < len(df) else np.nan
        t2_close = float(df.iloc[idx + 3]["Close"]) if idx + 3 < len(df) else np.nan

        out_rows.append({
            "friday": dt.strftime("%Y-%m-%d"),
            "fri_ret_pct": round(fri_ret * 100, 2),
            "mon_gap_pct": round((mon_open / fri_close - 1) * 100, 2),
            "mon_close_pct": round((mon_close / fri_close - 1) * 100, 2),
            "T+1_pct": round((t1_close / fri_close - 1) * 100, 2) if pd.notna(t1_close) else np.nan,
            "T+2_pct": round((t2_close / fri_close - 1) * 100, 2) if pd.notna(t2_close) else np.nan,
        })
    return pd.DataFrame(out_rows)


def bucket_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, fn in BUCKETS:
        mask = fn(df["fri_ret_pct"] / 100)
        sub = df[mask]
        if sub.empty:
            continue
        rows.append({
            "bucket": name,
            "n": len(sub),
            "fri_mean": round(sub["fri_ret_pct"].mean(), 2),
            "gap_mean": round(sub["mon_gap_pct"].mean(), 2),
            "gap_median": round(sub["mon_gap_pct"].median(), 2),
            "gap_pos_pct": round(100 * (sub["mon_gap_pct"] > 0).mean(), 1),
            "mon_close_mean": round(sub["mon_close_pct"].mean(), 2),
            "mon_close_median": round(sub["mon_close_pct"].median(), 2),
            "mon_close_pos_pct": round(100 * (sub["mon_close_pct"] > 0).mean(), 1),
            "T+1_mean": round(sub["T+1_pct"].mean(), 2),
            "T+2_mean": round(sub["T+2_pct"].mean(), 2),
        })
    return pd.DataFrame(rows)


def main() -> None:
    df = load()
    fridays = find_fridays(df)

    out_dir = Path(__file__).resolve().parents[2] / "data" / "event_studies"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save the full Friday data
    fridays.to_csv(out_dir / "oil_friday_returns.csv", index=False)

    # Print bucket summary
    stats = bucket_stats(fridays)
    print(f"\n=== USO Monday reaction conditional on Friday return ({SYMBOL} {START} -> {END}) ===\n")
    print(stats.to_string(index=False))

    # Show actual worst Fridays for context
    worst = fridays.nsmallest(15, "fri_ret_pct")
    print(f"\n=== 15 worst USO Fridays and their Monday reactions ===\n")
    print(worst.to_string(index=False))

    # Specific comparison: what did Mondays look like after Fridays similar to 2026-04-17?
    target_fri_ret = -15.7  # Friday 2026-04-17 was -15.7% WTI close to close; USO similar
    nearby = fridays[fridays["fri_ret_pct"] <= -10]
    print(f"\n=== All Fridays <= -10% (n={len(nearby)}) — most analogous precedents ===\n")
    print(nearby.sort_values("fri_ret_pct").to_string(index=False))

    stats.to_csv(out_dir / "oil_friday_crash_buckets.csv", index=False)
    print(f"\nSaved: {out_dir / 'oil_friday_returns.csv'}")
    print(f"Saved: {out_dir / 'oil_friday_crash_buckets.csv'}")


if __name__ == "__main__":
    main()
