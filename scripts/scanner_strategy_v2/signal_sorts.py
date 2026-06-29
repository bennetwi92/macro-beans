"""Pre-backtest VALIDATION SORT for the v3 long-horizon scanner signals.

This is the §7 "basic calculation" step from ``docs/guides/scanner_signals_v3.md``
— a cross-sectional forward-return *sort*, NOT a backtest. There is no account,
no equity curve, no stops/targets, no P&L. We ask one question per signal: when
we rank the universe by the signal each month, do the forward returns sort
**monotonically** across the buckets? A monotonic gradient = the signal carries
real cross-sectional content on this universe; a flat/noisy gradient = it does
not, and §6's attenuation caveat (US single-stock results may not survive on
diversified LSE ETFs) is biting.

Method (mirrors horizon_extended.py's price-loading and conventions):

  * Same ~124-instrument LSE-ETF cache (``prices_ohlc.parquet``), split-repaired
    via build_instruments, non-leveraged names only, window 2021-07 .. 2026-06.
  * On the first trading day of each month, compute each signal for every
    instrument using ONLY data up to that bar (no look-ahead).
  * Bucket the cross-section into quintiles (terciles when the month is thin).
  * Forward return uses the repo's next-open-entry convention: enter at the
    open of bar t+1, exit at the close of bar t+1+H, for H in {21, 63}.
  * Drift-removed return = the instrument's forward return minus that month's
    equal-weight universe forward return (beta stripped the way v3 §5 does it).
  * Aggregate every (month, instrument) row by bucket across all months.

Signals (definitions from §3):
  1. 52-week-high proximity   close / trailing-252d high       (B3)
  2. 12-1 absolute momentum   close[t-21]/close[t-252]-1       (B1)
  3. Vol-normalized drop      _move_z(close, t, W=10)          (A1)

Plus two supporting checks (§7.2, §7.3):
  4. Turnover / fire-count per new trigger.
  5. Vol-normalization audit: fixed-% vs z-score fire counts per instrument.

Run:    /usr/local/bin/python3 scripts/scanner_strategy_v2/signal_sorts.py
Outputs (data/scanner_strategy_v2/):
  sort_52wk_high.csv  sort_mom_12_1.csv  sort_drop_z.csv
  turnover_firecount.csv  volnorm_audit.csv  volnorm_audit_summary.csv
  signal_sorts.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.scanner_strategy.scanner_lib import (  # noqa: E402
    sma, _move_z, MD_WINDOW, BOUNCE_THRESHOLD, MD_THRESHOLD,
)
from scripts.scanner_strategy_v2.scanner_lib import (  # noqa: E402
    build_instruments, realised_vol,
)

DATA_DIR = REPO_ROOT / "data" / "scanner_strategy_v2"
PRICES = DATA_DIR / "prices_ohlc.parquet"

START = np.datetime64("2021-07-01")
END = np.datetime64("2026-06-26")
HORIZONS = (21, 63)            # forward-return holds, trading days (1mo, 3mo)
HIGH_LOOK = 252               # 52-week (1y) high window
MOM_LOOK = 252               # 12-month momentum lookback
MOM_SKIP = 21                # skip the most recent ~month (12-1)
DROP_W = 10                  # vol-normalized drop window (A1: "5-10 day")
N_QUINTILE = 5
MIN_FOR_QUINTILE = 20        # >= this many names in the month -> quintiles
MIN_FOR_TERCILE = 6         # >= this -> terciles; fewer -> skip the month
TRADING_DAYS = 252

# Trigger thresholds from §7.2 / §7.3
PROX_TRIGGER = 0.95          # within 5% of the 1-year high
DROP_Z_TRIGGER = -2.0        # >= 2 sigma multi-day drop
Z_BOUNCE_TRIGGER = -2.0
Z_MD_TRIGGER = -2.0


# --------------------------------------------------------------------------- #
# Per-bar signal & forward-return arrays (no look-ahead)
# --------------------------------------------------------------------------- #
def rolling_max(x: np.ndarray, w: int) -> np.ndarray:
    """Trailing `w`-bar max (inclusive of the current bar); NaN until full."""
    n = len(x)
    out = np.full(n, np.nan)
    for i in range(w - 1, n):
        out[i] = x[i - w + 1:i + 1].max()
    return out


def high_proximity(close: np.ndarray) -> np.ndarray:
    """close / trailing-252d high. 1.0 at a fresh high, lower = further below."""
    hi = rolling_max(close, HIGH_LOOK)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(hi > 0, close / hi, np.nan)


def momentum_12_1(close: np.ndarray) -> np.ndarray:
    """12-1 absolute momentum: total return t-252 -> t-21 (skip recent month)."""
    n = len(close)
    out = np.full(n, np.nan)
    if n > MOM_LOOK:
        out[MOM_LOOK:] = close[MOM_LOOK - MOM_SKIP:n - MOM_SKIP] / close[0:n - MOM_LOOK] - 1.0
    return out


def move_z_array(close: np.ndarray, w: int) -> np.ndarray:
    """Vectorized port of _move_z over every bar (validated identical)."""
    n = len(close)
    out = np.full(n, np.nan)
    mv = np.full(n, np.nan)
    mv[w:] = close[w:] / close[:-w] - 1.0
    for t in range(n):
        nn = t + 1
        if nn < w + 40:
            continue
        start = max(w, nn - 252)
        moves = mv[start:nn]
        moves = moves[np.isfinite(moves)]
        if len(moves) < 20:
            continue
        m = moves.mean()
        s = moves.std()
        if not s:
            continue
        out[t] = (mv[t] - m) / s
    return out


def fwd_return_arr(open_: np.ndarray, close: np.ndarray, hold: int) -> np.ndarray:
    """Next-open-entry forward return per bar j: close[j+1+hold]/open[j+1]-1."""
    n = len(close)
    fwd = np.full(n, np.nan)
    for j in range(n):
        ei, xi = j + 1, j + 1 + hold
        if xi >= n or ei >= n or not open_[ei] > 0:
            continue
        fwd[j] = close[xi] / open_[ei] - 1.0
    return fwd


def fresh_count(cond: np.ndarray) -> int:
    """Count rising edges (False/NaN-handled-as-False -> True) of a bool array."""
    c = np.asarray(cond, dtype=bool)
    fresh = c.copy()
    fresh[1:] = c[1:] & ~c[:-1]
    return int(fresh.sum())


# --------------------------------------------------------------------------- #
# Build the long per-bar frame
# --------------------------------------------------------------------------- #
def build_long(insts: dict) -> pd.DataFrame:
    frames = []
    for inst in insts.values():
        if inst.lev:
            continue
        close, open_ = inst.close, inst.open
        if len(close) < 300:
            continue
        ma200 = sma(close, 200)
        df = pd.DataFrame({
            "date": inst.dates.values,
            "ticker": inst.ticker,
            "prox": high_proximity(close),
            "mom": momentum_12_1(close),
            "dropz": move_z_array(close, DROP_W),
            "fwd21": fwd_return_arr(open_, close, 21),
            "fwd63": fwd_return_arr(open_, close, 63),
            "close": close,
            "ma200": ma200,
        })
        df["trend_up"] = np.where(np.isfinite(df["ma200"]), df["close"] >= df["ma200"], np.nan)
        frames.append(df)
    long = pd.concat(frames, ignore_index=True)
    return long


def month_start_dates(long: pd.DataFrame) -> pd.DatetimeIndex:
    """First trading day of each calendar month present in the universe window."""
    d = pd.DatetimeIndex(sorted(long["date"].unique()))
    d = d[(d >= START) & (d <= END)]
    first = pd.Series(d).groupby([d.year, d.month]).min()
    return pd.DatetimeIndex(sorted(first.values))


# --------------------------------------------------------------------------- #
# The cross-sectional sort
# --------------------------------------------------------------------------- #
def sort_signal(mdf: pd.DataFrame, sigcol: str) -> pd.DataFrame:
    """Quintile (or tercile) the universe each month by `sigcol`; aggregate
    forward returns per bucket across all months. Buckets numbered 1..k with
    1 = LOWEST signal value, k = highest. Adds drift-removed forward returns
    (instrument fwd minus that month's equal-weight universe fwd).
    """
    rows = []
    months_used = 0
    for d, g in mdf.groupby("date"):
        g = g.dropna(subset=[sigcol]).copy()
        nm = len(g)
        if nm >= MIN_FOR_QUINTILE:
            nb = N_QUINTILE
        elif nm >= MIN_FOR_TERCILE:
            nb = 3
        else:
            continue
        # per-month universe drift baseline (equal-weight), per horizon
        for h in HORIZONS:
            col = f"fwd{h}"
            base = g[col].dropna()
            g[f"dr{h}"] = g[col] - (base.mean() if len(base) else np.nan)
        try:
            q = pd.qcut(g[sigcol], nb, labels=False, duplicates="drop")
        except ValueError:
            continue
        if q.isna().all():
            continue
        # remap surviving bin codes to a uniform 1..N_QUINTILE scale so months
        # that fell back to terciles still align (low->1, high->5).
        codes = np.sort(q.dropna().unique())
        kk = len(codes)
        if kk < 2:
            continue
        remap = {c: int(round(1 + i * (N_QUINTILE - 1) / (kk - 1))) for i, c in enumerate(codes)}
        g["bucket"] = q.map(remap)
        g = g.dropna(subset=["bucket"])
        g["bucket"] = g["bucket"].astype(int)
        rows.append(g)
        months_used += 1
    allrows = pd.concat(rows, ignore_index=True)

    recs = []
    for b, gb in allrows.groupby("bucket"):
        rec = {"bucket": int(b), "n": int(len(gb))}
        for h in HORIZONS:
            f = gb[f"fwd{h}"].dropna()
            dr = gb[f"dr{h}"].dropna()
            rec[f"mean_fwd{h}%"] = round(f.mean() * 100, 3) if len(f) else np.nan
            rec[f"med_fwd{h}%"] = round(f.median() * 100, 3) if len(f) else np.nan
            rec[f"win{h}%"] = round((f > 0).mean() * 100, 1) if len(f) else np.nan
            rec[f"dr_fwd{h}%"] = round(dr.mean() * 100, 3) if len(dr) else np.nan
        recs.append(rec)
    out = pd.DataFrame(recs).sort_values("bucket").reset_index(drop=True)
    out.attrs["months_used"] = months_used
    return out


def monotonic_gradient(df: pd.DataFrame, col: str) -> tuple[float, str]:
    """Top-minus-bottom spread and a monotonicity verdict for a bucket column."""
    v = df.sort_values("bucket")[col].to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 3:
        return np.nan, "n/a"
    spread = v[-1] - v[0]
    diffs = np.diff(v)
    up = np.all(diffs >= -0.05)      # allow tiny non-monotone wiggle
    down = np.all(diffs <= 0.05)
    if up and not down:
        verdict = "monotone up"
    elif down and not up:
        verdict = "monotone down"
    else:
        # count sign agreement with the overall direction
        sign = np.sign(spread)
        agree = np.mean(np.sign(diffs) == sign) if sign else 0
        verdict = f"non-monotone ({agree*100:.0f}% steps in-direction)"
    return round(spread, 3), verdict


# --------------------------------------------------------------------------- #
# Check 4: turnover / fire-count per new trigger
# --------------------------------------------------------------------------- #
def turnover(insts: dict) -> pd.DataFrame:
    detectors = {
        "52wk_high>=0.95": 0,
        "12-1_mom>0 & >200MA": 0,
        f"drop_z(W{DROP_W})<=-2": 0,
    }
    inst_years = 0.0
    n_inst = 0
    for inst in insts.values():
        if inst.lev:
            continue
        close, open_ = inst.close, inst.open
        if len(close) < 300:
            continue
        d = inst.dates.values
        inwin = (d >= START) & (d <= END)
        if inwin.sum() < 30:
            continue
        n_inst += 1
        inst_years += inwin.sum() / TRADING_DAYS

        prox = high_proximity(close)
        mom = momentum_12_1(close)
        ma200 = sma(close, 200)
        dz = move_z_array(close, DROP_W)
        up = np.isfinite(ma200) & (close >= ma200)

        t_high = inwin & (prox >= PROX_TRIGGER)
        t_mom = inwin & (mom > 0) & up
        t_drop = inwin & (dz <= DROP_Z_TRIGGER)
        detectors["52wk_high>=0.95"] += fresh_count(t_high)
        detectors["12-1_mom>0 & >200MA"] += fresh_count(t_mom)
        detectors[f"drop_z(W{DROP_W})<=-2"] += fresh_count(t_drop)

    recs = []
    for name, fires in detectors.items():
        recs.append({
            "detector": name,
            "n_fires": fires,
            "n_instruments": n_inst,
            "instrument_years": round(inst_years, 1),
            "fires_per_inst_per_yr": round(fires / inst_years, 2) if inst_years else np.nan,
            "fires_per_yr_universe": round(fires / (inst_years / n_inst), 1) if n_inst else np.nan,
        })
    return pd.DataFrame(recs)


# --------------------------------------------------------------------------- #
# Check 5: vol-normalization audit (fixed-% vs z fire counts per instrument)
# --------------------------------------------------------------------------- #
def vol_audit(insts: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    recs = []
    for inst in insts.values():
        if inst.lev:
            continue
        close = inst.close
        if len(close) < 300:
            continue
        d = inst.dates.values
        inwin = (d >= START) & (d <= END)
        if inwin.sum() < 60:
            continue
        n = len(close)

        # daily and 5-day moves
        day = np.full(n, np.nan)
        day[1:] = close[1:] / close[:-1] - 1.0
        md = np.full(n, np.nan)
        if n > MD_WINDOW:
            md[MD_WINDOW:] = close[MD_WINDOW:] / close[:-MD_WINDOW] - 1.0

        # FIXED-% triggers
        fix_bounce = inwin & (day <= -BOUNCE_THRESHOLD / 100.0)
        fix_md = inwin & (md <= -MD_THRESHOLD / 100.0)
        # Z-score equivalents (same windows, -2 sigma)
        z1 = move_z_array(close, 1)
        z5 = move_z_array(close, MD_WINDOW)
        z_bounce = inwin & (z1 <= Z_BOUNCE_TRIGGER)
        z_md = inwin & (z5 <= Z_MD_TRIGGER)

        vol = realised_vol(close)
        ann_vol = np.nanmedian(vol[inwin]) * np.sqrt(TRADING_DAYS) * 100  # %, annualized

        recs.append({
            "ticker": inst.ticker,
            "ann_vol%": round(float(ann_vol), 1),
            "fix_bounce": fresh_count(fix_bounce),
            "z_bounce": fresh_count(z_bounce),
            "fix_md8": fresh_count(fix_md),
            "z_md": fresh_count(z_md),
        })
    df = pd.DataFrame(recs).sort_values("ann_vol%").reset_index(drop=True)

    # Summary: split universe at median vol; high/low fire ratios.
    med = df["ann_vol%"].median()
    lo = df[df["ann_vol%"] <= med]
    hi = df[df["ann_vol%"] > med]
    summ = []
    for col in ("fix_bounce", "z_bounce", "fix_md8", "z_md"):
        lo_m = lo[col].mean()
        hi_m = hi[col].mean()
        summ.append({
            "trigger": col,
            "low_vol_mean_fires": round(lo_m, 1),
            "high_vol_mean_fires": round(hi_m, 1),
            "high/low_ratio": round(hi_m / lo_m, 2) if lo_m else np.inf,
            "corr_vol_fires": round(float(df["ann_vol%"].corr(df[col])), 2),
        })
    return df, pd.DataFrame(summ)


# --------------------------------------------------------------------------- #
def plot_sorts(sorts: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    titles = {
        "52wk_high": "52-week-high proximity (B3)",
        "mom_12_1": "12-1 absolute momentum (B1)",
        "drop_z": f"Vol-normalized drop z (A1, W={DROP_W})",
    }
    notes = {
        "52wk_high": "Q5 = nearest 1y high",
        "mom_12_1": "Q5 = strongest momentum",
        "drop_z": "Q1 = biggest vol-adj dip",
    }
    for ax, (key, df) in zip(axes, sorts.items()):
        b = df["bucket"]
        ax.plot(b, df["mean_fwd21%"], "o-", label="+21d", color="#1f77b4")
        ax.plot(b, df["mean_fwd63%"], "s-", label="+63d", color="#d62728")
        ax.axhline(0, color="grey", lw=0.7)
        ax.set_title(titles[key], fontsize=10)
        ax.set_xlabel(f"bucket (1=low .. {N_QUINTILE}=high)\n{notes[key]}", fontsize=8)
        ax.set_ylabel("mean forward return %")
        ax.set_xticks(list(b))
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("v3 signal validation sorts — monthly cross-sectional, non-lev LSE ETFs, 2021-07..2026-06",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=110)
    print(f"  wrote {path}")


def main() -> None:
    if not PRICES.exists():
        sys.exit(f"missing {PRICES} -- run fetch_prices.py first")
    prices = pd.read_parquet(PRICES)
    insts = build_instruments(prices)
    n_nonlev = sum(1 for i in insts.values() if not i.lev and len(i.close) >= 300)
    print(f"{len(insts)} instruments ({n_nonlev} non-lev usable); window "
          f"{str(START)[:10]}..{str(END)[:10]}; horizons {HORIZONS}\n")

    long = build_long(insts)
    months = month_start_dates(long)
    mdf = long[long["date"].isin(months)].copy()
    # month-cross-section sizes (after requiring a finite signal handled per-sort)
    sizes = mdf.dropna(subset=["fwd21"]).groupby("date")["ticker"].count()
    print(f"{len(months)} monthly cross-sections "
          f"({months[0].date()}..{months[-1].date()}); "
          f"per-month names: min {int(sizes.min())}, median {int(sizes.median())}, "
          f"max {int(sizes.max())}\n")

    sig_map = [
        ("52wk_high", "prox", "sort_52wk_high.csv", "52-week-high proximity (B3)"),
        ("mom_12_1", "mom", "sort_mom_12_1.csv", "12-1 absolute momentum (B1)"),
        ("drop_z", "dropz", "sort_drop_z.csv", f"Vol-normalized drop z, W={DROP_W} (A1)"),
    ]
    sorts = {}
    for key, col, fname, label in sig_map:
        out = sort_signal(mdf, col)
        out.to_csv(DATA_DIR / fname, index=False)
        sorts[key] = out
        sp21, v21 = monotonic_gradient(out, "mean_fwd21%")
        sp63, v63 = monotonic_gradient(out, "mean_fwd63%")
        dsp21, _ = monotonic_gradient(out, "dr_fwd21%")
        dsp63, _ = monotonic_gradient(out, "dr_fwd63%")
        print(f"=== {label} ===  ({out.attrs['months_used']} months)")
        print(out.to_string(index=False))
        print(f"  Q{N_QUINTILE}-Q1 spread:  21d {sp21:+.2f}%  [{v21}] | "
              f"63d {sp63:+.2f}%  [{v63}]")
        print(f"  drift-removed spread: 21d {dsp21:+.2f}%  | 63d {dsp63:+.2f}%\n")

    print("=== Turnover / fire-count (Check 4) ===")
    tov = turnover(insts)
    tov.to_csv(DATA_DIR / "turnover_firecount.csv", index=False)
    print(tov.to_string(index=False), "\n")

    print("=== Vol-normalization audit (Check 5) ===")
    audit, summ = vol_audit(insts)
    audit.to_csv(DATA_DIR / "volnorm_audit.csv", index=False)
    summ.to_csv(DATA_DIR / "volnorm_audit_summary.csv", index=False)
    print(summ.to_string(index=False))
    print(f"  (per-instrument table -> volnorm_audit.csv, {len(audit)} names)\n")

    plot_sorts(sorts, DATA_DIR / "signal_sorts.png")
    print("\nDone.")


if __name__ == "__main__":
    main()
