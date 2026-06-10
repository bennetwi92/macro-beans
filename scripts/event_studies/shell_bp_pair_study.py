"""Shell vs BP — the London oil-supermajor pair, last-year relationship study.

Both Shell (SHEL.L) and BP (BP.L) are London-listed integrated oil majors whose
share prices are dominated by the same factor: the crude oil price. Hedging one
against the other strips out the common oil move and leaves the *relative* story
— company-specific strategy, balance sheet, trading results and corporate-action
news. This script characterises that relative relationship over the last ~year
and isolates the biggest swings so they can be mapped to news catalysts.

What it measures
----------------
  * raw correlation / beta of the two names (how tightly they co-move)
  * a price *ratio* SHEL/BP (the simplest "relationship" line a trader watches)
  * a rolling-beta, beta-hedged spread:  r_spread = r_SHEL - beta * r_BP
    beta[t] = cov(r_SHEL, r_BP over t-LOOKBACK..t-1) / var(r_BP over same)
    (1-day lag, no look-ahead) — this is the long-Shell / short-BP pair return
    with the oil beta removed, i.e. pure relative performance.
  * the cumulative spread equity curve (long Shell / short BP, oil-neutral)
  * the largest single-day relative moves and the largest multi-week drifts,
    printed with dates so the swings can be attributed to catalysts.

Outputs
-------
  data/event_studies/shell_bp_pair_daily.csv      full daily series
  data/event_studies/shell_bp_pair_extremes.csv   top single-day relative moves
  data/event_studies/shell_bp_pair_swings.csv      largest cumulative drift legs
  data/event_studies/shell_bp_pair.png             ratio + spread + rolling stats
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import yfinance as yf

LOOKBACK = 60          # trading days for rolling beta / correlation
TOP_N = 15             # extreme single-day relative moves to list each side
# Pull a little over a year so the rolling beta is warm at the start of the
# one-year analysis window.
FETCH_PERIOD = "18mo"
ANALYSIS_DAYS = 365    # calendar days defining the "last year" window


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df


def fetch_closes() -> pd.DataFrame:
    raw = yf.download(["SHEL.L", "BP.L"], period=FETCH_PERIOD,
                      progress=False, auto_adjust=True)
    closes = raw["Close"].dropna().copy()
    closes = closes.rename(columns={"SHEL.L": "shel", "BP.L": "bp"})
    return closes[["shel", "bp"]]


def build(closes: pd.DataFrame) -> pd.DataFrame:
    rets = closes.pct_change()
    cov = rets["shel"].rolling(LOOKBACK).cov(rets["bp"])
    var = rets["bp"].rolling(LOOKBACK).var()
    beta = (cov / var).shift(1)                       # yesterday's beta for today
    corr = rets["shel"].rolling(LOOKBACK).corr(rets["bp"])
    r_spread = rets["shel"] - beta * rets["bp"]       # oil-neutral long-SHEL/short-BP

    out = pd.DataFrame({
        "shel": closes["shel"],
        "bp": closes["bp"],
        "ratio": closes["shel"] / closes["bp"],
        "r_shel": rets["shel"],
        "r_bp": rets["bp"],
        "beta": beta,
        "corr60": corr,
        "r_spread": r_spread,
    })
    return out


def restrict_to_year(df: pd.DataFrame) -> pd.DataFrame:
    cutoff = df.index[-1] - pd.Timedelta(days=ANALYSIS_DAYS)
    win = df[df.index >= cutoff].copy()
    # Re-base the spread equity curve to 1.0 at the start of the window.
    win = win.dropna(subset=["r_spread"])
    win["spread_equity"] = (1 + win["r_spread"]).cumprod()
    win["ratio_norm"] = win["ratio"] / win["ratio"].iloc[0]
    return win


def summarise(df: pd.DataFrame) -> None:
    print(f"\nAnalysis window: {df.index[0].date()} -> {df.index[-1].date()}  "
          f"(n={len(df)} trading days)")
    print(f"SHEL.L: {df['shel'].iloc[0]:.0f}p -> {df['shel'].iloc[-1]:.0f}p  "
          f"({df['shel'].iloc[-1]/df['shel'].iloc[0]-1:+.1%})")
    print(f"BP.L:   {df['bp'].iloc[0]:.0f}p -> {df['bp'].iloc[-1]:.0f}p  "
          f"({df['bp'].iloc[-1]/df['bp'].iloc[0]-1:+.1%})")
    print(f"Ratio SHEL/BP: {df['ratio'].iloc[0]:.2f} -> {df['ratio'].iloc[-1]:.2f}  "
          f"(min {df['ratio'].min():.2f} on {df['ratio'].idxmin().date()}, "
          f"max {df['ratio'].max():.2f} on {df['ratio'].idxmax().date()})")
    print(f"Rolling 60d corr: mean={df['corr60'].mean():.2f}  "
          f"min={df['corr60'].min():.2f} ({df['corr60'].idxmin().date()})  "
          f"max={df['corr60'].max():.2f}")
    print(f"Rolling 60d beta (SHEL on BP): mean={df['beta'].mean():.2f}  "
          f"min={df['beta'].min():.2f}  max={df['beta'].max():.2f}")

    ann_mean = df["r_spread"].mean() * 252 * 100
    ann_vol = df["r_spread"].std() * np.sqrt(252) * 100
    sharpe = ann_mean / ann_vol if ann_vol else np.nan
    tot = df["spread_equity"].iloc[-1] - 1
    print(f"\nOil-neutral spread (long SHEL / short BP, beta-hedged):")
    print(f"  total return over window = {tot:+.1%}")
    print(f"  ann mean={ann_mean:+.1f}%  ann vol={ann_vol:.1f}%  Sharpe={sharpe:.2f}")
    print(f"  best day {df['r_spread'].max()*100:+.2f}% ({df['r_spread'].idxmax().date()})  "
          f"worst day {df['r_spread'].min()*100:+.2f}% ({df['r_spread'].idxmin().date()})")


def extreme_days(df: pd.DataFrame, n: int) -> pd.DataFrame:
    cols = ["r_spread", "r_shel", "r_bp", "beta", "shel", "bp", "ratio"]
    winners = df.nlargest(n, "r_spread")[cols].copy()
    losers = df.nsmallest(n, "r_spread")[cols].copy()
    winners["side"] = "SHEL_outperf"
    losers["side"] = "BP_outperf"
    table = pd.concat([winners, losers])
    table["r_spread_pct"] = (table["r_spread"] * 100).round(2)
    table["r_shel_pct"] = (table["r_shel"] * 100).round(2)
    table["r_bp_pct"] = (table["r_bp"] * 100).round(2)
    table["beta"] = table["beta"].round(2)
    return table[["side", "r_spread_pct", "r_shel_pct", "r_bp_pct", "beta",
                  "shel", "bp", "ratio"]].sort_index()


def swing_legs(df: pd.DataFrame, col: str = "spread_equity",
               min_move: float = 0.04) -> pd.DataFrame:
    """Decompose `col` into monotone-ish drift legs by detecting swing pivots
    (zig-zag) of at least `min_move` cumulative size. Returns the leg
    start/end with the relative move over each leg."""
    eq = df[col].values
    idx = df.index
    pivots = [0]
    direction = 0          # +1 rising, -1 falling, 0 undecided
    ext_i, ext_v = 0, eq[0]    # running extreme in the active direction
    for i in range(1, len(eq)):
        v = eq[i]
        if direction == 0:
            # Wait for the first move that clears the threshold from the start
            # to establish an initial direction; track the farther tentative
            # extreme in the meantime.
            if v >= eq[0] * (1 + min_move):
                direction, ext_i, ext_v = +1, i, v
            elif v <= eq[0] * (1 - min_move):
                direction, ext_i, ext_v = -1, i, v
            elif abs(v - eq[0]) > abs(ext_v - eq[0]):
                ext_i, ext_v = i, v
        elif direction == +1:
            if v > ext_v:
                ext_i, ext_v = i, v
            elif v <= ext_v * (1 - min_move):       # confirmed swing high
                pivots.append(ext_i)
                direction, ext_i, ext_v = -1, i, v
        else:  # direction == -1
            if v < ext_v:
                ext_i, ext_v = i, v
            elif v >= ext_v * (1 + min_move):        # confirmed swing low
                pivots.append(ext_i)
                direction, ext_i, ext_v = +1, i, v
    pivots.append(len(eq) - 1)
    pivots = sorted(set(pivots))

    rows = []
    for a, b in zip(pivots[:-1], pivots[1:]):
        move = eq[b] / eq[a] - 1
        shel_leg = df["shel"].iloc[b] / df["shel"].iloc[a] - 1
        bp_leg = df["bp"].iloc[b] / df["bp"].iloc[a] - 1
        rows.append({
            "start": idx[a].date(),
            "end": idx[b].date(),
            "days": (idx[b] - idx[a]).days,
            "move_pct": round(move * 100, 2),
            "shel_leg_pct": round(shel_leg * 100, 1),
            "bp_leg_pct": round(bp_leg * 100, 1),
            "winner": "SHEL" if move > 0 else "BP",
            "shel_start": round(df["shel"].iloc[a]),
            "shel_end": round(df["shel"].iloc[b]),
            "bp_start": round(df["bp"].iloc[a]),
            "bp_end": round(df["bp"].iloc[b]),
        })
    return pd.DataFrame(rows)


def plot(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 11), sharex=True)

    # 1) normalised prices
    (df["shel"] / df["shel"].iloc[0]).plot(ax=axes[0], color="C2", label="Shell (SHEL.L)")
    (df["bp"] / df["bp"].iloc[0]).plot(ax=axes[0], color="C1", label="BP (BP.L)")
    axes[0].set_title("Shell vs BP — normalised price (start = 1.0)")
    axes[0].set_ylabel("Normalised price")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=0.3)

    # 2) oil-neutral spread equity (long Shell / short BP)
    axes[1].plot(df.index, df["spread_equity"], color="C0",
                 label="Long Shell / Short BP (beta-hedged, oil-neutral)")
    axes[1].axhline(1.0, color="black", lw=0.8)
    axes[1].set_title("Relative performance — oil stripped out (rolling 60d beta hedge)")
    axes[1].set_ylabel("Spread equity ($1 start)")
    axes[1].legend(loc="best")
    axes[1].grid(alpha=0.3)

    # 3) rolling beta & correlation
    ax3 = axes[2]
    ax3.plot(df.index, df["corr60"], color="C3", label="60d correlation (left)")
    ax3.set_ylabel("Correlation", color="C3")
    ax3.tick_params(axis="y", labelcolor="C3")
    ax3.grid(alpha=0.3)
    ax3b = ax3.twinx()
    ax3b.plot(df.index, df["beta"], color="C4", alpha=0.8, label="60d beta SHEL~BP (right)")
    ax3b.set_ylabel("Beta", color="C4")
    ax3b.tick_params(axis="y", labelcolor="C4")
    ax3.set_title("How tightly the pair co-moves (rolling 60d)")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"Chart saved -> {out_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "data" / "event_studies"
    out_dir.mkdir(parents=True, exist_ok=True)

    closes = fetch_closes()
    full = build(closes)
    win = restrict_to_year(full)

    summarise(win)

    daily_path = out_dir / "shell_bp_pair_daily.csv"
    win.round(6).to_csv(daily_path)
    print(f"\nDaily series saved -> {daily_path}")

    ext = extreme_days(win, TOP_N)
    ext_path = out_dir / "shell_bp_pair_extremes.csv"
    ext.round(4).to_csv(ext_path)
    print(f"Extreme single-day relative moves saved -> {ext_path}")
    print("\nLargest single-day relative moves (spread = SHEL - beta*BP):")
    print(ext.to_string())

    # Swings on the price ratio SHEL/BP — the "relationship" line a trader
    # actually watches. This captures BP's idiosyncratic re-rating, which the
    # beta-hedged spread (beta~0.6) deliberately damps out.
    ratio_swings = swing_legs(win, col="ratio", min_move=0.045)
    rsw_path = out_dir / "shell_bp_pair_swings.csv"
    ratio_swings.to_csv(rsw_path, index=False)
    print(f"\nMajor swing legs (SHEL/BP ratio) saved -> {rsw_path}")
    print("\nMajor swing legs in the SHEL/BP price ratio (>=4.5% zig-zag):")
    print(ratio_swings.to_string(index=False))

    # Also report the oil-neutral spread legs for completeness.
    spread_swings = swing_legs(win, col="spread_equity", min_move=0.05)
    print("\nMajor swing legs in the oil-neutral beta-hedged spread (>=5% zig-zag):")
    print(spread_swings.to_string(index=False))

    plot(win, out_dir / "shell_bp_pair.png")


if __name__ == "__main__":
    main()
