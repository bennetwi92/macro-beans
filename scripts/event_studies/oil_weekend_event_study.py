"""Oil weekend event study.

How does USO react at Monday open and through the following week when major
oil-sensitive geopolitical events break on a Saturday?

Motivated by Iran's 2026-04-18 (Saturday) re-closure of the Strait of Hormuz
with reports of tanker attacks. Markets reopen Monday 2026-04-20.

Events analyzed (all Saturdays, all within USO's trading history since 2006-04):
  - 2011-03-19  Libya intervention (Operation Odyssey Dawn)
  - 2019-09-14  Abqaiq drone attack on Saudi Aramco (cleanest supply-shock analog)
  - 2023-10-07  Hamas attack on Israel
  - 2024-04-13  Iran drone/missile barrage on Israel (telegraphed, faded)

Output:
  data/oil_weekend_event_study.csv   per-event returns
  data/oil_weekend_event_study.png   chart of USO path Monday -> T+5
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

EVENTS = [
    {
        "date": "2011-03-19", "day": "Sat",
        "name": "Libya intervention",
        "detail": "Coalition airstrikes begin against Gaddafi",
        "clean": True,
    },
    {
        "date": "2019-09-14", "day": "Sat",
        "name": "Abqaiq drone attack",
        "detail": "5.7 mbpd Saudi production knocked offline — cleanest supply shock",
        "clean": True,
    },
    {
        "date": "2023-04-02", "day": "Sun",
        "name": "OPEC+ surprise cut",
        "detail": "1.16 mbpd voluntary production cut announced Sunday",
        "clean": True,
    },
    {
        "date": "2023-10-07", "day": "Sat",
        "name": "Hamas attack on Israel",
        "detail": "Surprise attack triggers ME risk premium",
        "clean": True,
    },
    {
        "date": "2023-12-23", "day": "Sat",
        "name": "Houthi Red Sea escalation",
        "detail": "Tanker strikes + BP pauses Red Sea transits",
        "clean": True,
    },
    {
        "date": "2024-04-13", "day": "Sat",
        "name": "Iran attacks Israel",
        "detail": "Telegraphed Friday, 99% intercepted — CONTAMINATED (pre-positioned)",
        "clean": False,
    },
    {
        "date": "2025-06-21", "day": "Sat",
        "name": "US B-2 strikes on Iran",
        "detail": "Operation Midnight Hammer — Fordow/Natanz/Isfahan — CLOSEST ANALOG",
        "clean": True,
    },
]

HORIZONS = [0, 1, 2, 3, 4, 5]  # Monday close is H=0; T+1..T+5 are subsequent closes


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch_window(symbol: str, event_date: str, pad_days: int = 20) -> pd.DataFrame:
    event = pd.Timestamp(event_date)
    start = event - pd.Timedelta(days=pad_days)
    end = event + pd.Timedelta(days=pad_days)
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    return _flatten(df)


def simulate_letf_cumulative(daily_returns: pd.Series, leverage: float) -> pd.Series:
    """Path-dependent daily-reset LETF approximation.

    Models UCO (leverage=+2) / SDS (leverage=-2) by applying the leverage to
    each day's underlying return and compounding. Ignores borrow/financing
    drag (~5bps/day) which is immaterial at T+1..T+5 horizons.
    """
    levered = leverage * daily_returns
    return (1 + levered).cumprod() - 1


def analyze(symbol: str, event_date: str) -> dict:
    df = fetch_window(symbol, event_date)
    event = pd.Timestamp(event_date)

    # Only consider weekday bars strictly before the event and after
    weekdays = df[df.index.dayofweek < 5]
    pre = weekdays[weekdays.index < event]
    post = weekdays[weekdays.index > event]
    if pre.empty or post.empty:
        return {}

    friday = pre.iloc[-1]
    assert friday.name.dayofweek == 4, f"expected Friday, got {friday.name}"
    fri_close = float(friday["Close"])

    monday = post.iloc[0]
    mon_open = float(monday["Open"])
    mon_high = float(monday["High"])
    mon_low = float(monday["Low"])
    mon_close = float(monday["Close"])

    out = {
        "fri_date": friday.name.strftime("%Y-%m-%d"),
        "fri_close": round(fri_close, 2),
        "mon_date": monday.name.strftime("%Y-%m-%d"),
        "mon_open": round(mon_open, 2),
        "gap_pct": round((mon_open / fri_close - 1) * 100, 2),
        "mon_high_pct": round((mon_high / fri_close - 1) * 100, 2),
        "mon_low_pct": round((mon_low / fri_close - 1) * 100, 2),
    }

    # Build daily-return series from Friday close through T+5.
    # Day 0 return (Mon): mon_close / fri_close - 1
    # Day n return: close[n] / close[n-1] - 1
    closes = pd.concat([pd.Series([fri_close], index=[friday.name]),
                        post["Close"].iloc[: max(HORIZONS) + 1]])
    daily_rets = closes.pct_change().dropna()

    for h in HORIZONS:
        if h >= len(post):
            out[f"T+{h}_pct"] = np.nan
            continue
        close = float(post.iloc[h]["Close"])
        out[f"T+{h}_pct"] = round((close / fri_close - 1) * 100, 2)

    # Gap-fade: raw fade in percentage points (pp), meaningful even near zero
    out["gap_fade_pp"] = round(out["T+0_pct"] - out["gap_pct"], 2)

    return {"_daily_rets": daily_rets, **out}


def build_table() -> pd.DataFrame:
    rows = []
    for ev in EVENTS:
        uso = analyze("USO", ev["date"])
        spy = analyze("SPY", ev["date"])
        if not uso:
            continue

        # Path-dependent LETF simulation (daily-reset 2x and -2x) — this is
        # what a real UCO / SDS position earns across the event window, which
        # differs from 2x the cumulative return when sessions are volatile.
        uco_cum = simulate_letf_cumulative(uso["_daily_rets"], +2.0)
        sds_cum = simulate_letf_cumulative(spy["_daily_rets"], -2.0)

        row = {
            "event_date": ev["date"], "day": ev["day"], "event": ev["name"],
            "clean": ev["clean"], "detail": ev["detail"],
        }
        row.update({f"USO_{k}": v for k, v in uso.items() if not k.startswith("_")})
        row.update({f"SPY_{k}": v for k, v in spy.items() if not k.startswith("_")})

        for h in HORIZONS:
            if h < len(uco_cum):
                row[f"UCO_sim_T+{h}_pct"] = round(uco_cum.iloc[h] * 100, 2)
            if h < len(sds_cum):
                row[f"SDS_sim_T+{h}_pct"] = round(sds_cum.iloc[h] * 100, 2)
            # Pair: equal-notional long-UCO + short-SPX-via-SDS
            if h < len(uco_cum) and h < len(sds_cum):
                row[f"PAIR_T+{h}_pct"] = round(
                    (uco_cum.iloc[h] + sds_cum.iloc[h]) * 100, 2
                )
        rows.append(row)
    return pd.DataFrame(rows)


def print_summary(df: pd.DataFrame) -> None:
    print("\n=== USO reaction to weekend oil shocks (n=%d) ===\n" % len(df))
    cols = [
        "event_date", "day", "event", "clean",
        "USO_gap_pct", "USO_mon_high_pct", "USO_T+0_pct",
        "USO_T+1_pct", "USO_T+2_pct", "USO_T+3_pct", "USO_T+4_pct", "USO_T+5_pct",
        "USO_gap_fade_pp",
    ]
    print(df[cols].to_string(index=False))

    print("\n=== SPY reaction ===\n")
    cols = [
        "event_date", "event",
        "SPY_gap_pct", "SPY_T+0_pct", "SPY_T+1_pct", "SPY_T+2_pct",
        "SPY_T+3_pct", "SPY_T+5_pct",
    ]
    print(df[cols].to_string(index=False))

    print("\n=== UCO (sim, daily-reset 2x long USO) ===\n")
    cols = ["event_date", "event"] + [
        f"UCO_sim_T+{h}_pct" for h in HORIZONS if f"UCO_sim_T+{h}_pct" in df.columns
    ]
    print(df[cols].to_string(index=False))

    print("\n=== Pair (UCO long + SDS short, equal notional, path-dependent) ===\n")
    cols = ["event_date", "event"] + [
        f"PAIR_T+{h}_pct" for h in HORIZONS if f"PAIR_T+{h}_pct" in df.columns
    ]
    print(df[cols].to_string(index=False))

    print("\n=== Case-study stats (descriptive only — NOT a statistical base rate) ===\n")
    stats_cols = [
        "USO_gap_pct", "USO_T+0_pct", "USO_T+1_pct", "USO_T+2_pct",
        "USO_T+3_pct", "USO_T+5_pct",
    ]
    print(df[stats_cols].agg(["mean", "median", "min", "max"]).round(2).to_string())

    # "Clean" subset excludes contaminated / pre-positioned events
    clean_df = df[df["clean"]]
    print("\n=== Same stats on CLEAN events only (n=%d) ===\n" % len(clean_df))
    print(clean_df[stats_cols].agg(["mean", "median", "min", "max"]).round(2).to_string())


def plot_paths(df: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    for _, row in df.iterrows():
        xs = [-0.5] + HORIZONS  # -0.5 = Monday open (gap), 0 = Mon close, 1..5 = T+N close
        ys = [row["USO_gap_pct"]] + [row.get(f"USO_T+{h}_pct") for h in HORIZONS]
        ax.plot(xs, ys, marker="o", label=f"{row['event_date']} {row['event']}")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Session (-0.5 = Monday open gap, 0 = Mon close, 1..5 = T+N close)")
    ax.set_ylabel("USO return from Friday close (%)")
    ax.set_title("USO path after Saturday oil-shock events")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"\nChart saved -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = repo_root / "data" / "event_studies"
    data_dir.mkdir(parents=True, exist_ok=True)

    df = build_table()

    csv_path = data_dir / "oil_weekend_event_study.csv"
    df.to_csv(csv_path, index=False)
    print(f"Data saved   -> {csv_path}")

    print_summary(df)
    plot_paths(df, data_dir / "oil_weekend_event_study.png")


if __name__ == "__main__":
    main()
