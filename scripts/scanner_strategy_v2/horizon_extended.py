"""Extended horizon study: does holding *much* longer (3 weeks - 3 months) help?

The v2 report tested holds of 2-20 days and rejected longer horizons as
"overfitting", arguing from *per-day* edge. But for a cost-bound £1000 account
the thing that pays the rent is **total return per trade net of the fixed
per-trade cost**, not per-day edge. A longer hold:

  * amortises the round-trip spread (+ FX) over a bigger move, and
  * lets the market's own drift (beta) work for you instead of being churned
    away in 3-day round-trips.

So this script measures, for every setup, across holds out to ~3 months
(63 trading days), on uptrend names in the live window:

  gross%    mean forward return entry-open -> exit-close (alpha + the drift you
            actually KEEP by staying long)
  edge%     gross minus the instrument's own next-open baseline (drift removed;
            the v1/v2 "EDGE")
  net%      gross minus a realistic round-trip cost (LSE 0.30% blended)
  ann_net%  net% annualised if you held back-to-back trades all year
            (= net% * 252 / hold) -- the "money" column: a smaller per-day edge
            held longer can still win because cost is paid once per trade.

Run: /usr/local/bin/python3 scripts/scanner_strategy_v2/horizon_extended.py
Outputs: data/scanner_strategy_v2/horizon_extended.csv  (+ console tables)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.scanner_strategy.scanner_lib import _trigger_arrays, HOLD, LABEL  # noqa: E402
from scripts.scanner_strategy_v2.scanner_lib import sma, build_instruments  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "scanner_strategy_v2"
PRICES = DATA_DIR / "prices_ohlc.parquet"

START = np.datetime64("2021-07-01")
END = np.datetime64("2026-06-26")
HOLDS = (3, 5, 10, 15, 21, 42, 63)          # 3d, 1wk, 2wk, 3wk, 1mo, 2mo, 3mo
ROUND_TRIP_COST = 0.30                        # %, blended LSE spread + a little FX
TRADING_DAYS = 252


def fwd_returns(open_: np.ndarray, close: np.ndarray, hold: int):
    """Per signal-bar j: forward return entry-open(j+1) -> close(j+1+hold)."""
    n = len(close)
    fwd = np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    for j in range(n):
        ei, xi = j + 1, j + 1 + hold
        if xi >= n or ei >= n or not open_[ei] > 0:
            continue
        fwd[j] = close[xi] / open_[ei] - 1.0
        valid[j] = True
    return fwd, valid


def main():
    if not PRICES.exists():
        sys.exit(f"missing {PRICES} -- run fetch_prices.py first")
    prices = pd.read_parquet(PRICES)
    insts = build_instruments(prices)
    print(f"{len(insts)} instruments; holds {HOLDS}; cost {ROUND_TRIP_COST}% round-trip\n")

    recs = []
    for setup in HOLD:
        for h in HOLDS:
            ev_fwd, base_fwd = [], []
            for inst in insts.values():
                if inst.lev:
                    continue
                close, open_ = inst.close, inst.open
                if len(close) < 260:
                    continue
                ma = sma(close, 200)
                up = np.isfinite(ma) & (close >= ma)
                trig = _trigger_arrays(close)[setup]
                fresh = trig.copy()
                fresh[1:] = trig[1:] & ~trig[:-1]
                fwd, valid = fwd_returns(open_, close, h)
                d = inst.dates.values
                inwin = valid & up & (d >= START) & (d <= END)
                base_fwd.append(fwd[inwin])
                ev_fwd.append(fwd[inwin & fresh])
            bf = np.concatenate(base_fwd) if base_fwd else np.array([])
            ef = np.concatenate(ev_fwd) if ev_fwd else np.array([])
            if len(ef) < 30 or not len(bf):
                recs.append({"setup": setup, "hold": h, "n": int(len(ef))})
                continue
            gross = ef.mean() * 100
            edge = gross - bf.mean() * 100
            net = gross - ROUND_TRIP_COST
            recs.append({
                "setup": setup, "hold": h, "n": int(len(ef)),
                "win%": round((ef > 0).mean() * 100, 1),
                "gross%": round(gross, 3),
                "edge%": round(edge, 3),
                "net%": round(net, 3),
                "net/day": round(net / h, 4),
                "ann_net%": round(net * TRADING_DAYS / h, 1),
            })
    df = pd.DataFrame(recs)
    df.to_csv(DATA_DIR / "horizon_extended.csv", index=False)

    pd.set_option("display.width", 140)
    for setup in HOLD:
        sub = df[df["setup"] == setup].drop(columns="setup")
        print(f"=== {LABEL[setup]} ({setup}) ===")
        print(sub.to_string(index=False))
        print()
    print(f"Wrote {DATA_DIR / 'horizon_extended.csv'}")


if __name__ == "__main__":
    main()
