"""Drive the v2 backtest: validate the v1 replica, attribute every change, and
build the final v2 on a like-for-like honest basis.

The central finding (see the report) is that v1's headline was inflated by an
unrealistic close-only stop. So every comparison here runs on ONE current
dataset, and the fair yardstick is v1's own rules under honest intraday
accounting — not v1's published number.

Writes into data/scanner_strategy_v2/:
  results.json   all tables (the report reads this)
  equity_curve.csv / .png   v1 / v1-honest / v2 / GBP benchmark
  by_year.csv  by_strategy.csv  trades_v2.csv

Run: /usr/local/bin/python3 -m scripts.scanner_strategy_v2.run_experiments
"""

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from scripts.scanner_strategy_v2 import scanner_lib as L
from scripts.scanner_strategy_v2.backtest import (
    Config, DATA_DIR, PRICES, FX, build_scanner_rows, run,
)

# --- canonical config fragments ---------------------------------------------
HONEST = dict(exit_mode="intraday_hl", stop_basis="mae_low", fx=True)
WIDE_STOP = dict(stop_min=0.05, stop_max=0.20, stop_mult=2.0)


def hdr(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def line(s):
    return (f"£{s['final_equity']:>7.1f}  ret {s['total_return_pct']:>6.1f}%  "
            f"cagr {s['cagr_pct']:>5.1f}%  dd {s['max_drawdown_pct']:>6.1f}%  "
            f"n {s['n_trades']:>4}  win {s.get('win_rate_pct','-')}%  "
            f"avg {s.get('avg_trade_pct','-')}%  bench £{s.get('benchmark_final','-')}")


def main():
    print("Loading prices + FX ...")
    prices = pd.read_parquet(PRICES)
    fx_df = pd.read_parquet(FX)
    insts = L.build_instruments(prices)
    timeline = pd.DatetimeIndex(sorted(prices["date"].unique()))
    idx_maps = {tk: {d: i for i, d in enumerate(inst.dates)} for tk, inst in insts.items()}
    rows = build_scanner_rows(insts)
    print(f"  {len(rows):,} fresh rows; "
          f"{rows['entry_date'].between('2021-07-01','2026-06-26').sum():,} in window")

    def R(cfg):
        return run(cfg, insts, rows, timeline, idx_maps, fx_df)

    def S(cfg):
        return R(cfg)[2]

    results = {}

    # ---------------------------------------------------------- ACCOUNTING TRUTH
    hdr("ACCOUNTING: v1 rules under v1 (optimistic) vs honest intraday")
    s_v1 = S(Config())
    s_v1h = S(Config(**HONEST))
    print("  v1 rules / v1 close-only acct :", line(s_v1))
    print("  v1 rules / honest intraday acct:", line(s_v1h))
    results["v1_optimistic"] = s_v1
    results["v1_honest"] = s_v1h

    # ----------------------------------------------- SINGLE CHANGE FROM V1 (acct)
    hdr("EACH ACCOUNTING/METHOD CHANGE IN ISOLATION (from v1)")
    singles = {
        "intraday_hl_only": Config(exit_mode="intraday_hl", stop_basis="mae_low"),
        "fx_only": Config(fx=True),
        "confluence2_only": Config(confluence_min=2),
        "widestop_only": Config(**WIDE_STOP),
    }
    sing = {n: S(c) for n, c in singles.items()}
    for n, s in sing.items():
        print(f"  {n:20s} {line(s)}")
    results["single_changes"] = sing

    # ------------------------- MFE PERCENTILE SWEEP (on the PROPER v2 base) -----
    hdr("MFE PERCENTILE SWEEP (honest + conf>=2 + wide stop) -> the target dial")
    base = dict(**HONEST, **WIDE_STOP, confluence_min=2)
    sweep = []
    for p in [30, 40, 50, 60, 70, 75, 80]:
        _, tr, s = R(Config(target_mode="mfe_pctl", mfe_pctl=p, **base))
        tp = (tr["reason"] == "take_profit").mean() * 100 if len(tr) else 0
        rec = {"pctl": p, "final": s["final_equity"], "ret": s["total_return_pct"],
               "dd": s["max_drawdown_pct"], "n": s["n_trades"], "win": s.get("win_rate_pct"),
               "avg": s.get("avg_trade_pct"), "tp_hit_rate": round(tp, 1)}
        sweep.append(rec)
        print(f"  p{p:>2}: final £{rec['final']:>7.1f}  ret {rec['ret']:>6.1f}%  "
              f"win {rec['win']}%  avg {rec['avg']}%  tp-hit {rec['tp_hit_rate']}%  n {rec['n']}")
    # reference points
    s_fixed = S(Config(tp_r=3.0, **base))
    s_notgt = S(Config(tp_r=99, **base))
    print(f"  fixed 3R : {line(s_fixed)}")
    print(f"  no target: {line(s_notgt)}")
    results["mfe_sweep"] = sweep
    results["mfe_fixed3r"] = s_fixed
    results["mfe_notarget"] = s_notgt
    best_p = max(sweep, key=lambda r: r["final"])["pctl"]
    results["mfe_best_pctl"] = best_p
    print(f"  -> best percentile by final equity: p{best_p}")

    # ----------------------------------------------------------- CONFLUENCE -----
    hdr("CONFLUENCE (feedback said drop it; test whether it earns its place)")
    v2base = dict(**HONEST, **WIDE_STOP, target_mode="mfe_pctl", mfe_pctl=best_p)
    conf = {}
    for n, k in {"conf1 (off)": {"confluence_min": 1},
                 "conf2": {"confluence_min": 2},
                 "conf3": {"confluence_min": 3}}.items():
        conf[n] = S(Config(**v2base, **k))
        print(f"  {n:12s} {line(conf[n])}")
    results["confluence_runs"] = conf
    # descriptive split by confluence and by setup strength
    _, tr_c, _ = R(Config(**v2base, confluence_min=1))
    if len(tr_c):
        tr_c["bucket"] = np.where(tr_c["confluence"] >= 2, "conf>=2", "conf==1")
        cb = tr_c.groupby("bucket").agg(
            trades=("return_pct", "size"),
            win=("return_pct", lambda x: round((x > 0).mean() * 100, 1)),
            avg=("return_pct", lambda x: round(x.mean(), 3)),
            total_pnl=("pnl", lambda x: round(x.sum(), 2))).reset_index()
        results["confluence_descriptive"] = cb.to_dict("records")
        print(cb.to_string(index=False))
        weak = tr_c[tr_c["strategy"] != "bounce"]
        if len(weak):
            wb = weak.groupby(np.where(weak["confluence"] >= 2, "conf>=2", "conf==1")).agg(
                trades=("return_pct", "size"),
                win=("return_pct", lambda x: round((x > 0).mean() * 100, 1)),
                avg=("return_pct", lambda x: round(x.mean(), 3))).reset_index(names="bucket")
            results["confluence_weak_setups"] = wb.to_dict("records")
            print("  non-bounce (weak) setups only:")
            print(wb.to_string(index=False))

    # ------------------------------------------------------ VOLATILITY REGIME ----
    hdr("VOLATILITY REGIME (does conditioning add edge?)")
    vol = {}
    for n, k in {"vol_off": {}, "vol_high": {"vol_gate": "high"},
                 "vol_low": {"vol_gate": "low"},
                 "require_vol_edge": {"require_vol_edge": True}}.items():
        vol[n] = S(Config(**v2base, confluence_min=2, **k))
        print(f"  {n:16s} {line(vol[n])}")
    results["vol_runs"] = vol
    # descriptive: forward edge by regime (is the EDGE itself regime-dependent?)
    w = rows[rows["entry_date"].between("2021-07-01", "2026-06-26") & rows["edge"].notna()
             & rows["trend_up"].eq(True) & rows["n"].ge(15)]
    desc = {}
    for lab, m in {"high_vol": w["vol_high"].eq(True), "low_vol": w["vol_high"].eq(False)}.items():
        g = w[m]
        desc[lab] = {"rows": int(len(g)), "mean_edge_pct": round(float(g["edge"].mean()), 3)}
    results["vol_descriptive"] = desc
    print("  forward edge by regime:", desc)

    # -------------------------------------------------------------- HORIZONS -----
    hdr("HORIZON STUDY (per-day edge by hold; do more horizons help?)")
    hs = horizon_analysis(insts)
    results["horizon_study"] = hs
    for setup, tbl in hs.items():
        valid = [r for r in tbl if r["per_day_edge"] is not None]
        best = max(valid, key=lambda r: r["per_day_edge"]) if valid else {"hold": None, "per_day_edge": None}
        print(f"  {setup:9s} current={L.HOLD[setup]:>2}  best per-day-edge hold={best['hold']}  "
              f"(edge/day {best['per_day_edge']})")

    # ------------------------------------------------------ FINAL V2 vs V1 -------
    hdr("FINAL V2")
    v2cfg = Config(**HONEST, **WIDE_STOP, target_mode="mfe_pctl", mfe_pctl=best_p,
                   confluence_min=2)
    v2scfg = Config(**HONEST, **WIDE_STOP, target_mode="mfe_pctl", mfe_pctl=best_p,
                    confluence_min=2, vol_gate="low")
    eq1, _, _ = R(Config())                       # v1 optimistic (for the chart)
    eq1h, _, s1h = R(Config(**HONEST))            # v1 honest
    eq2, tr2, s2 = R(v2cfg)                        # v2 core
    _, _, s2s = R(v2scfg)                          # v2 selective (+vol_low)
    results["v2_config"] = asdict(v2cfg)
    results["v2"] = s2
    results["v2_selective"] = s2s
    print("  v1 optimistic :", line(results["v1_optimistic"]))
    print("  v1 honest     :", line(s1h))
    print("  v2 core       :", line(s2))
    print("  v2 selective  :", line(s2s))

    if len(tr2):
        g = tr2.groupby("strategy")
        bp = pd.DataFrame({
            "trades": g.size(),
            "win_pct": g["return_pct"].apply(lambda x: round((x > 0).mean() * 100, 1)),
            "avg_ret_pct": g["return_pct"].mean().round(3),
            "total_pnl": g["pnl"].sum().round(2),
            "avg_hold_days": g["held_days"].mean().round(1),
        }).sort_values("total_pnl", ascending=False)
        bp.to_csv(DATA_DIR / "by_strategy.csv")
        results["v2_by_strategy"] = bp.reset_index().to_dict("records")
        print(bp.to_string())
        tr2.to_csv(DATA_DIR / "trades_v2.csv", index=False)
        results["v2_exit_reasons"] = s2.get("exit_reasons", {})

    write_by_year(eq2, results)
    plot_equity(eq1, eq1h, eq2)
    save_equity(eq1, eq1h, eq2)
    (DATA_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote results.json + CSVs + PNG to {DATA_DIR}")


def horizon_analysis(insts, holds=(2, 3, 5, 7, 10, 15, 20)):
    from scripts.scanner_strategy.scanner_lib import _trigger_arrays
    from scripts.scanner_strategy_v2.scanner_lib import sma
    start, end = np.datetime64("2021-07-01"), np.datetime64("2026-06-26")
    out = {}
    for setup in L.HOLD:
        out[setup] = []
        for h in holds:
            ev, ba = [], []
            for inst in insts.values():
                close, open_ = inst.close, inst.open
                n = len(close)
                if n < 260:
                    continue
                ma = sma(close, 200)
                up = np.isfinite(ma) & (close >= ma)
                trig = _trigger_arrays(close)[setup]
                fresh = trig.copy()
                fresh[1:] = trig[1:] & ~trig[:-1]
                fwd, valid = _fwd_h(open_, close, h)
                d = inst.dates.values
                m = valid & up & (d >= start) & (d <= end)
                ba.append(fwd[m]); ev.append(fwd[m & fresh])
            bf = np.concatenate(ba) if ba else np.array([])
            ef = np.concatenate(ev) if ev else np.array([])
            if len(ef) >= 30 and len(bf):
                edge = (ef.mean() - bf.mean()) * 100
                out[setup].append({"hold": h, "n": int(len(ef)),
                                   "edge": round(edge, 3), "per_day_edge": round(edge / h, 4)})
            else:
                out[setup].append({"hold": h, "n": int(len(ef)), "edge": None, "per_day_edge": None})
    return out


def _fwd_h(open_, close, hold):
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


def write_by_year(equity_df, results):
    e = equity_df.set_index("date")
    yr, yrf = e.resample("YE").last(), e.resample("YE").first()
    rows = []
    for d in yr.index:
        rec = {"year": d.year,
               "strategy_ret_pct": round((yr.loc[d, "equity"] / yrf.loc[d, "equity"] - 1) * 100, 1)}
        if "benchmark" in e:
            rec["benchmark_ret_pct"] = round((yr.loc[d, "benchmark"] / yrf.loc[d, "benchmark"] - 1) * 100, 1)
        rows.append(rec)
    pd.DataFrame(rows).to_csv(DATA_DIR / "by_year.csv", index=False)
    results["v2_by_year"] = rows


def save_equity(eq1, eq1h, eq2):
    out = eq2[["date", "equity"]].rename(columns={"equity": "v2"}).copy()
    out["v1_optimistic"] = eq1["equity"].values
    out["v1_honest"] = eq1h["equity"].values
    if "benchmark" in eq2:
        out["benchmark_gbp"] = eq2["benchmark"].values
    out.to_csv(DATA_DIR / "equity_curve.csv", index=False)


def plot_equity(eq1, eq1h, eq2):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"(skip chart: {exc})")
        return
    fig, ax = plt.subplots(figsize=(9, 4.8))
    if "benchmark" in eq2:
        ax.plot(eq2["date"], eq2["benchmark"], color="#e3b452", lw=1.3, ls="--",
                label="Buy & hold MSCI World (GBP)")
    ax.plot(eq1["date"], eq1["equity"], color="#9aa0b5", lw=1.2,
            label="v1 (optimistic close-only stop)")
    ax.plot(eq1h["date"], eq1h["equity"], color="#f06673", lw=1.3,
            label="v1 rules, honest intraday accounting")
    ax.plot(eq2["date"], eq2["equity"], color="#4fe3ef", lw=2.0, label="v2 (honest)")
    ax.axhline(1000, color="#888", lw=0.7, alpha=0.5)
    ax.set_title("£1000: Scanner v2 vs v1 vs buy-and-hold (all GBP)", fontsize=11)
    ax.set_ylabel("Account value (£)")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(DATA_DIR / "equity_curve.png", dpi=130)
    print(f"Wrote {DATA_DIR / 'equity_curve.png'}")


if __name__ == "__main__":
    main()
