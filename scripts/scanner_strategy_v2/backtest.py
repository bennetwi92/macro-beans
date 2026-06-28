"""Backtest the Scanner playbook v2 on a simulated £1000 GBP ISA.

v2 differs from v1 (scripts/scanner_strategy/backtest.py) along the axes the
owner's feedback asked for, each switchable so we can ablate its contribution:

  * exit_mode    "close_nextopen" (v1) | "intraday_hl" (v2): check stop/target
                 against the day's HIGH/LOW intraday and fill there, instead of
                 on the prior close at the next open.
  * stop_basis   "mae_close" (v1) | "mae_low" (v2): size the stop off the
                 intraday (low) MAE, the dip you actually endure.
  * target_mode  "fixed_r" (v1, 3R alert) | "mfe_pctl" (v2): set the take-profit
                 at a chosen percentile of the historical max-favourable-
                 excursion, so it is reached with a known probability.
  * fx           translate USD/EUR fills to GBP through the daily cross and
                 charge Trading 212's FX conversion fee (v1 ignored currency).
  * vol_gate     condition entries on the volatility regime.
  * confluence   require / ignore multi-setup agreement.

Accounting is GBP and compounds (risk is a % of live equity). The benchmark is
£1000 into MSCI World (IWDA), translated to GBP and charged one entry cost — the
honest "just buy the market" yardstick for a GBP investor.

Run (after fetch_prices.py):
    /usr/local/bin/python3 scripts/scanner_strategy_v2/backtest.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.scanner_strategy_v2 import scanner_lib as L  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "scanner_strategy_v2"
PRICES = DATA_DIR / "prices_ohlc.parquet"
FX = DATA_DIR / "fx.parquet"
ROWS_CACHE = DATA_DIR / "scanner_rows.parquet"
BENCHMARK = "IWDA.L"


@dataclass
class Config:
    start: str = "2021-07-01"
    end: str = "2026-06-26"
    capital: float = 1000.0
    # selection
    edge_min: float = 0.30
    edge_min_lev: float = 1.00
    n_min: int = 15
    require_green_win: bool = True
    uptrend_only: bool = True
    allow_leverage: bool = False
    dip_only: bool = False
    min_score: float = 0.0
    min_abs_z: float = 0.0
    max_new_per_day: int = 99
    max_positions: int = 6
    confluence_min: int = 1            # require >= this many setups agreeing
    use_confluence_sort: bool = True   # tie-break picks by confluence
    vol_gate: str = "off"              # off | high | low (take only that regime)
    require_vol_edge: bool = False     # require trend×vol-conditioned edge > 0
    # sizing
    risk_pct: float = 0.015
    stop_basis: str = "mae_close"      # mae_close | mae_low
    stop_mult: float = 1.4
    stop_min: float = 0.03
    stop_max: float = 0.12
    pos_cap: float = 0.40
    min_ticket: float = 5.0
    # exit / target
    exit_mode: str = "close_nextopen"  # close_nextopen | intraday_hl
    target_mode: str = "fixed_r"       # fixed_r | mfe_pctl
    tp_r: float = 3.0                  # fixed_r: target = tp_r x stop distance
    mfe_pctl: int = 40                 # mfe_pctl: target = this MFE percentile
    # costs
    spread_plain: float = 0.0025
    spread_lev: float = 0.0060
    fx: bool = False                   # translate + charge FX on USD/EUR names
    fx_fee: float = 0.0015             # T212 FX conversion fee, per conversion


@dataclass
class Position:
    ticker: str
    strategy: str
    entry_date: pd.Timestamp
    entry_idx: int
    entry_fill: float          # native, spread-inclusive
    notional: float            # GBP deployed
    fx_entry: float            # FX rate (units/GBP) at entry; 1.0 for sterling
    is_fx: bool
    stop_level: float          # native price
    tp_level: float            # native price
    hold: int
    lev: bool
    confluence: int


def spread(cfg: Config, lev: bool) -> float:
    return cfg.spread_lev if lev else cfg.spread_plain


def build_scanner_rows(insts, force: bool = False) -> pd.DataFrame:
    if ROWS_CACHE.exists() and not force:
        return pd.read_parquet(ROWS_CACHE)
    frames = []
    for i, (ticker, inst) in enumerate(insts.items(), 1):
        df = L.scan_history(inst)
        if not df.empty:
            frames.append(df)
        if i % 25 == 0:
            print(f"  scanned {i}/{len(insts)} instruments")
    rows = pd.concat(frames, ignore_index=True)
    rows.to_parquet(ROWS_CACHE, index=False)
    return rows


def fx_factor(cfg: Config, currency: str, fx_row) -> tuple[float, bool]:
    """(units-per-GBP rate, is_fx). Sterling names -> (1.0, False)."""
    if not cfg.fx:
        return 1.0, False
    c = (currency or "").upper()
    if c == "USD":
        return float(fx_row["gbpusd"]), True
    if c == "EUR":
        return float(fx_row["gbpeur"]), True
    return 1.0, False  # GBp / GBP


def _exit_today(cfg, p, inst, i, fx_at):
    """Decide and price a position's exit on bar i. Returns (reason, gbp_proceeds)
    or (None, None) if it stays open. GBP proceeds are net of exit spread + FX."""
    o, hi, lo, cl = inst.open[i], inst.high[i], inst.low[i], inst.close[i]
    held = i - p.entry_idx
    sp = spread(cfg, p.lev)
    entry_day = i == p.entry_idx

    def gbp(exit_native):
        fx_now, _ = fx_at(p.ticker, inst, i)
        gross = p.notional * (exit_native / p.entry_fill) * (p.fx_entry / fx_now)
        if p.is_fx:
            gross *= (1 - cfg.fx_fee)  # the sell-side conversion (buy-side at entry)
        return gross

    if cfg.exit_mode == "close_nextopen":
        # v1: act on the PRIOR close at today's open; entry day never exits.
        if entry_day:
            return None, None
        prior_close = inst.close[i - 1]
        reason = None
        if prior_close <= p.stop_level:
            reason = "stop"
        elif prior_close >= p.tp_level:
            reason = "take_profit"
        elif held >= p.hold:
            reason = "time"
        if reason is None:
            return None, None
        return reason, gbp(o * (1 - sp / 2))

    # intraday_hl
    if not entry_day:
        # gap through a level at the open fills at the open
        if o <= p.stop_level:
            return "stop", gbp(o * (1 - sp / 2))
        if o >= p.tp_level:
            return "take_profit", gbp(o * (1 - sp / 2))
    # intraday touch; stop wins ties (conservative)
    hit_stop = lo <= p.stop_level
    hit_tp = hi >= p.tp_level
    if hit_stop:
        return "stop", gbp(p.stop_level * (1 - sp / 2))
    if hit_tp:
        return "take_profit", gbp(p.tp_level * (1 - sp / 2))
    if not entry_day and held >= p.hold:
        return "time", gbp(cl * (1 - sp / 2))
    return None, None


def run(cfg: Config, insts, rows: pd.DataFrame, timeline, idx_maps, fx_df):
    start, end = pd.Timestamp(cfg.start), pd.Timestamp(cfg.end)
    cand = rows[(rows["entry_date"] >= start) & (rows["entry_date"] <= end)].copy()
    by_day = {d: g for d, g in cand.groupby("entry_date")}

    # FX aligned to the union timeline, forward-filled
    fx_aligned = fx_df.set_index("date").reindex(timeline).ffill().bfill()

    def fx_at(ticker, inst, i):
        d = inst.dates[i]
        return fx_factor(cfg, inst.currency, fx_aligned.loc[d])

    cash = cfg.capital
    positions: list[Position] = []
    equity_hist, trades = [], []
    days = timeline[(timeline >= start) & (timeline <= end)]

    for d in days:
        # ---- 1. exits on today's bar ----
        still: list[Position] = []
        for p in positions:
            i = idx_maps[p.ticker].get(d)
            if i is None or i < p.entry_idx:
                still.append(p)
                continue
            reason, proceeds = _exit_today(cfg, p, insts[p.ticker], i, fx_at)
            if reason is None:
                still.append(p)
                continue
            cash += proceeds
            held = i - p.entry_idx
            trades.append({
                "ticker": p.ticker, "strategy": p.strategy, "lev": p.lev,
                "is_fx": p.is_fx, "confluence": p.confluence,
                "entry_date": p.entry_date, "exit_date": d, "held_days": held,
                "notional": p.notional, "pnl": proceeds - p.notional,
                "return_pct": (proceeds / p.notional - 1) * 100, "reason": reason,
            })
        positions = still

        # ---- 2. entries at today's open ----
        held_tickers = {p.ticker for p in positions}
        slots = cfg.max_positions - len(positions)
        if slots > 0 and d in by_day:
            buy = by_day[d]
            ok = (buy["n"].ge(cfg.n_min) & buy["edge"].notna() & buy["mae"].notna()
                  & buy["score"].ge(cfg.min_score) & buy["confluence"].ge(cfg.confluence_min))
            if cfg.uptrend_only:
                ok &= buy["trend_up"].eq(True)
            if cfg.require_green_win:
                ok &= buy["edge_win"].gt(0)
            if cfg.dip_only:
                ok &= buy["style"].eq("dip")
            if cfg.min_abs_z > 0:
                z = buy["z"].to_numpy()
                ok &= ~(np.isfinite(z) & (np.abs(z) < cfg.min_abs_z))
            if cfg.vol_gate == "high":
                ok &= buy["vol_high"].eq(True)
            elif cfg.vol_gate == "low":
                ok &= buy["vol_high"].eq(False)
            if cfg.require_vol_edge:
                ok &= buy["edge_vol"].gt(0)
            edge_bar = np.where(buy["lev"].to_numpy(), cfg.edge_min_lev, cfg.edge_min)
            ok &= buy["edge"].to_numpy() >= edge_bar
            if not cfg.allow_leverage:
                ok &= ~buy["lev"].to_numpy()
            sort_cols = ["score", "confluence"] if cfg.use_confluence_sort else ["score"]
            picks = buy[ok].sort_values(sort_cols, ascending=False)

            opened = 0
            for _, r in picks.iterrows():
                if slots <= 0 or opened >= cfg.max_new_per_day:
                    break
                tk = r["ticker"]
                if tk in held_tickers:
                    continue
                i = idx_maps[tk].get(d)
                if i is None:
                    continue
                inst = insts[tk]
                open_px = inst.open[i]
                if not open_px > 0:
                    continue
                lev = bool(r["lev"])
                equity = cash + sum(
                    pp.notional * (insts[pp.ticker].close[idx_maps[pp.ticker].get(d, pp.entry_idx)]
                                   / pp.entry_fill) * (pp.fx_entry / fx_at(pp.ticker, insts[pp.ticker],
                                   idx_maps[pp.ticker].get(d, pp.entry_idx))[0])
                    for pp in positions)
                # stop distance
                mae_src = r["mae_low"] if cfg.stop_basis == "mae_low" else r["mae"]
                if not np.isfinite(mae_src):
                    mae_src = r["mae"]
                stop_dist = min(max(cfg.stop_mult * abs(mae_src) / 100.0, cfg.stop_min), cfg.stop_max)
                # target distance
                if cfg.target_mode == "mfe_pctl":
                    tgt = r.get(f"mfe_p{cfg.mfe_pctl}", np.nan)
                    if not np.isfinite(tgt) or tgt <= 0:
                        tgt = cfg.tp_r * stop_dist * 100.0
                    tp_dist = tgt / 100.0
                else:
                    tp_dist = cfg.tp_r * stop_dist
                risk_budget = cfg.risk_pct * equity
                notional = min(risk_budget / stop_dist, cfg.pos_cap * equity, cash)
                if notional < cfg.min_ticket:
                    continue
                fx_e, is_fx = fx_at(tk, inst, i)
                sp = spread(cfg, lev)
                entry_fill = open_px * (1 + sp / 2)
                deployed = notional * (1 - cfg.fx_fee) if is_fx else notional  # buy-side FX fee
                positions.append(Position(
                    ticker=tk, strategy=r["strategy"], entry_date=d, entry_idx=i,
                    entry_fill=entry_fill, notional=deployed, fx_entry=fx_e, is_fx=is_fx,
                    stop_level=open_px * (1 - stop_dist), tp_level=open_px * (1 + tp_dist),
                    hold=int(r["hold"]), lev=lev, confluence=int(r["confluence"]),
                ))
                cash -= notional
                held_tickers.add(tk)
                slots -= 1
                opened += 1

        # ---- 3. mark to market at close (GBP) ----
        mtm = 0.0
        for p in positions:
            i = idx_maps[p.ticker].get(d)
            inst = insts[p.ticker]
            px = inst.close[i] if i is not None else inst.close[p.entry_idx]
            fx_now = fx_at(p.ticker, inst, i)[0] if i is not None else p.fx_entry
            mtm += p.notional * (px / p.entry_fill) * (p.fx_entry / fx_now)
        equity_hist.append({"date": d, "equity": cash + mtm, "cash": cash,
                            "n_positions": len(positions)})

    equity_df = pd.DataFrame(equity_hist)
    trades_df = pd.DataFrame(trades)

    # ---- benchmark: IWDA in GBP, one entry cost ----
    bench = insts.get(BENCHMARK)
    if bench is not None:
        bim = idx_maps[BENCHMARK]
        first = days[0]
        bi = bim.get(first)
        if bi is not None:
            sp = spread(cfg, False)
            b0 = bench.open[bi] * (1 + sp / 2)
            fx0 = fx_at(BENCHMARK, bench, bi)[0]
            entry_haircut = (1 - cfg.fx_fee) if (cfg.fx and bench.currency.upper() in ("USD", "EUR")) else 1.0
            bvals = []
            for d in days:
                i = bim.get(d)
                if i is None:
                    bvals.append(np.nan)
                    continue
                fxn = fx_at(BENCHMARK, bench, i)[0]
                bvals.append(cfg.capital * (bench.close[i] / b0) * (fx0 / fxn) * entry_haircut)
            equity_df["benchmark"] = pd.Series(bvals).ffill().values

    return equity_df, trades_df, summarise(cfg, equity_df, trades_df, days)


def summarise(cfg, equity_df, trades_df, days) -> dict:
    eq = equity_df["equity"].to_numpy()
    final = float(eq[-1])
    years = (days[-1] - days[0]).days / 365.25
    cagr = (final / cfg.capital) ** (1 / years) - 1 if years > 0 and final > 0 else float("nan")
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak).min())
    out = {
        "final_equity": round(final, 2),
        "total_return_pct": round((final / cfg.capital - 1) * 100, 1),
        "cagr_pct": round(cagr * 100, 1),
        "max_drawdown_pct": round(max_dd * 100, 1),
        "n_trades": int(len(trades_df)),
    }
    if len(trades_df):
        out["win_rate_pct"] = round((trades_df["return_pct"] > 0).mean() * 100, 1)
        out["avg_trade_pct"] = round(trades_df["return_pct"].mean(), 3)
        out["median_trade_pct"] = round(trades_df["return_pct"].median(), 3)
        out["avg_hold_days"] = round(trades_df["held_days"].mean(), 1)
        out["worst_trade_pct"] = round(trades_df["return_pct"].min(), 1)
        out["exit_reasons"] = trades_df["reason"].value_counts().to_dict()
    if "benchmark" in equity_df:
        b = equity_df["benchmark"].to_numpy()
        out["benchmark_final"] = round(float(b[-1]), 2)
        out["benchmark_return_pct"] = round(float(b[-1] / cfg.capital - 1) * 100, 1)
        bpeak = np.maximum.accumulate(b)
        out["benchmark_max_drawdown_pct"] = round(float(((b - bpeak) / bpeak).min()) * 100, 1)
    return out


if __name__ == "__main__":
    print("loaded backtest module")
