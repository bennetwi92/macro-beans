"""Oil + Short-Nasdaq pair event study under vol-parity sizing.

Pair:
  + 3OIL.L  (+3x daily WTI, simulated from USO daily returns)
  + QQQS.L  (-3x daily Nasdaq 100, simulated from QQQ daily returns)

Sizing: vol parity — each leg contributes equal dollar-vol risk to the
portfolio. Since both legs are 3x, the leverage cancels and the weight
ratio is simply inversely proportional to the underlying realized vols:

    w_oil   =  vol_qqq / (vol_uso + vol_qqq)
    w_nas   =  vol_uso / (vol_uso + vol_qqq)
    w_oil + w_nas = 1  (fully invested £100)

Realized vol = 20-day stdev of daily simple returns ending at Friday close.

Portfolio return at horizon h:
    R_portfolio_h = w_oil * R_3OIL_h + w_nas * R_QQQS_h

Where each LETF return is simulated path-dependently: 3OIL.L = cumprod of
(1 + 3·r_uso), QQQS.L = cumprod of (1 - 3·r_qqq). Captures daily-reset
compounding faithfully for 1-5 day holds.

Output:
  data/oil_nasdaq_pair_study.csv
  data/oil_nasdaq_pair_paths.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

EVENTS = [
    {"date": "2011-03-19", "day": "Sat", "name": "Libya intervention", "clean": True},
    {"date": "2019-09-14", "day": "Sat", "name": "Abqaiq drone attack", "clean": True},
    {"date": "2023-04-02", "day": "Sun", "name": "OPEC+ surprise cut", "clean": True},
    {"date": "2023-10-07", "day": "Sat", "name": "Hamas attack on Israel", "clean": True},
    {"date": "2023-12-23", "day": "Sat", "name": "Houthi Red Sea escalation", "clean": True},
    {"date": "2024-04-13", "day": "Sat", "name": "Iran attacks Israel", "clean": False},
    {"date": "2025-06-21", "day": "Sat", "name": "US B-2 strikes on Iran", "clean": True},
]

HORIZONS = [0, 1, 2, 3, 4, 5]
VOL_LOOKBACK = 20
OIL_LEV = 3.0
NAS_LEV = -3.0
BUDGET = 100.0  # GBP
TILT_OIL = 0.70  # conviction sizing: 70% oil leg, 30% nasdaq-short leg


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    df = _flatten(df)
    df = df[df.index.dayofweek < 5]
    df["ret"] = df["Close"].pct_change()
    return df


def simulate_letf(daily_rets: pd.Series, leverage: float) -> pd.Series:
    return (1 + leverage * daily_rets).cumprod() - 1


def analyze(uso: pd.DataFrame, qqq: pd.DataFrame, event_date: str) -> dict | None:
    event = pd.Timestamp(event_date)
    uso_pre = uso[uso.index < event]
    qqq_pre = qqq[qqq.index < event]
    uso_post = uso[uso.index > event]
    qqq_post = qqq[qqq.index > event]
    if uso_pre.empty or qqq_pre.empty or uso_post.empty or qqq_post.empty:
        return None

    fri = uso_pre.index[-1]
    assert fri.dayofweek == 4, f"expected Friday, got {fri}"

    # 20-day realized vol (daily stdev) ending Friday
    uso_vol = float(uso_pre["ret"].iloc[-VOL_LOOKBACK:].std())
    qqq_vol = float(qqq_pre["ret"].iloc[-VOL_LOOKBACK:].std())

    # Vol-parity weights (sum to 1)
    w_oil = qqq_vol / (uso_vol + qqq_vol)
    w_nas = uso_vol / (uso_vol + qqq_vol)

    # Daily return series starting from Friday close
    max_h = max(HORIZONS)
    uso_fri = float(uso_pre.iloc[-1]["Close"])
    qqq_fri = float(qqq_pre.iloc[-1]["Close"])
    uso_series = pd.concat([
        pd.Series([uso_fri], index=[fri]),
        uso_post["Close"].iloc[: max_h + 1],
    ])
    qqq_series = pd.concat([
        pd.Series([qqq_fri], index=[fri]),
        qqq_post["Close"].iloc[: max_h + 1],
    ])
    uso_rets = uso_series.pct_change().dropna()
    qqq_rets = qqq_series.pct_change().dropna()

    oil_path = simulate_letf(uso_rets, OIL_LEV)
    nas_path = simulate_letf(qqq_rets, NAS_LEV)

    out = {
        "fri_date": fri.strftime("%Y-%m-%d"),
        "uso_vol_pct": round(uso_vol * 100, 3),
        "qqq_vol_pct": round(qqq_vol * 100, 3),
        "vol_ratio_uso_qqq": round(uso_vol / qqq_vol, 2),
        "w_oil": round(w_oil, 3),
        "w_nas": round(w_nas, 3),
        "oil_alloc_gbp": round(BUDGET * w_oil, 2),
        "nas_alloc_gbp": round(BUDGET * w_nas, 2),
    }

    for h in HORIZONS:
        if h < len(oil_path) and h < len(nas_path):
            oil_r = float(oil_path.iloc[h])
            nas_r = float(nas_path.iloc[h])
            vp = w_oil * oil_r + w_nas * nas_r
            eq = 0.5 * oil_r + 0.5 * nas_r
            tilt = TILT_OIL * oil_r + (1 - TILT_OIL) * nas_r
            out[f"3OIL_T+{h}_pct"] = round(oil_r * 100, 2)
            out[f"QQQS_T+{h}_pct"] = round(nas_r * 100, 2)
            out[f"VP_T+{h}_pct"] = round(vp * 100, 2)
            out[f"EQ_T+{h}_pct"] = round(eq * 100, 2)
            out[f"TILT_T+{h}_pct"] = round(tilt * 100, 2)
            out[f"TILT_T+{h}_gbp"] = round(tilt * BUDGET, 2)
            out[f"VP_T+{h}_gbp"] = round(vp * BUDGET, 2)

    return out


def build_table() -> pd.DataFrame:
    uso = fetch("USO", "2010-01-01", "2026-04-18")
    qqq = fetch("QQQ", "2010-01-01", "2026-04-18")
    rows = []
    for ev in EVENTS:
        r = analyze(uso, qqq, ev["date"])
        if r is None:
            continue
        row = {"event_date": ev["date"], "day": ev["day"], "event": ev["name"], "clean": ev["clean"]}
        row.update(r)
        rows.append(row)
    return pd.DataFrame(rows)


def print_results(df: pd.DataFrame) -> None:
    print("\n=== Vol-parity sizing at each event ===\n")
    print(df[["event_date", "event", "clean", "uso_vol_pct", "qqq_vol_pct",
              "vol_ratio_uso_qqq", "w_oil", "w_nas",
              "oil_alloc_gbp", "nas_alloc_gbp"]].to_string(index=False))

    print("\n=== 3OIL.L leg (sim +3x USO, % return) ===\n")
    cols = ["event_date", "event"] + [f"3OIL_T+{h}_pct" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print("\n=== QQQS.L leg (sim -3x QQQ, % return) ===\n")
    cols = ["event_date", "event"] + [f"QQQS_T+{h}_pct" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print("\n=== VOL-PARITY portfolio (% of £100 budget) ===\n")
    cols = ["event_date", "event"] + [f"VP_T+{h}_pct" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print("\n=== Vol-parity portfolio in £ on a £100 stake ===\n")
    cols = ["event_date", "event"] + [f"VP_T+{h}_gbp" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print("\n=== Equal-notional portfolio for comparison (% of £100) ===\n")
    cols = ["event_date", "event"] + [f"EQ_T+{h}_pct" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print(f"\n=== OIL-TILTED portfolio ({int(TILT_OIL*100)}% oil / {int((1-TILT_OIL)*100)}% nas, % of £100) ===\n")
    cols = ["event_date", "event"] + [f"TILT_T+{h}_pct" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print(f"\n=== OIL-TILTED portfolio in £ on £100 stake ===\n")
    cols = ["event_date", "event"] + [f"TILT_T+{h}_gbp" for h in HORIZONS]
    print(df[cols].to_string(index=False))

    print("\n=== Portfolio stats — ALL events (n=%d) ===\n" % len(df))
    for label, prefix in [("Vol parity", "VP"), ("Equal notional", "EQ"),
                           (f"Oil-tilted {int(TILT_OIL*100)}/{int((1-TILT_OIL)*100)}", "TILT")]:
        stats = [f"{prefix}_T+{h}_pct" for h in HORIZONS]
        print(f"\n{label}:")
        print(df[stats].agg(["mean", "median", "min", "max"]).round(2).to_string())

    print("\n=== Stats — CLEAN events only (n=%d) ===\n" % int(df["clean"].sum()))
    clean = df[df["clean"]]
    for label, prefix in [("Vol parity", "VP"), ("Equal notional", "EQ"),
                           (f"Oil-tilted {int(TILT_OIL*100)}/{int((1-TILT_OIL)*100)}", "TILT")]:
        stats = [f"{prefix}_T+{h}_pct" for h in HORIZONS]
        print(f"\n{label}:")
        print(clean[stats].agg(["mean", "median", "min", "max"]).round(2).to_string())

    print("\n=== Win rate at each horizon (by sizing method) ===\n")
    for label, prefix in [("Vol parity", "VP"), ("Equal notional", "EQ"),
                           (f"Oil-tilted {int(TILT_OIL*100)}/{int((1-TILT_OIL)*100)}", "TILT")]:
        rates = []
        for h in HORIZONS:
            col = f"{prefix}_T+{h}_pct"
            pos = (df[col] > 0).sum()
            total = df[col].notna().sum()
            rates.append(f"T+{h}: {pos}/{total}")
        print(f"{label:30s} | " + " | ".join(rates))


def plot_paths(df: pd.DataFrame, out_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for _, row in df.iterrows():
        ys_vp = [row.get(f"VP_T+{h}_pct", np.nan) for h in HORIZONS]
        ys_eq = [row.get(f"EQ_T+{h}_pct", np.nan) for h in HORIZONS]
        label = f"{row['event_date']} {row['event']}"
        axes[0].plot(HORIZONS, ys_vp, marker="o", label=label)
        axes[1].plot(HORIZONS, ys_eq, marker="o", label=label)
    for ax, title in zip(axes, ["Vol parity", "Equal notional"]):
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlabel("Trading days after Friday close")
        ax.set_title(f"{title} portfolio path")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Portfolio return (% of £100)")
    axes[0].legend(loc="best", fontsize=8)
    fig.suptitle("3OIL.L long + QQQS.L short: pair P&L by sizing method")
    fig.tight_layout()
    fig.savefig(out_dir / "oil_nasdaq_pair_paths.png", dpi=140)
    print(f"\nChart saved -> {out_dir / 'oil_nasdaq_pair_paths.png'}")


def main() -> None:
    df = build_table()
    out_dir = Path(__file__).resolve().parents[2] / "data" / "event_studies"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "oil_nasdaq_pair_study.csv", index=False)
    print_results(df)
    plot_paths(df, out_dir)


if __name__ == "__main__":
    main()
