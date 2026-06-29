"""v3 monthly momentum-rotation backtest on a simulated £1000 GBP ISA.

WHY A NEW ENGINE. The v2 backtest (``backtest.py``) is event-driven: a setup
fires on a bar, you enter next open, and you exit on a stop / target / time.
That is the right machine for a *dip* trade. But the one signal that passed the
v3 validation sort cleanly — 12-1 momentum (B1) — is a **monthly cross-sectional
rotation**, a different machine: each month, rank the universe, hold the top few
trend-confirmed names, rebalance. Forcing it through the event engine would
misrepresent it. So this engine rotates, while *reusing v2's honest accounting*
verbatim:

  * GBP ISA, compounding (positions are a % of live equity).
  * LSE round-trip cost = ``spread`` charged ``spread/2`` per side.
  * Trading 212 FX conversion fee charged per conversion on USD/EUR names; fills
    translated to GBP through the daily cross.
  * Benchmark = £1000 into IWDA (MSCI World) in GBP, one entry cost — the same
    "just buy the market" yardstick v2 uses.
  * Only the realised *delta* of each rebalance is charged (names that stay in
    the book are not churned), so costs are not overstated.

Signals come from :mod:`scripts.scanner_strategy_v2.signals_v3` (the cemented v3
detectors). The rebalance convention matches the validation sort exactly:
signals are read at the close of the first trading day of each month (using only
data up to that bar) and executed at the **next open** — no look-ahead.

This module only defines the engine + Config. ``run_experiments_v3.py`` drives
it (train/test split, sweeps, the dip satellite) and writes the report outputs.

Run a single default config for a smoke test:
    /usr/local/bin/python3 -m scripts.scanner_strategy_v2.backtest_v3
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.scanner_strategy_v2 import scanner_lib as L  # noqa: E402
from scripts.scanner_strategy_v2 import signals_v3 as S3  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "scanner_strategy_v2"
PRICES = DATA_DIR / "prices_ohlc.parquet"
FX = DATA_DIR / "fx.parquet"
BENCHMARK = "IWDA.L"
TRADING_DAYS = 252


@dataclass
class Config:
    start: str = "2021-07-01"
    end: str = "2026-06-26"
    capital: float = 1000.0
    # selection (pre-registered defaults from the note/sort, NOT P&L-fit)
    n_hold: int = 5                 # equal-weight top-N
    mom_look: int = 252             # 12-month lookback
    mom_skip: int = 21              # 12-1 skip month
    blend_proximity: float = 0.0    # 0 = pure 12-1; >0 blends 52wk-high prox tilt
    require_pos_mom: bool = True    # only hold names with momentum > 0
    require_trend: bool = True      # only hold names above their 200-day MA
    cash_when_few: bool = True      # O4 escape hatch: undersized book sits in cash
    rebalance_freq: str = "M"       # M(onthly) | Q(uarterly)
    vol_target: bool = False        # O2: inverse-vol weights instead of equal
    vol_floor: float = 0.05         # annualized vol floor for inverse-vol sizing
    # costs (identical intent to v2)
    spread_plain: float = 0.0025    # LSE round-trip spread (charged /2 per side)
    fx: bool = True                 # translate + charge FX on USD/EUR names
    fx_fee: float = 0.0015          # T212 FX conversion fee, per conversion


# --------------------------------------------------------------------------- #
# Pre-compute per-instrument signal arrays once.
# --------------------------------------------------------------------------- #
@dataclass
class SigArrays:
    mom: np.ndarray
    prox: np.ndarray
    trend: np.ndarray
    vol: np.ndarray


def precompute_signals(insts: dict, cfg: Config) -> dict[str, SigArrays]:
    out = {}
    for tk, inst in insts.items():
        if inst.lev:
            continue
        close = inst.close
        if len(close) < 300:
            continue
        out[tk] = SigArrays(
            mom=S3.momentum_12_1(close, cfg.mom_look, cfg.mom_skip),
            prox=S3.high_proximity(close),
            trend=S3.trend_up(close),
            vol=L.realised_vol(close),
        )
    return out


def rebalance_signal_dates(timeline: pd.DatetimeIndex, cfg: Config) -> pd.DatetimeIndex:
    """First trading day of each month (or quarter) in the window — the bar at
    whose close signals are read (execution is the next open)."""
    start, end = pd.Timestamp(cfg.start), pd.Timestamp(cfg.end)
    d = timeline[(timeline >= start) & (timeline <= end)]
    s = pd.Series(d)
    if cfg.rebalance_freq == "Q":
        key = [s.dt.year, s.dt.quarter]
    else:
        key = [s.dt.year, s.dt.month]
    first = s.groupby(key).min()
    return pd.DatetimeIndex(sorted(first.values))


# --------------------------------------------------------------------------- #
# The rotation engine.
# --------------------------------------------------------------------------- #
def _targets(cfg, sigs, idx_maps, sig_date, tickers) -> dict[str, float]:
    """Target GBP *weights* for the book as of a signal bar. Sums to <= 1; the
    remainder (escape hatch) is cash. Weight keys are tickers."""
    cands = []
    for tk in tickers:
        sa = sigs.get(tk)
        if sa is None:
            continue
        i = idx_maps[tk].get(sig_date)
        if i is None:
            continue
        m = sa.mom[i]
        if not np.isfinite(m):
            continue
        if cfg.require_trend and not sa.trend[i]:
            continue
        if cfg.require_pos_mom and not (m > 0):
            continue
        score = m
        if cfg.blend_proximity > 0 and np.isfinite(sa.prox[i]):
            # rank-blend handled by caller; here we keep a composite score by
            # adding a standardized proximity tilt at fixed weight.
            score = m + cfg.blend_proximity * sa.prox[i]
        cands.append((tk, score, sa.vol[i]))
    if not cands:
        return {}
    cands.sort(key=lambda x: x[1], reverse=True)
    picks = cands[:cfg.n_hold]
    # denominator: n_hold when the escape hatch is on (so a thin book holds cash),
    # else the number actually picked (always fully invested).
    denom = cfg.n_hold if cfg.cash_when_few else len(picks)
    if cfg.vol_target:
        inv = []
        for tk, _, v in picks:
            av = (v * np.sqrt(TRADING_DAYS)) if np.isfinite(v) else np.nan
            inv.append(1.0 / max(av, cfg.vol_floor) if np.isfinite(av) else 0.0)
        tot = sum(inv)
        if tot <= 0:
            return {tk: 1.0 / denom for tk, _, _ in picks}
        # scale so the fully-invested fraction matches len(picks)/denom
        frac = len(picks) / denom
        return {tk: frac * w / tot for (tk, _, _), w in zip(picks, inv)}
    return {tk: 1.0 / denom for tk, _, _ in picks}


def run(cfg: Config, insts, sigs, timeline, idx_maps, fx_df):
    start, end = pd.Timestamp(cfg.start), pd.Timestamp(cfg.end)
    days = timeline[(timeline >= start) & (timeline <= end)]
    sig_dates = rebalance_signal_dates(timeline, cfg)
    # execution day = the trading day AFTER each signal day (next open)
    pos_in_tl = {d: k for k, d in enumerate(timeline)}
    exec_after = {}
    for sd in sig_dates:
        k = pos_in_tl[sd]
        if k + 1 < len(timeline):
            exec_after[timeline[k + 1]] = sd
    tickers = list(sigs.keys())

    fx_aligned = fx_df.set_index("date").reindex(timeline).ffill().bfill()
    # per-ticker sorted date array for carry-forward lookups
    date_arrs = {tk: inst.dates.values for tk, inst in insts.items()}

    def fx_units_per_gbp(inst, d):
        if not cfg.fx:
            return 1.0, False
        c = (inst.currency or "").upper()
        row = fx_aligned.loc[d]
        if c == "USD":
            return float(row["gbpusd"]), True
        if c == "EUR":
            return float(row["gbpeur"]), True
        return 1.0, False

    def px(tk, d, field="close"):
        """Exact-bar price on day d (for trading). None if the name has no bar."""
        i = idx_maps[tk].get(d)
        if i is None:
            return None
        v = getattr(insts[tk], field)[i]
        return float(v) if v > 0 else None

    def px_carry(tk, d):
        """Last valid close on or before d (for mark-to-market on data-gap days).

        The union timeline contains days where some names did not trade; marking a
        held name to zero on such a day would invent a phantom crash. Carrying the
        last known close (no look-ahead) is the correct valuation."""
        arr = date_arrs[tk]
        pos = int(np.searchsorted(arr, np.datetime64(d), side="right")) - 1
        c = insts[tk].close
        while pos >= 0:
            if c[pos] > 0:
                return float(c[pos])
            pos -= 1
        return None

    def gbp_value(tk, shares, d, field="close"):
        """GBP mark of a holding. For close marks, carry forward across data gaps;
        for open (trade-time) marks, require an exact bar."""
        if shares == 0:
            return 0.0
        p = px_carry(tk, d) if field == "close" else px(tk, d, field)
        if p is None:
            return None
        fxr, _ = fx_units_per_gbp(insts[tk], d)
        return shares * p / fxr

    cash = cfg.capital
    shares: dict[str, float] = {}
    equity_hist, rebal_log = [], []
    cost_total = 0.0
    sp = cfg.spread_plain

    for d in days:
        # ---- rebalance at this open if d is an execution day ----
        if d in exec_after:
            sig_date = exec_after[d]
            # equity at the execution open (mark retained holdings at open)
            held_val = 0.0
            for tk, sh in shares.items():
                v = gbp_value(tk, sh, d, "open")
                if v is None:
                    v = gbp_value(tk, sh, d, "close") or 0.0
                held_val += v
            equity = cash + held_val
            weights = _targets(cfg, sigs, idx_maps, sig_date, tickers)

            # target shares per ticker at the execution open
            target_shares: dict[str, float] = {}
            for tk, w in weights.items():
                p = px(tk, d, "open")
                if p is None:
                    continue
                fxr, _ = fx_units_per_gbp(insts[tk], d)
                target_shares[tk] = (w * equity) * fxr / p

            # trade every name whose share count changes (delta only)
            names = set(shares) | set(target_shares)
            traded_gbp = 0.0
            for tk in names:
                cur = shares.get(tk, 0.0)
                tgt = target_shares.get(tk, 0.0)
                dsh = tgt - cur
                if abs(dsh) < 1e-12:
                    continue
                p = px(tk, d, "open")
                if p is None:
                    continue  # cannot trade a name with no bar today; keep it
                fxr, is_fx = fx_units_per_gbp(insts[tk], d)
                notional = abs(dsh) * p / fxr                 # GBP mid notional
                side_cost = notional * (sp / 2 + (cfg.fx_fee if is_fx else 0.0))
                cost_total += side_cost
                traded_gbp += notional
                if dsh > 0:                                   # buy
                    cash -= notional + side_cost
                else:                                          # sell
                    cash += notional - side_cost
                new_sh = cur + dsh
                if abs(new_sh) < 1e-12:
                    shares.pop(tk, None)
                else:
                    shares[tk] = new_sh
            rebal_log.append({"exec_date": d, "signal_date": sig_date,
                              "n_held": len(target_shares), "traded_gbp": round(traded_gbp, 2),
                              "invested_frac": round(sum(weights.values()), 3)})

        # ---- mark to market at close (GBP) ----
        mtm = 0.0
        for tk, sh in shares.items():
            v = gbp_value(tk, sh, d, "close")
            if v is None:
                v = gbp_value(tk, sh, d, "open") or 0.0
            mtm += v
        equity_hist.append({"date": d, "equity": cash + mtm, "cash": cash,
                            "n_positions": len(shares)})

    equity_df = pd.DataFrame(equity_hist)
    equity_df = _add_benchmark(cfg, equity_df, insts, idx_maps, days, fx_aligned)
    summary = summarise(cfg, equity_df, days, cost_total, rebal_log)
    return equity_df, summary, pd.DataFrame(rebal_log)


def _add_benchmark(cfg, equity_df, insts, idx_maps, days, fx_aligned):
    bench = insts.get(BENCHMARK)
    if bench is None:
        return equity_df
    bim = idx_maps[BENCHMARK]

    def bfx(d):
        if not cfg.fx:
            return 1.0, False
        c = (bench.currency or "").upper()
        row = fx_aligned.loc[d]
        if c == "USD":
            return float(row["gbpusd"]), True
        if c == "EUR":
            return float(row["gbpeur"]), True
        return 1.0, False

    bi = bim.get(days[0])
    if bi is None:
        return equity_df
    sp = cfg.spread_plain
    b0 = bench.open[bi] * (1 + sp / 2)
    fx0, is_fx = bfx(days[0])
    haircut = (1 - cfg.fx_fee) if (cfg.fx and is_fx) else 1.0
    vals = []
    for d in days:
        i = bim.get(d)
        if i is None:
            vals.append(np.nan)
            continue
        fxn = bfx(d)[0]
        vals.append(cfg.capital * (bench.close[i] / b0) * (fx0 / fxn) * haircut)
    equity_df["benchmark"] = pd.Series(vals).ffill().bfill().values
    return equity_df


def _sharpe(eq: np.ndarray) -> float:
    r = np.diff(eq) / eq[:-1]
    r = r[np.isfinite(r)]
    if len(r) < 2 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS))


def _max_dd(eq: np.ndarray) -> float:
    peak = np.maximum.accumulate(eq)
    return float(((eq - peak) / peak).min())


def summarise(cfg, equity_df, days, cost_total, rebal_log) -> dict:
    eq = equity_df["equity"].to_numpy()
    final = float(eq[-1])
    years = (days[-1] - days[0]).days / 365.25
    cagr = (final / cfg.capital) ** (1 / years) - 1 if years > 0 and final > 0 else float("nan")
    out = {
        "final_equity": round(final, 2),
        "total_return_pct": round((final / cfg.capital - 1) * 100, 1),
        "cagr_pct": round(cagr * 100, 1),
        "max_drawdown_pct": round(_max_dd(eq) * 100, 1),
        "sharpe": round(_sharpe(eq), 2),
        "calmar": round(cagr / abs(_max_dd(eq)), 2) if _max_dd(eq) < 0 else float("nan"),
        "total_cost_gbp": round(cost_total, 2),
        "n_rebalances": len(rebal_log),
        "avg_invested_frac": round(float(np.mean([r["invested_frac"] for r in rebal_log])), 3) if rebal_log else 0.0,
    }
    if "benchmark" in equity_df:
        b = equity_df["benchmark"].to_numpy()
        bcagr = (b[-1] / cfg.capital) ** (1 / years) - 1 if years > 0 and b[-1] > 0 else float("nan")
        out["benchmark_final"] = round(float(b[-1]), 2)
        out["benchmark_return_pct"] = round(float(b[-1] / cfg.capital - 1) * 100, 1)
        out["benchmark_max_drawdown_pct"] = round(_max_dd(b) * 100, 1)
        out["benchmark_sharpe"] = round(_sharpe(b), 2)
        out["benchmark_calmar"] = round(bcagr / abs(_max_dd(b)), 2) if _max_dd(b) < 0 else float("nan")
    return out


def sanitize_spikes(inst, thr: float = 0.25) -> int:
    """Repair single-bar 'spike-and-revert' glitches in a price series.

    Yahoo occasionally prints a bad close (e.g. SPGP 2517 -> 3317 -> 2380 on one
    day) that jumps >thr and snaps back the next bar. Split repair (>4x) misses
    these sub-split spikes; left in, they inflate a concentrated book's apparent
    volatility and dent its Sharpe. We replace any bar that moves >thr and
    reverts the opposite way next bar — and whose day-after price returns within
    15% of the day-before price (confirming a round-trip, not a real move) — with
    the interpolation of its neighbours, scaling O/H/L by the same factor. Only
    isolated single-bar glitches are touched; genuine multi-day moves are left.
    """
    c = inst.close.copy()
    o, h, lo = inst.open.copy(), inst.high.copy(), inst.low.copy()
    n = len(c)
    fixed = 0
    for i in range(1, n - 1):
        if c[i - 1] <= 0 or c[i] <= 0 or c[i + 1] <= 0:
            continue
        r_in = c[i] / c[i - 1] - 1.0
        r_out = c[i + 1] / c[i] - 1.0
        spike = (r_in > thr and r_out < -thr * 0.6) or (r_in < -thr and r_out > thr * 0.6)
        if spike and abs(c[i + 1] / c[i - 1] - 1.0) < 0.15:
            repl = (c[i - 1] + c[i + 1]) / 2.0
            f = repl / c[i]
            o[i] *= f
            h[i] *= f
            lo[i] *= f
            c[i] = repl
            fixed += 1
    if fixed:
        inst.close, inst.open, inst.high, inst.low = c, o, h, lo
    return fixed


def load_world():
    """Load prices, FX, instruments, timeline and per-ticker index maps.

    Prices are split-repaired (in build_instruments) and then de-spiked, so the
    backtest never trades on or marks against a bad print."""
    prices = pd.read_parquet(PRICES)
    fx_df = pd.read_parquet(FX)
    insts = L.build_instruments(prices)
    spikes = sum(sanitize_spikes(inst) for inst in insts.values())
    if spikes:
        print(f"  de-spiked {spikes} bad bars across the universe")
    timeline = pd.DatetimeIndex(sorted(prices["date"].unique()))
    idx_maps = {tk: {d: i for i, d in enumerate(inst.dates)} for tk, inst in insts.items()}
    return insts, fx_df, timeline, idx_maps


if __name__ == "__main__":
    insts, fx_df, timeline, idx_maps = load_world()
    cfg = Config()
    sigs = precompute_signals(insts, cfg)
    print(f"{len(sigs)} non-lev instruments with signals; "
          f"window {cfg.start}..{cfg.end}")
    eq, s, rl = run(cfg, insts, sigs, timeline, idx_maps, fx_df)
    print("DEFAULT v3 rotation (12-1 mom, top-5, monthly, 200MA gate, cash hatch):")
    for k, v in s.items():
        print(f"  {k:28s} {v}")
