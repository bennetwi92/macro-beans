"""Backtest the Scanner trade-picking playbook on a simulated £1000 ISA.

Replays the Macro Beans Scanner day by day (no look-ahead) and trades it under
the rules in docs/guides/scanner_trade_strategy.md, modelling a Trading 212
Stocks & Shares ISA:

  * No commission — the only cost is the bid/ask spread (assumed below).
  * No OCO: each position carries a real resting STOP order plus a take-profit
    ALERT the trader actions the next morning. Modelled here as a once-a-day
    morning check that exits at the next open on a stop breach, a target breach,
    or the setup's hold horizon — whichever comes first.
  * Positions sized by risk: each trade risks a fixed % of equity to a stop set
    from the setup's own MAE (so the stop sits beyond the noise it usually
    needs). Fractional shares (T212 supports them) so size is exact.

Selection mirrors the guide's daily routine: New today, Uptrend, Same-trend
stats, 5-year track record; take the highest-scoring rows that clear an EDGE,
sample-size and "green WIN%" bar, leveraged (⚡) names only on a higher EDGE bar.

Run (after fetch_prices.py):
    /usr/local/bin/python3 scripts/scanner_strategy/backtest.py

Outputs (data/scanner_strategy/):
    equity_curve.csv   date, equity, cash, n_positions, benchmark
    trades.csv         one row per closed trade
    summary.json       headline metrics + the config used
    sensitivity.csv    headline metrics across parameter variants
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from scripts.scanner_strategy import scanner_lib as L  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "scanner_strategy"
PRICES = DATA_DIR / "prices.parquet"
ROWS_CACHE = DATA_DIR / "scanner_rows.parquet"
BENCHMARK = "IWDA.L"  # MSCI World — the honest "just buy the market" yardstick


@dataclass
class Config:
    start: str = "2021-07-01"          # 5y track record fully available from here
    end: str = "2026-06-26"
    capital: float = 1000.0
    # selection
    edge_min: float = 0.30             # min EDGE % (total over the hold) for plain names
    edge_min_lev: float = 1.00         # higher bar for leveraged ⚡ names
    n_min: int = 15                    # min sample size (Scanner ⚠ is <10)
    require_green_win: bool = True     # WIN% must beat the instrument's own baseline
    uptrend_only: bool = True          # only buy names above their 200-day average
    allow_leverage: bool = False       # ⚡ off in the backtest: Yahoo's LSE
    #                                    leveraged-ETP history has un-flagged
    #                                    reverse splits that fake ±100%+ moves.
    #                                    The live rule still allows ⚡ on a higher
    #                                    EDGE bar (the Scanner uses clean prices).
    dip_only: bool = False             # restrict to mean-reversion (buy-weakness) setups
    min_score: float = 0.0             # min ranking score (per-day edge x shrink)
    min_abs_z: float = 0.0             # min |z| for dip setups that have a z (0 = off)
    max_new_per_day: int = 99          # cap fresh entries opened in one morning
    max_positions: int = 6
    # sizing (risk-based off MAE)
    risk_pct: float = 0.015            # capital at risk per trade
    stop_mult: float = 1.4             # stop sits this multiple beyond avg MAE
    stop_min: float = 0.03             # floor / cap on the stop distance
    stop_max: float = 0.12
    pos_cap: float = 0.40              # max fraction of equity in one position
    tp_r: float = 3.0                  # take-profit distance = tp_r x stop distance
    #                                    (wide: an opportunistic alert, not a
    #                                    tight cap that clips the trend tailwind)
    min_ticket: float = 5.0            # don't bother opening sub-£5 positions
    # costs
    spread_plain: float = 0.0025       # round-trip spread, plain ETFs (0.25%)
    spread_lev: float = 0.0060         # round-trip spread, leveraged ETFs (0.60%)


@dataclass
class Position:
    ticker: str
    strategy: str
    entry_date: pd.Timestamp
    entry_idx: int
    entry_fill: float
    notional: float          # £ deployed at entry (after entry-side spread)
    stop_level: float        # price level (raw, pre-spread)
    tp_level: float
    hold: int
    lev: bool


def build_scanner_rows(insts: dict[str, L.Instrument], force: bool = False) -> pd.DataFrame:
    """All fresh Scanner rows across every instrument (cached)."""
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


def spread(cfg: Config, lev: bool) -> float:
    return cfg.spread_lev if lev else cfg.spread_plain


def run(cfg: Config, insts: dict[str, L.Instrument], rows: pd.DataFrame,
        timeline: pd.DatetimeIndex, idx_maps: dict[str, dict]):
    """Simulate the account. Returns (equity_df, trades_df, summary dict)."""
    start = pd.Timestamp(cfg.start)
    end = pd.Timestamp(cfg.end)

    # candidate rows by the morning they'd be acted on (entry_date == that day)
    cand = rows[(rows["entry_date"] >= start) & (rows["entry_date"] <= end)].copy()
    by_day = {d: g for d, g in cand.groupby("entry_date")}

    cash = cfg.capital
    positions: list[Position] = []
    equity_hist = []
    trades = []

    days = timeline[(timeline >= start) & (timeline <= end)]

    for d in days:
        # ---- 1. morning management: stop / take-profit / time exit at the open ----
        still_open: list[Position] = []
        for p in positions:
            im = idx_maps[p.ticker]
            i = im.get(d)
            if i is None or i == 0:
                still_open.append(p)
                continue
            inst = insts[p.ticker]
            prior_close = inst.close[i - 1]
            today_open = inst.open[i]
            held = i - p.entry_idx
            reason = None
            if prior_close <= p.stop_level:
                reason = "stop"
            elif prior_close >= p.tp_level:
                reason = "take_profit"
            elif held >= p.hold:
                reason = "time"
            if reason is None:
                still_open.append(p)
                continue
            # exit at today's open, minus exit-side spread
            sp = spread(cfg, p.lev)
            exit_fill = today_open * (1 - sp / 2)
            proceeds = p.notional * (exit_fill / p.entry_fill)
            cash += proceeds
            ret = proceeds / p.notional - 1
            trades.append({
                "ticker": p.ticker, "strategy": p.strategy, "lev": p.lev,
                "entry_date": p.entry_date, "exit_date": d, "held_days": held,
                "entry_fill": p.entry_fill, "exit_fill": exit_fill,
                "notional": p.notional, "pnl": proceeds - p.notional,
                "return_pct": ret * 100, "reason": reason,
            })
        positions = still_open

        # ---- 2. selection: open new positions from today's buy list ----
        held_tickers = {p.ticker for p in positions}
        slots = cfg.max_positions - len(positions)
        if slots > 0 and d in by_day:
            buy = by_day[d]
            ok = (
                buy["n"].ge(cfg.n_min)
                & buy["edge"].notna()
                & buy["mae"].notna()
                & buy["score"].ge(cfg.min_score)
            )
            if cfg.uptrend_only:
                ok &= buy["trend_up"].eq(True)
            if cfg.require_green_win:
                ok &= buy["edge_win"].gt(0)
            if cfg.dip_only:
                ok &= buy["style"].eq("dip")
            if cfg.min_abs_z > 0:
                # only applies to setups that carry a z (bounce / multi-day); a
                # NaN z (streaks, breakouts, …) is left untouched by this gate
                z = buy["z"].to_numpy()
                ok &= ~(np.isfinite(z) & (np.abs(z) < cfg.min_abs_z))
            # EDGE bar: higher for leveraged names; leverage may be disabled
            edge_bar = np.where(buy["lev"].to_numpy(), cfg.edge_min_lev, cfg.edge_min)
            ok &= buy["edge"].to_numpy() >= edge_bar
            if not cfg.allow_leverage:
                ok &= ~buy["lev"].to_numpy()
            picks = buy[ok].sort_values(["score", "confluence"], ascending=False)

            opened_today = 0
            for _, r in picks.iterrows():
                if slots <= 0 or opened_today >= cfg.max_new_per_day:
                    break
                tk = r["ticker"]
                if tk in held_tickers:
                    continue
                im = idx_maps[tk]
                i = im.get(d)
                if i is None:
                    continue
                inst = insts[tk]
                open_px = inst.open[i]
                if not open_px > 0:
                    continue
                lev = bool(r["lev"])
                equity = cash + sum(
                    pp.notional * (insts[pp.ticker].close[idx_maps[pp.ticker].get(d, pp.entry_idx)]
                                   / pp.entry_fill)
                    for pp in positions
                )
                stop_dist = min(max(cfg.stop_mult * abs(r["mae"]) / 100.0, cfg.stop_min), cfg.stop_max)
                tp_dist = cfg.tp_r * stop_dist
                risk_budget = cfg.risk_pct * equity
                notional = risk_budget / stop_dist
                notional = min(notional, cfg.pos_cap * equity, cash)
                if notional < cfg.min_ticket:
                    continue
                sp = spread(cfg, lev)
                entry_fill = open_px * (1 + sp / 2)
                positions.append(Position(
                    ticker=tk, strategy=r["strategy"], entry_date=d, entry_idx=i,
                    entry_fill=entry_fill, notional=notional,
                    stop_level=open_px * (1 - stop_dist),
                    tp_level=open_px * (1 + tp_dist),
                    hold=int(r["hold"]), lev=lev,
                ))
                cash -= notional
                held_tickers.add(tk)
                slots -= 1
                opened_today += 1

        # ---- 3. mark to market at the close ----
        mtm = 0.0
        for p in positions:
            i = idx_maps[p.ticker].get(d)
            px = insts[p.ticker].close[i] if i is not None else insts[p.ticker].close[p.entry_idx]
            mtm += p.notional * (px / p.entry_fill)
        equity_hist.append({"date": d, "equity": cash + mtm, "cash": cash,
                            "n_positions": len(positions)})

    equity_df = pd.DataFrame(equity_hist)
    trades_df = pd.DataFrame(trades)

    # benchmark: £capital into MSCI World at the first day's open, marked to close
    bench = insts.get(BENCHMARK)
    if bench is not None:
        bim = idx_maps[BENCHMARK]
        first = days[0]
        bi = bim.get(first)
        b0 = bench.open[bi] if bi is not None else bench.close[bim[min(bim)]]
        bvals = []
        for d in days:
            i = bim.get(d)
            px = bench.close[i] if i is not None else np.nan
            bvals.append(cfg.capital * px / b0)
        equity_df["benchmark"] = pd.Series(bvals).ffill().values

    summary = summarise(cfg, equity_df, trades_df, days)
    return equity_df, trades_df, summary


def summarise(cfg, equity_df, trades_df, days) -> dict:
    eq = equity_df["equity"].to_numpy()
    final = float(eq[-1])
    total_ret = final / cfg.capital - 1
    years = (days[-1] - days[0]).days / 365.25
    cagr = (final / cfg.capital) ** (1 / years) - 1 if years > 0 and final > 0 else float("nan")
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak).min())
    out = {
        "start": cfg.start, "end": cfg.end, "years": round(years, 2),
        "final_equity": round(final, 2),
        "total_return_pct": round(total_ret * 100, 1),
        "cagr_pct": round(cagr * 100, 1),
        "max_drawdown_pct": round(max_dd * 100, 1),
        "n_trades": int(len(trades_df)),
    }
    if len(trades_df):
        out["win_rate_pct"] = round((trades_df["return_pct"] > 0).mean() * 100, 1)
        out["avg_trade_pct"] = round(trades_df["return_pct"].mean(), 2)
        out["median_trade_pct"] = round(trades_df["return_pct"].median(), 2)
        out["avg_hold_days"] = round(trades_df["held_days"].mean(), 1)
        out["best_trade_pct"] = round(trades_df["return_pct"].max(), 1)
        out["worst_trade_pct"] = round(trades_df["return_pct"].min(), 1)
        out["exit_reasons"] = trades_df["reason"].value_counts().to_dict()
        out["pct_leveraged_trades"] = round(trades_df["lev"].mean() * 100, 1)
    if "benchmark" in equity_df:
        b = equity_df["benchmark"].to_numpy()
        out["benchmark_final"] = round(float(b[-1]), 2)
        out["benchmark_return_pct"] = round(float(b[-1] / cfg.capital - 1) * 100, 1)
        bpeak = np.maximum.accumulate(b)
        out["benchmark_max_drawdown_pct"] = round(float(((b - bpeak) / bpeak).min()) * 100, 1)
    return out


def write_breakdowns(equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> None:
    """Per-calendar-year strategy vs benchmark, and per-setup trade stats."""
    e = equity_df.set_index("date")
    yr = e.resample("YE").last()
    yr_first = e.resample("YE").first()
    rows = []
    for d in yr.index:
        y = d.year
        s0 = yr_first.loc[d, "equity"]; s1 = yr.loc[d, "equity"]
        rec = {"year": y, "strategy_ret_pct": round((s1 / s0 - 1) * 100, 1)}
        if "benchmark" in e:
            b0 = yr_first.loc[d, "benchmark"]; b1 = yr.loc[d, "benchmark"]
            rec["benchmark_ret_pct"] = round((b1 / b0 - 1) * 100, 1)
        rows.append(rec)
    pd.DataFrame(rows).to_csv(DATA_DIR / "by_year.csv", index=False)

    if len(trades_df):
        g = trades_df.groupby("strategy")
        bp = pd.DataFrame({
            "trades": g.size(),
            "win_pct": (g["return_pct"].apply(lambda x: (x > 0).mean() * 100)).round(1),
            "avg_ret_pct": g["return_pct"].mean().round(2),
            "total_pnl": g["pnl"].sum().round(2),
            "avg_hold_days": g["held_days"].mean().round(1),
        }).sort_values("total_pnl", ascending=False)
        bp.to_csv(DATA_DIR / "by_strategy.csv")
        print("\nBy setup:\n", bp.to_string())


def plot_equity(equity_df: pd.DataFrame) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"(skipping chart: {exc})")
        return
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(equity_df["date"], equity_df["equity"], color="#58cdd6", lw=1.8,
            label="Scanner strategy")
    if "benchmark" in equity_df:
        ax.plot(equity_df["date"], equity_df["benchmark"], color="#82839a", lw=1.4,
                ls="--", label="Buy & hold MSCI World (IWDA)")
    ax.axhline(1000, color="#e3b452", lw=0.8, alpha=0.6)
    ax.set_title("£1000 traded on the Scanner vs buy-and-hold", fontsize=11)
    ax.set_ylabel("Account value (£)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(DATA_DIR / "equity_curve.png", dpi=130)
    print(f"Wrote {DATA_DIR / 'equity_curve.png'}")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading prices ...")
    prices = pd.read_parquet(PRICES)
    insts = L.build_instruments(prices)
    timeline = pd.DatetimeIndex(sorted(prices["date"].unique()))
    idx_maps = {tk: {d: i for i, d in enumerate(inst.dates)} for tk, inst in insts.items()}

    print("Building Scanner rows (this replays every setup over all history) ...")
    rows = build_scanner_rows(insts)
    print(f"  {len(rows):,} fresh Scanner rows total")

    cfg = Config()
    print(f"\nRunning base backtest {cfg.start} .. {cfg.end} ...")
    equity_df, trades_df, summary = run(cfg, insts, rows, timeline, idx_maps)

    equity_df.to_csv(DATA_DIR / "equity_curve.csv", index=False)
    trades_df.to_csv(DATA_DIR / "trades.csv", index=False)
    (DATA_DIR / "summary.json").write_text(
        json.dumps({"config": asdict(cfg), "summary": summary}, indent=2, default=str))

    print("\n=== BASE CASE (recommended config) ===")
    for k, v in summary.items():
        print(f"  {k:28s} {v}")

    # ---- per-year strategy vs benchmark + per-setup breakdown + chart ----
    write_breakdowns(equity_df, trades_df)
    plot_equity(equity_df)

    # ---- sensitivity: vary one lever at a time ----
    print("\nRunning sensitivity variants ...")
    variants = {
        "base": cfg,
        # --- selectivity (the dominant lever: fewer, bigger-edge trades) ---
        "score_0.05": Config(min_score=0.05),
        "score_0.10": Config(min_score=0.10),
        "new_per_day_2": Config(max_new_per_day=2),
        "new_per_day_1": Config(max_new_per_day=1),
        "dip_only": Config(dip_only=True),
        "extreme_z_2": Config(min_abs_z=2.0),
        "edge_min_0.6": Config(edge_min=0.6),
        "edge_min_1.0": Config(edge_min=1.0),
        "n_min_25": Config(n_min=25),
        # --- the selective combo the report recommends ---
        "selective": Config(min_score=0.05, max_new_per_day=2, edge_min=0.5, n_min=20),
        # --- risk / sizing / cost robustness ---
        "risk_1pct": Config(risk_pct=0.01),
        "risk_3pct": Config(risk_pct=0.03),
        "with_leverage": Config(allow_leverage=True),
        "tp_2.0R": Config(tp_r=2.0),
        "tp_1.0R": Config(tp_r=1.0),
        "maxpos_4": Config(max_positions=4),
        "spread_0.10pct": Config(spread_plain=0.0010),
        "spread_0.50pct": Config(spread_plain=0.0050),
        "stop_mult_1.0": Config(stop_mult=1.0),
        "stop_mult_1.6": Config(stop_mult=1.6),
    }
    sens = []
    for name, c in variants.items():
        _, td, s = run(c, insts, rows, timeline, idx_maps)
        sens.append({"variant": name, **s})
        print(f"  {name:16s} final £{s['final_equity']:>8.2f}  "
              f"ret {s['total_return_pct']:>6.1f}%  dd {s['max_drawdown_pct']:>6.1f}%  "
              f"trades {s['n_trades']}")
    sens_df = pd.DataFrame(sens)
    keep = ["variant", "final_equity", "total_return_pct", "cagr_pct",
            "max_drawdown_pct", "n_trades", "win_rate_pct", "avg_trade_pct"]
    sens_df[[c for c in keep if c in sens_df.columns]].to_csv(
        DATA_DIR / "sensitivity.csv", index=False)
    print(f"\nWrote outputs to {DATA_DIR}")


if __name__ == "__main__":
    main()
