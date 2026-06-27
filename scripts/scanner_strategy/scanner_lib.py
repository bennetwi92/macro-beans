"""Offline port of the Macro Beans Scanner (web/v2/js/scanner.js).

This reproduces, in Python, exactly what the Scanner shows so a backtest can
replay it as of any past date with no look-ahead. The maths mirrors
``web/js/strategy-engine.js`` (the tested engine the live site imports) and the
row construction in ``web/v2/js/scanner.js``:

  * six long-only setups (bounce / red streak / multi-day drop / breakout high /
    MA-cross-up / tight range), each firing on a bar's close;
  * entry at the NEXT bar's open (you can't buy the close you detect on);
  * a per-setup track record over a trailing window (default 5y), optionally
    conditioned on the current 200-day trend ("same trend");
  * EDGE = the setup's average forward return minus the instrument's own
    next-open baseline over the same window/horizon/regime (drift removed);
  * MAE = average worst close-to-close drawdown during the hold;
  * the ranking score = per-day edge shrunk toward zero by sample size.

The single public entry point is :func:`scan_history`, which returns every
"fresh" Scanner row (a setup that flipped true on that bar) across an
instrument's history, each stamped with the stats the Scanner would have shown
*that day*. The backtest consumes those rows.

Parameters are fixed to the live Scanner's values so the numbers agree.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---- fixed Scanner parameters (mirror web/v2/js/scanner.js) ----
BOUNCE_THRESHOLD = 2.0      # single-day drop %, "Buy the Bounce"
STREAK_N = 3                # consecutive red closes, "Red Streak"
MD_THRESHOLD = 8.0          # trailing-window drop %, "Multi-Day Drop"
MD_WINDOW = 5
BREAK_LOOK = 20             # n-day high, "Breakout High"
CROSS_PERIOD = 200          # "MA Cross Up"
RANGE_BAND = 3.0            # +-band% half-width, "Tight Range"
RANGE_WINDOW = 10
SHRINK_K = 20               # small-sample shrinkage in the ranking score

# Per-setup hold horizon (trading days) = last forward horizon in the engine.
HOLD = {
    "bounce": 3,
    "streak": 5,
    "multiday": 10,
    "breakout": 10,
    "cross": 20,
    "range": 10,
}
STYLE = {
    "bounce": "dip", "streak": "dip", "multiday": "dip",
    "breakout": "breakout", "cross": "breakout", "range": "range",
}
LABEL = {
    "bounce": "Buy the Bounce", "streak": "Red Streak", "multiday": "Multi-Day Drop",
    "breakout": "Breakout High", "cross": "MA Cross Up", "range": "Tight Range",
}


def sma(close: np.ndarray, period: int) -> np.ndarray:
    """Trailing `period`-day mean of close; NaN until the window fills."""
    n = len(close)
    out = np.full(n, np.nan)
    if n >= period:
        csum = np.cumsum(close)
        out[period - 1] = csum[period - 1] / period
        out[period:] = (csum[period:] - csum[:-period]) / period
    return out


def _trigger_arrays(close: np.ndarray) -> dict[str, np.ndarray]:
    """Boolean 'setup fires on this close' array for each setup (no look-ahead).

    Mirrors the firing conditions in strategy-engine.js find* / live* functions.
    """
    n = len(close)
    trig: dict[str, np.ndarray] = {k: np.zeros(n, dtype=bool) for k in HOLD}

    # bounce: single-day move <= -threshold
    with np.errstate(divide="ignore", invalid="ignore"):
        day = close[1:] / close[:-1] - 1.0
    trig["bounce"][1:] = day <= -BOUNCE_THRESHOLD / 100.0

    # streak: N consecutive down closes ending here
    down = np.zeros(n, dtype=bool)
    down[1:] = close[1:] < close[:-1]
    run = np.zeros(n, dtype=int)
    for i in range(1, n):
        run[i] = run[i - 1] + 1 if down[i] else 0
    trig["streak"] = run >= STREAK_N

    # multiday: trailing MD_WINDOW-day move <= -threshold
    if n > MD_WINDOW:
        mv = close[MD_WINDOW:] / close[:-MD_WINDOW] - 1.0
        trig["multiday"][MD_WINDOW:] = mv <= -MD_THRESHOLD / 100.0

    # breakout: close above the max of the prior BREAK_LOOK closes
    for i in range(BREAK_LOOK, n):
        if close[i] > close[i - BREAK_LOOK:i].max():
            trig["breakout"][i] = True

    # cross: close crosses from <=200d-MA to >200d-MA
    ma = sma(close, CROSS_PERIOD)
    for i in range(CROSS_PERIOD, n):
        if np.isfinite(ma[i - 1]) and np.isfinite(ma[i]):
            if close[i - 1] <= ma[i - 1] and close[i] > ma[i]:
                trig["cross"][i] = True

    # range: trailing RANGE_WINDOW-day peak-to-trough spread <= 2*band, and the
    # prior window did NOT qualify (fire only on the first day of a fresh range)
    spread = np.full(n, np.nan)
    for j in range(RANGE_WINDOW - 1, n):
        w = close[j - RANGE_WINDOW + 1:j + 1]
        spread[j] = (w.max() - w.min()) / w.mean()
    thr = 2 * RANGE_BAND / 100.0
    for i in range(RANGE_WINDOW - 1, n):
        if spread[i] <= thr and not (np.isfinite(spread[i - 1]) and spread[i - 1] <= thr):
            trig["range"][i] = True

    return trig


def _forward_arrays(open_: np.ndarray, close: np.ndarray, hold: int):
    """Next-open-entry forward return and MAE for a hold, per bar.

    fwd[j] = close[j+1+hold] / open[j+1] - 1          (entry at next open)
    mae[j] = min over h in 1..hold of close[j+1+h]/open[j+1] - 1  (<=0)
    valid[j] = the full hold window exists within the series.
    """
    n = len(close)
    fwd = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    for j in range(n):
        entry_idx = j + 1
        exit_idx = j + 1 + hold
        if exit_idx >= n or entry_idx >= n:
            continue
        entry = open_[entry_idx]
        if not entry > 0:
            continue
        fwd[j] = close[exit_idx] / entry - 1.0
        worst = 0.0
        for h in range(1, hold + 1):
            r = close[entry_idx + h] / entry - 1.0
            if r < worst:
                worst = r
        mae[j] = worst
        valid[j] = True
    return fwd, mae, valid


def _move_z(close: np.ndarray, t: int, w: int) -> float:
    """z-score of the latest w-day move vs its trailing ~1y distribution.

    Mirrors moveZ() in scanner.js. Returns NaN when there is too little history.
    """
    n = t + 1
    if n < w + 40:
        return np.nan
    start = max(w, n - 252)
    moves = close[start:n] / close[start - w:n - w] - 1.0
    if len(moves) < 20:
        return np.nan
    m = moves.mean()
    s = moves.std()  # population std, matching the JS
    if not s:
        return np.nan
    last = close[t] / close[t - w] - 1.0
    return (last - m) / s


@dataclass
class Instrument:
    ticker: str
    name: str
    theme: str
    lev: bool
    dates: pd.DatetimeIndex
    open: np.ndarray
    close: np.ndarray


# A single-day price ratio beyond this is physically impossible even for a 3x
# daily ETP (it would need a >100% underlying move), so it is a split / bad bar,
# not a real return. Yahoo bakes some leveraged-ETP reverse splits straight into
# the (adj)close without a split event, so we repair them ourselves.
SPLIT_HI = 4.0
SPLIT_LO = 0.25


def repair_splits(open_: np.ndarray, close: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Back-adjust prices across split-sized discontinuities.

    Anchors the most recent segment (factor 1) and scales each earlier segment so
    the series is continuous through every split. Returns (open, close, n_splits).
    """
    n = len(close)
    f = np.ones(n)
    n_splits = 0
    for t in range(n - 1, 0, -1):
        if close[t - 1] <= 0:
            continue
        r = close[t] / close[t - 1]
        if r > SPLIT_HI or r < SPLIT_LO:
            f[:t] *= r
            n_splits += 1
    return open_ * f, close * f, n_splits


def build_instruments(prices: pd.DataFrame, repair: bool = True) -> dict[str, Instrument]:
    """Group the long price frame into per-ticker Instrument records."""
    out: dict[str, Instrument] = {}
    repaired = 0
    for ticker, g in prices.groupby("ticker", sort=False):
        g = g.sort_values("date")
        open_ = g["open"].to_numpy(dtype=float)
        close = g["close"].to_numpy(dtype=float)
        if repair:
            open_, close, ns = repair_splits(open_, close)
            if ns:
                repaired += 1
        out[ticker] = Instrument(
            ticker=ticker,
            name=g["name"].iloc[0],
            theme=g["theme"].iloc[0],
            lev=bool(g["lev"].iloc[0]),
            dates=pd.DatetimeIndex(g["date"].values),
            open=open_,
            close=close,
        )
    if repair and repaired:
        print(f"  repaired splits in {repaired} instruments")
    return out


def scan_history(inst: Instrument, track_years: int = 5, same_trend: bool = True) -> pd.DataFrame:
    """Every 'fresh' Scanner row across this instrument's history.

    A fresh row = a setup that fires on bar t but did not on t-1 (the Scanner's
    "New today"). Each row carries the stats the Scanner would have displayed on
    the signal date (close of bar t), computed with no look-ahead. Entry is the
    next open (bar t+1).

    Columns: ticker, name, theme, lev, strategy, style, hold, signal_idx,
    signal_date, entry_idx, entry_date, edge, edge_win, win_rate, med, worst,
    mae, n, trend_up, z, score, confluence.
    """
    close, open_, dates = inst.close, inst.open, inst.dates
    n = len(close)
    sma200 = sma(close, 200)
    regime_valid = np.isfinite(sma200)
    regime_up = np.zeros(n, dtype=bool)
    regime_up[regime_valid] = close[regime_valid] >= sma200[regime_valid]

    trig = _trigger_arrays(close)
    fwd_by = {}
    mae_by = {}
    valid_by = {}
    for k, h in HOLD.items():
        fwd_by[k], mae_by[k], valid_by[k] = _forward_arrays(open_, close, h)

    date_vals = dates.values  # datetime64[ns], sorted
    rows = []

    for strat, h in HOLD.items():
        tr = trig[strat]
        fwd, mae, valid = fwd_by[strat], mae_by[strat], valid_by[strat]
        fresh = tr.copy()
        fresh[1:] = tr[1:] & ~tr[:-1]  # flipped true on this bar
        # Need a next bar to enter on, and >=2 prior bars (scanner idx>=2).
        fresh_idx = np.flatnonzero(fresh)
        for t in fresh_idx:
            if t < 2 or t + 1 >= n:
                continue
            up = bool(regime_up[t]) if regime_valid[t] else None
            regime = (up if same_trend else None) if up is not None else None

            cutoff = dates[t] - pd.DateOffset(years=track_years)
            lo = int(np.searchsorted(date_vals, np.datetime64(cutoff), side="left"))
            hi = t - h  # events need the full hold inside the view: j <= t-h-1

            if hi <= lo:
                base_avg = base_rate = np.nan
                ev_n = 0
                edge = edge_win = win_rate = med = worst = mae_avg = np.nan
            else:
                sl = slice(lo, hi)
                vmask = valid[sl]
                if regime is not None:
                    rmask = regime_valid[sl] & (regime_up[sl] == (regime == "up"))
                    base_mask = vmask & rmask
                else:
                    base_mask = vmask
                bf = fwd[sl][base_mask]
                if len(bf):
                    base_avg = bf.mean() * 100.0
                    base_rate = (bf > 0).mean() * 100.0
                else:
                    base_avg = base_rate = np.nan
                ev_mask = base_mask & tr[sl]
                ef = fwd[sl][ev_mask]
                em = mae[sl][ev_mask]
                ev_n = int(len(ef))
                if ev_n:
                    ev_avg = ef.mean() * 100.0
                    win_rate = (ef > 0).mean() * 100.0
                    med = float(np.median(ef)) * 100.0
                    worst = ef.min() * 100.0
                    mae_avg = em.mean() * 100.0
                    edge = ev_avg - base_avg if np.isfinite(base_avg) else np.nan
                    edge_win = win_rate - base_rate if np.isfinite(base_rate) else np.nan
                else:
                    win_rate = med = worst = mae_avg = edge = edge_win = np.nan

            score = (edge / h) * (ev_n / (ev_n + SHRINK_K)) if np.isfinite(edge) else -np.inf
            z = np.nan
            if strat == "bounce":
                z = _move_z(close, t, 1)
            elif strat == "multiday":
                z = _move_z(close, t, MD_WINDOW)

            rows.append({
                "ticker": inst.ticker, "name": inst.name, "theme": inst.theme, "lev": inst.lev,
                "strategy": strat, "style": STYLE[strat], "hold": h,
                "signal_idx": int(t), "signal_date": dates[t],
                "entry_idx": int(t + 1), "entry_date": dates[t + 1],
                "edge": edge, "edge_win": edge_win, "win_rate": win_rate,
                "med": med, "worst": worst, "mae": mae_avg, "n": ev_n,
                "trend_up": up, "z": z, "score": score,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        # Confluence: setups firing on the same instrument on the same date.
        df["confluence"] = df.groupby("signal_date")["strategy"].transform("count")
    return df
