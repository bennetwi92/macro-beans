"""v3 long-horizon Scanner signals — the cemented detector set.

This module is where the ``scanner_signals_v3`` redesign turns from a design note
into reusable strategy code. It implements the signals that survived the
pre-backtest validation sort (``signal_sorts.py`` / ``scanner_signals_v3_sorts.md``)
as plain, no-look-ahead per-instrument arrays the v3 backtests consume:

  * :func:`momentum_12_1`  — B1, the one signal that PASSED the sort cleanly.
    12-month total return skipping the most recent ~month. The workhorse the
    monthly rotation engine ranks on.
  * :func:`high_proximity` — B3, the MARGINAL signal. close / trailing-252d high.
    Right sign, best top-bucket win-rate, but non-monotone and fading by 63d, so
    it is used trend-gated as a *tilt / confirmation*, never a standalone ranker.
  * :func:`multiday_drop_z` — A1, the vol-normalized replacement for the fixed
    ``-8%`` Multi-Day Drop. It FAILED as a cross-sectional ranker but the v3
    horizon study found a positive edge in its *event tail under a trend gate*,
    so it is exposed here as an event trigger (z <= -2) for the dip satellite,
    NOT as a continuous ranking score.
  * :func:`trend_up` — the 200-day-MA state (overlay B4 / O4). Used as the gate on
    every signal and as the cash escape hatch's regime switch.

Design rules these obey (note §2): state-not-event, volatility-normalized
thresholds, trend-gated. The fixed-threshold v1 detectors in
``scripts.scanner_strategy.scanner_lib`` are deliberately left untouched — they
mirror the live website's Scanner, and this research track must not silently
change what the public site fires on.

All functions are pure ``numpy`` and use only data up to each bar (entries happen
on the *next* bar in the backtests, never on the signal bar).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.scanner_strategy.scanner_lib import sma  # noqa: E402

# ---- v3 signal parameters (pre-registered from the note / sort, not P&L-fit) --
MOM_LOOK = 252      # 12-month momentum lookback (trading days)
MOM_SKIP = 21       # skip the most recent ~month (the 12-1 standard)
HIGH_LOOK = 252     # 52-week (1-year) high window
DROP_W = 10         # vol-normalized multi-day drop window (A1: "5-10 day")
DROP_Z = -2.0       # A1 event trigger: a >= 2-sigma drop
TREND_MA = 200      # trend-state / gate moving average
PROX_TRIGGER = 0.95  # B3 "near the high": within 5% of the 1-year high


def momentum_12_1(close: np.ndarray, look: int = MOM_LOOK, skip: int = MOM_SKIP) -> np.ndarray:
    """12-1 absolute (time-series) momentum per bar (B1).

    ``out[t] = close[t-skip] / close[t-look] - 1`` — the total return over the
    year ending one month ago, skipping the most recent ~month so short-term
    reversal does not contaminate it. NaN until ``look`` bars of history exist.
    """
    n = len(close)
    out = np.full(n, np.nan)
    if n > look:
        out[look:] = close[look - skip:n - skip] / close[0:n - look] - 1.0
    return out


def high_proximity(close: np.ndarray, look: int = HIGH_LOOK) -> np.ndarray:
    """close / trailing-`look`-day high (B3).

    1.0 at a fresh high, lower = further below. NaN until the window fills.
    """
    n = len(close)
    out = np.full(n, np.nan)
    for i in range(look - 1, n):
        hi = close[i - look + 1:i + 1].max()
        if hi > 0:
            out[i] = close[i] / hi
    return out


def move_z_array(close: np.ndarray, w: int) -> np.ndarray:
    """z-score of every bar's `w`-day move vs its own trailing ~1y distribution.

    Vectorized port of ``scanner_lib._move_z`` over all bars (population std, to
    match the live JS). NaN where there is too little history. This is the
    volatility-normalization the v3 vol-audit justified (design rule 2): "a -2 sigma
    move" means the same thing on a gilt ETF and a 3x ETP.
    """
    n = len(close)
    out = np.full(n, np.nan)
    mv = np.full(n, np.nan)
    if n > w:
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
        s = moves.std()
        if not s:
            continue
        out[t] = (mv[t] - moves.mean()) / s
    return out


def multiday_drop_z(close: np.ndarray, w: int = DROP_W, thresh: float = DROP_Z) -> np.ndarray:
    """A1 event trigger: a vol-normalized multi-day drop of at least `thresh` sigma.

    Boolean per-bar "fires on this close". This is the z-score replacement for the
    v1 fixed ``-8% / 5d`` Multi-Day Drop, which the vol-audit showed over-fires
    high-vol names 4-6x. Use only event-gated and trend-gated (see the note): the
    raw signal failed the cross-sectional sort.
    """
    z = move_z_array(close, w)
    return np.isfinite(z) & (z <= thresh)


def trend_up(close: np.ndarray, period: int = TREND_MA) -> np.ndarray:
    """200-day-MA trend state (B4 / the universal gate).

    Boolean per bar: price at/above its `period`-day MA. False before the MA
    exists. A persistent *state*, not the one-bar cross event v1 traded.
    """
    ma = sma(close, period)
    up = np.zeros(len(close), dtype=bool)
    ok = np.isfinite(ma)
    up[ok] = close[ok] >= ma[ok]
    return up


def fresh_edges(cond: np.ndarray) -> np.ndarray:
    """Rising edges of a boolean array (True only on the bar a condition turns on)."""
    c = np.asarray(cond, dtype=bool)
    fresh = c.copy()
    fresh[1:] = c[1:] & ~c[:-1]
    return fresh
