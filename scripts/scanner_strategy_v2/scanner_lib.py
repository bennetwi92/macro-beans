"""Scanner port for the v2 strategy — v1's engine plus the v2 methodology.

This imports the *tested* v1 detectors verbatim from
``scripts.scanner_strategy.scanner_lib`` (so the two backtests can never disagree
on what fires when) and adds the four things v2 needs:

  1. **Intraday MAE/MFE** — worst (low) and best (high) excursions during the
     hold, measured against the day's range, not just the close. v1 used
     close-to-close, which understates both the dip that shakes you out and the
     spike that could fill a target.
  2. **MFE percentile distribution** — for each signal, the percentiles of the
     historical max-favourable-excursion among comparable past events. v2 sets
     its take-profit from a *low percentile* of this distribution so the target
     is reached with known probability, instead of v1's fixed 3R alert.
  3. **Volatility regime** — realised 20-day vol and a high/low flag vs its own
     trailing median, so edge can be conditioned on (trend × vol), not trend
     alone.
  4. **Conditioned edge** — edge computed both v1-style (trend only) and
     v2-style (trend × vol), each with its own sample size, so we can measure
     whether the vol split earns its keep.

The detectors, the next-open-entry convention and the EDGE definition are
unchanged from v1.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
# Reuse the v1 engine: detectors, SMA, move-z, split repair, and the maps.
from scripts.scanner_strategy.scanner_lib import (  # noqa: E402
    HOLD, STYLE, LABEL, SHRINK_K, MD_WINDOW,
    sma, _trigger_arrays, _move_z, repair_splits,
)

VOL_WINDOW = 20          # trading days for realised vol
VOL_LOOKBACK = 252       # trailing window the vol regime is judged against
# MFE / MAE percentiles we expose per row (the backtest picks one for its target)
MFE_PCTLS = [10, 20, 25, 30, 40, 50, 60, 70, 75, 80]


@dataclass
class Instrument:
    ticker: str
    name: str
    theme: str
    lev: bool
    currency: str
    dates: pd.DatetimeIndex
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray


def build_instruments(prices: pd.DataFrame, repair: bool = True) -> dict[str, Instrument]:
    """Group the long OHLC frame into per-ticker records, repairing splits."""
    out: dict[str, Instrument] = {}
    repaired = 0
    for ticker, g in prices.groupby("ticker", sort=False):
        g = g.sort_values("date")
        o = g["open"].to_numpy(dtype=float)
        h = g["high"].to_numpy(dtype=float)
        lo = g["low"].to_numpy(dtype=float)
        c = g["close"].to_numpy(dtype=float)
        if repair:
            # Repair on close; apply the same factor to O/H/L by re-deriving it.
            o2, c2, ns = repair_splits(o, c)
            if ns:
                factor = np.divide(c2, c, out=np.ones_like(c), where=c > 0)
                h = h * factor
                lo = lo * factor
                o = o2
                c = c2
                repaired += 1
        out[ticker] = Instrument(
            ticker=ticker, name=g["name"].iloc[0], theme=g["theme"].iloc[0],
            lev=bool(g["lev"].iloc[0]), currency=str(g["currency"].iloc[0]),
            dates=pd.DatetimeIndex(g["date"].values), open=o, high=h, low=lo, close=c,
        )
    if repair and repaired:
        print(f"  repaired splits in {repaired} instruments")
    return out


def _forward_arrays_hl(open_, high, low, close, hold: int):
    """Forward stats per signal bar j, entering at the next open (bar j+1).

    Returns, per j:
      fwd       close[j+1+hold]/entry - 1            (v1 horizon return)
      mae_close min_{1..hold} close[entry+k]/entry-1 (v1 close-based MAE, <=0)
      mae_low   min_{0..hold} low[entry+k]/entry-1   (intraday dip, <=0)
      mfe_high  max_{0..hold} high[entry+k]/entry-1  (intraday spike, >=0)
      valid     full window present.
    Excursions include the entry day (k=0): the position is live from the open,
    so that day's range can already hit a stop or a target.
    """
    n = len(close)
    fwd = np.full(n, np.nan)
    mae_close = np.full(n, np.nan)
    mae_low = np.full(n, np.nan)
    mfe_high = np.full(n, np.nan)
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
        wc = 0.0
        for k in range(1, hold + 1):
            r = close[entry_idx + k] / entry - 1.0
            if r < wc:
                wc = r
        mae_close[j] = wc
        wl = 0.0
        wh = 0.0
        for k in range(0, hold + 1):
            rl = low[entry_idx + k] / entry - 1.0
            rh = high[entry_idx + k] / entry - 1.0
            if rl < wl:
                wl = rl
            if rh > wh:
                wh = rh
        mae_low[j] = wl
        mfe_high[j] = wh
        valid[j] = True
    return fwd, mae_close, mae_low, mfe_high, valid


def realised_vol(close: np.ndarray) -> np.ndarray:
    """Trailing VOL_WINDOW-day stdev of daily returns (per bar, NaN until full)."""
    n = len(close)
    ret = np.full(n, np.nan)
    ret[1:] = close[1:] / close[:-1] - 1.0
    out = np.full(n, np.nan)
    for i in range(VOL_WINDOW, n):
        w = ret[i - VOL_WINDOW + 1:i + 1]
        if np.all(np.isfinite(w)):
            out[i] = w.std()
    return out


def vol_regime(vol: np.ndarray) -> np.ndarray:
    """High(True)/low(False)/unknown(NaN-as-None) vs trailing-median vol.

    A day is 'high vol' if its realised vol exceeds the median realised vol over
    the prior VOL_LOOKBACK days. Uses only past data (no look-ahead).
    """
    n = len(vol)
    out = np.full(n, np.nan)  # 1.0 high, 0.0 low, nan unknown
    for i in range(n):
        if not np.isfinite(vol[i]):
            continue
        lo = max(0, i - VOL_LOOKBACK)
        hist = vol[lo:i]
        hist = hist[np.isfinite(hist)]
        if len(hist) < 30:
            continue
        out[i] = 1.0 if vol[i] > np.median(hist) else 0.0
    return out


def scan_history(inst: Instrument, track_years: int = 5, same_trend: bool = True) -> pd.DataFrame:
    """Every fresh Scanner row across an instrument's history, v2-augmented.

    Adds to the v1 columns: currency, mae_low, mfe_high, mfe_p* (percentiles),
    vol, vol_high, edge_vol (trend×vol-conditioned edge) and n_vol.
    """
    close, open_, high, low, dates = inst.close, inst.open, inst.high, inst.low, inst.dates
    n = len(close)
    sma200 = sma(close, 200)
    regime_valid = np.isfinite(sma200)
    regime_up = np.zeros(n, dtype=bool)
    regime_up[regime_valid] = close[regime_valid] >= sma200[regime_valid]

    vol = realised_vol(close)
    vreg = vol_regime(vol)            # 1 high / 0 low / nan
    vreg_valid = np.isfinite(vreg)

    trig = _trigger_arrays(close)
    fwd_by, mae_c_by, mae_l_by, mfe_by, valid_by = {}, {}, {}, {}, {}
    for k, h in HOLD.items():
        fwd_by[k], mae_c_by[k], mae_l_by[k], mfe_by[k], valid_by[k] = \
            _forward_arrays_hl(open_, high, low, close, h)

    date_vals = dates.values
    rows = []

    for strat, h in HOLD.items():
        tr = trig[strat]
        fwd, mae_c, mae_l, mfe = fwd_by[strat], mae_c_by[strat], mae_l_by[strat], mfe_by[strat]
        valid = valid_by[strat]
        fresh = tr.copy()
        fresh[1:] = tr[1:] & ~tr[:-1]
        for t in np.flatnonzero(fresh):
            if t < 2 or t + 1 >= n:
                continue
            up = bool(regime_up[t]) if regime_valid[t] else None
            regime = up if (same_trend and up is not None) else None
            vhi = bool(vreg[t]) if vreg_valid[t] else None

            cutoff = dates[t] - pd.DateOffset(years=track_years)
            lo_i = int(np.searchsorted(date_vals, np.datetime64(cutoff), side="left"))
            hi_i = t - h

            row = {
                "ticker": inst.ticker, "name": inst.name, "theme": inst.theme,
                "lev": inst.lev, "currency": inst.currency,
                "strategy": strat, "style": STYLE[strat], "hold": h,
                "signal_idx": int(t), "signal_date": dates[t],
                "entry_idx": int(t + 1), "entry_date": dates[t + 1],
                "trend_up": up, "vol": float(vol[t]) if np.isfinite(vol[t]) else np.nan,
                "vol_high": vhi,
            }

            if hi_i <= lo_i:
                row.update(_empty_stats())
                rows.append(row)
                continue

            sl = slice(lo_i, hi_i)
            vmask = valid[sl]
            if regime is not None:
                rmask = regime_valid[sl] & (regime_up[sl] == regime)
                base_mask = vmask & rmask
            else:
                base_mask = vmask
            bf = fwd[sl][base_mask]
            base_avg = bf.mean() * 100.0 if len(bf) else np.nan
            base_rate = (bf > 0).mean() * 100.0 if len(bf) else np.nan

            ev_mask = base_mask & tr[sl]
            ef = fwd[sl][ev_mask]
            el = mae_l[sl][ev_mask]
            ec = mae_c[sl][ev_mask]
            ehi = mfe[sl][ev_mask]
            ev_n = int(len(ef))
            if ev_n:
                ev_avg = ef.mean() * 100.0
                row["win_rate"] = (ef > 0).mean() * 100.0
                row["med"] = float(np.median(ef)) * 100.0
                row["worst"] = ef.min() * 100.0
                row["mae"] = ec.mean() * 100.0          # v1 close MAE
                row["mae_low"] = el.mean() * 100.0       # intraday MAE
                row["mfe_high"] = ehi.mean() * 100.0
                row["edge"] = ev_avg - base_avg if np.isfinite(base_avg) else np.nan
                row["edge_win"] = row["win_rate"] - base_rate if np.isfinite(base_rate) else np.nan
                # MFE percentiles (in %), low percentile = conservative target
                for p in MFE_PCTLS:
                    row[f"mfe_p{p}"] = float(np.percentile(ehi, p)) * 100.0
            else:
                row.update(_empty_event_stats())
            row["n"] = ev_n

            # ---- vol-conditioned edge (trend AND vol regime) ----
            if vhi is not None:
                vmask2 = base_mask & vreg_valid[sl] & (vreg[sl] == (1.0 if vhi else 0.0))
                bf2 = fwd[sl][vmask2]
                base_avg2 = bf2.mean() * 100.0 if len(bf2) else np.nan
                ev2 = vmask2 & tr[sl]
                ef2 = fwd[sl][ev2]
                if len(ef2) and np.isfinite(base_avg2):
                    row["edge_vol"] = ef2.mean() * 100.0 - base_avg2
                    row["n_vol"] = int(len(ef2))
                else:
                    row["edge_vol"] = np.nan
                    row["n_vol"] = int(len(ef2))
            else:
                row["edge_vol"] = np.nan
                row["n_vol"] = 0

            edge = row.get("edge", np.nan)
            row["score"] = (edge / h) * (ev_n / (ev_n + SHRINK_K)) if np.isfinite(edge) else -np.inf

            z = np.nan
            if strat == "bounce":
                z = _move_z(close, t, 1)
            elif strat == "multiday":
                z = _move_z(close, t, MD_WINDOW)
            row["z"] = z
            rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["confluence"] = df.groupby("signal_date")["strategy"].transform("count")
    return df


def _empty_event_stats() -> dict:
    d = {k: np.nan for k in ("win_rate", "med", "worst", "mae", "mae_low",
                             "mfe_high", "edge", "edge_win")}
    for p in MFE_PCTLS:
        d[f"mfe_p{p}"] = np.nan
    return d


def _empty_stats() -> dict:
    d = _empty_event_stats()
    d.update({"n": 0, "score": -np.inf, "z": np.nan, "edge_vol": np.nan, "n_vol": 0})
    return d
