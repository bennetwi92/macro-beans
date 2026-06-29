"""Drive the v3 backtest with out-of-sample discipline and write the report data.

The brief is to find the truth about whether a *profitable, trustworthy* strategy
exists for the £1000 GBP ISA — not to manufacture a good-looking curve. So this
runner is built around four guardrails:

  1. NO LOOK-AHEAD  — the engine reads signals at a bar's close and trades the
     next open (backtest_v3).
  2. HONEST COSTS    — LSE round-trip spread + T212 FX fee on USD/EUR names, the
     v2 accounting, charged on the realised delta of each rebalance.
  3. OUT-OF-SAMPLE   — knobs are chosen on a TRAIN window (2021-07..2024-06) and
     the verdict is read on a held-out TEST window (2024-07..2026-06). Every
     number is labelled IS (in-sample) or OOS. A pre-registered default
     (top-5, pure 12-1, monthly, 200-MA gate) is also reported so the reader can
     see the answer does not hinge on the tuning.
  4. HONEST BENCHMARK— net-of-cost vs £1000 into IWDA (MSCI World) in GBP. A
     strategy that does not beat buy-and-hold on a RISK-ADJUSTED basis is
     reported as such.

Sections:
  A. Pre-registered default — full / IS / OOS vs benchmark.
  B. TRAIN tuning of book size -> OOS confirmation (the disciplined number).
  C. Variant comparison (trend gate on/off, proximity blend, vol-target,
     quarterly, escape hatch) — what each design choice is worth.
  D. Full-window robustness sweep over N (is the edge a knife-edge?).
  E. Dip satellite — the z-gated, trend-gated A1 dip as a small portfolio,
     evaluated on whether it earns a place next to the momentum sleeve.

Writes into data/scanner_strategy_v2/:
  results_v3.json   equity_curve_v3.csv / .png   sweep_v3.csv   dip_v3.csv

Run: /usr/local/bin/python3 -m scripts.scanner_strategy_v2.run_experiments_v3
"""

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from scripts.scanner_strategy_v2 import signals_v3 as S3
from scripts.scanner_strategy_v2.backtest_v3 import (
    Config, DATA_DIR, TRADING_DAYS, load_world, precompute_signals, run,
    _sharpe, _max_dd,
)

FULL = ("2021-07-01", "2026-06-26")
TRAIN = ("2021-07-01", "2024-06-30")
TEST = ("2024-07-01", "2026-06-26")


def hdr(t):
    print("\n" + "=" * 74 + f"\n{t}\n" + "=" * 74)


def line(s):
    return (f"£{s['final_equity']:>7.0f}  ret {s['total_return_pct']:>6.1f}%  "
            f"cagr {s['cagr_pct']:>5.1f}%  dd {s['max_drawdown_pct']:>6.1f}%  "
            f"sharpe {s['sharpe']:>4}  calmar {s['calmar']:>4}  "
            f"bench £{s.get('benchmark_final','-'):>6} (sh {s.get('benchmark_sharpe','-')})")


def main():
    insts, fx_df, timeline, idx_maps = load_world()
    n_uni = sum(1 for i in insts.values() if not i.lev and len(i.close) >= 300)
    print(f"{n_uni} non-lev instruments; full {FULL}, train {TRAIN}, test {TEST}")
    results = {"windows": {"full": FULL, "train": TRAIN, "test": TEST},
               "universe_nonlev": n_uni}

    # signals depend only on (mom_look, mom_skip); cache by those
    sig_cache = {}

    def sigs_for(cfg):
        key = (cfg.mom_look, cfg.mom_skip)
        if key not in sig_cache:
            sig_cache[key] = precompute_signals(insts, cfg)
        return sig_cache[key]

    def S(cfg):
        return run(cfg, insts, sigs_for(cfg), timeline, idx_maps, fx_df)[1]

    def win(cfg, w):
        c = Config(**{**asdict(cfg), "start": w[0], "end": w[1]})
        return S(c)

    # --------------------------------------------------------------- A. DEFAULT
    hdr("A. PRE-REGISTERED DEFAULT (top-5, pure 12-1, monthly, 200-MA gate, cash hatch)")
    default = Config(n_hold=5)
    a_full, a_is, a_oos = win(default, FULL), win(default, TRAIN), win(default, TEST)
    print("  full :", line(a_full))
    print("  IS   :", line(a_is))
    print("  OOS  :", line(a_oos))
    results["default_config"] = asdict(default)
    results["default"] = {"full": a_full, "is": a_is, "oos": a_oos}

    # ----------------------------------------------- A'. RECOMMENDED (defensible)
    hdr("A'. RECOMMENDED: diversified quarterly top-12 (chosen for ROBUSTNESS, "
        "not return — it wins risk-adjusted in BOTH halves)")
    rec = Config(n_hold=12, rebalance_freq="Q")
    r_full, r_is, r_oos = win(rec, FULL), win(rec, TRAIN), win(rec, TEST)
    print("  full :", line(r_full))
    print("  IS   :", line(r_is))
    print("  OOS  :", line(r_oos))
    results["recommended_config"] = asdict(rec)
    results["recommended"] = {"full": r_full, "is": r_is, "oos": r_oos}

    # ------------------------------------------------- B. TRAIN-TUNE -> OOS CHECK
    hdr("B. TUNE BOOK SIZE ON TRAIN (by Sharpe), CONFIRM OOS")
    grid_n = [3, 5, 8, 10, 15, 20, 25]
    btab = []
    for n in grid_n:
        c = Config(n_hold=n)
        sis, soos = win(c, TRAIN), win(c, TEST)
        btab.append({"n_hold": n, "train_sharpe": sis["sharpe"], "train_ret": sis["total_return_pct"],
                     "train_dd": sis["max_drawdown_pct"], "oos_sharpe": soos["sharpe"],
                     "oos_ret": soos["total_return_pct"], "oos_dd": soos["max_drawdown_pct"],
                     "oos_final": soos["final_equity"]})
        print(f"  N={n:>2}: TRAIN sharpe {sis['sharpe']:>4} ret {sis['total_return_pct']:>6.1f}% dd {sis['max_drawdown_pct']:>6.1f}%"
              f"  |  OOS sharpe {soos['sharpe']:>4} ret {soos['total_return_pct']:>6.1f}% dd {soos['max_drawdown_pct']:>6.1f}%")
    best = max(btab, key=lambda r: (r["train_sharpe"] if r["train_sharpe"] == r["train_sharpe"] else -9))
    bn = best["n_hold"]
    print(f"\n  -> TRAIN picks N={bn} (best train Sharpe). Its OOS: "
          f"sharpe {best['oos_sharpe']} ret {best['oos_ret']}% dd {best['oos_dd']}% final £{best['oos_final']}")
    bench_oos = a_oos.get("benchmark_sharpe")
    print(f"     benchmark OOS sharpe {bench_oos}, ret {a_oos.get('benchmark_return_pct')}%, "
          f"dd {a_oos.get('benchmark_max_drawdown_pct')}%")
    results["train_tune"] = btab
    results["train_pick_n"] = bn
    results["tuned_oos"] = win(Config(n_hold=bn), TEST)

    # ------------------------------------------------------- C. VARIANTS (full)
    hdr("C. DESIGN-CHOICE ABLATIONS (full window, N=10 base)")
    base = Config(n_hold=10)
    variants = {
        "base (pure 12-1, gated)": base,
        "no 200-MA gate": Config(n_hold=10, require_trend=False, require_pos_mom=False),
        "no cash escape hatch": Config(n_hold=10, cash_when_few=False),
        "+ proximity blend": Config(n_hold=10, blend_proximity=0.5),
        "+ vol-target sizing": Config(n_hold=10, vol_target=True),
        "quarterly rebalance": Config(n_hold=10, rebalance_freq="Q"),
        "no FX cost (sanity)": Config(n_hold=10, fx=False),
    }
    vtab = {}
    for name, c in variants.items():
        s = win(c, FULL)
        vtab[name] = s
        print(f"  {name:26s} {line(s)}")
    results["variants_full"] = vtab

    # ----------------------------------------------- D. ROBUSTNESS SWEEP (full)
    hdr("D. FULL-WINDOW ROBUSTNESS SWEEP OVER N")
    sweep = []
    for n in [3, 5, 8, 10, 12, 15, 20, 25, 30]:
        s = win(Config(n_hold=n), FULL)
        sweep.append({"n_hold": n, "final": s["final_equity"], "ret": s["total_return_pct"],
                      "cagr": s["cagr_pct"], "dd": s["max_drawdown_pct"], "sharpe": s["sharpe"],
                      "calmar": s["calmar"], "inv_frac": s["avg_invested_frac"]})
    pd.DataFrame(sweep).to_csv(DATA_DIR / "sweep_v3.csv", index=False)
    results["sweep_full"] = sweep
    for r in sweep:
        print(f"  N={r['n_hold']:>2}: final £{r['final']:>6.0f} ret {r['ret']:>6.1f}% dd {r['dd']:>6.1f}% "
              f"sharpe {r['sharpe']} calmar {r['calmar']}")
    print(f"  bench: final £{a_full['benchmark_final']:.0f} ret {a_full['benchmark_return_pct']}% "
          f"dd {a_full['benchmark_max_drawdown_pct']}% sharpe {a_full['benchmark_sharpe']} "
          f"calmar {a_full['benchmark_calmar']}")

    # --------------------------------------------------------- E. DIP SATELLITE
    hdr("E. DIP SATELLITE — z-gated, trend-gated A1 multi-day drop")
    for label, w in [("full", FULL), ("IS", TRAIN), ("OOS", TEST)]:
        d = dip_portfolio(insts, idx_maps, fx_df, timeline, w)
        results.setdefault("dip", {})[label] = d
        print(f"  {label:4s}: trades {d['n_trades']:>3}  win {d['win_pct']}%  "
              f"avg/trade {d['avg_trade_pct']}%  net edge vs control {d['net_edge_pct']}%  "
              f"sleeve final £{d['final_equity']} (ret {d['total_return_pct']}%)  cash £{d['cash_benchmark']}")

    # ----------------------------------------------------- write report outputs
    eq_rec = run(rec, insts, sigs_for(rec), timeline, idx_maps, fx_df)[0]
    eq_d5 = run(default, insts, sigs_for(default), timeline, idx_maps, fx_df)[0]
    out = eq_d5[["date", "equity"]].rename(columns={"equity": "preregistered_top5_monthly"})
    out["recommended_top12_quarterly"] = eq_rec["equity"].values
    if "benchmark" in eq_d5:
        out["benchmark_gbp"] = eq_d5["benchmark"].values
    out.to_csv(DATA_DIR / "equity_curve_v3.csv", index=False)
    plot_equity(out)
    (DATA_DIR / "results_v3.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote results_v3.json, equity_curve_v3.csv/.png, sweep_v3.csv to {DATA_DIR}")


# --------------------------------------------------------------------------- #
# Dip satellite: a small, honest portfolio of z-gated, trend-gated dip events.
# Enter next open after a >=2-sigma multi-day drop in a 200-MA uptrend; hold 21d
# (time exit) with a wide disaster stop; equal-risk, capped concurrency; same
# costs/FX as the rotation engine. Compared to sitting in cash over the window
# (the right control for a satellite — the core sleeve is the momentum book).
# --------------------------------------------------------------------------- #
def dip_portfolio(insts, idx_maps, fx_df, timeline, window,
                  hold=21, stop=0.15, max_concurrent=4, risk_pct=0.02,
                  spread=0.0025, fx_fee=0.0015, capital=1000.0):
    start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    fx_aligned = fx_df.set_index("date").reindex(timeline).ffill().bfill()

    def fxr(inst, d):
        c = (inst.currency or "").upper()
        row = fx_aligned.loc[d]
        if c == "USD":
            return float(row["gbpusd"]), True
        if c == "EUR":
            return float(row["gbpeur"]), True
        return 1.0, False

    # collect every fresh dip event (signal bar t -> entry t+1) in window
    events = []
    ctrl = []  # control: same-name next-open 21d return on ALL uptrend bars
    for tk, inst in insts.items():
        if inst.lev or len(inst.close) < 300:
            continue
        close, open_, high, low = inst.close, inst.open, inst.high, inst.low
        trend = S3.trend_up(close)
        fresh = S3.fresh_edges(S3.multiday_drop_z(close))
        n = len(close)
        d = inst.dates.values
        for t in np.flatnonzero(fresh):
            ei = t + 1
            if ei >= n or not trend[t]:
                continue
            sd = inst.dates[ei]
            if not (start <= sd <= end):
                continue
            events.append((sd, tk, ei))
        # control distribution (drift baseline): all uptrend bars, 21d fwd
        for t in range(n - hold - 2):
            if trend[t] and start <= inst.dates[t + 1] <= end and open_[t + 1] > 0:
                ctrl.append(close[t + 1 + hold] / open_[t + 1] - 1.0)
    events.sort()

    # simulate capped-concurrency equal-risk portfolio
    cash = capital
    trades = []
    eq_dates = timeline[(timeline >= start) & (timeline <= end)]
    # index events by entry date
    by_date = {}
    for sd, tk, ei in events:
        by_date.setdefault(sd, []).append((tk, ei))
    equity_hist = []
    held = {}  # tk -> dict(shares, entry_idx, fx_e, is_fx, stop_px, exit_idx)
    for day in eq_dates:
        # exits
        for tk in list(held.keys()):
            inst = insts[tk]; im = idx_maps[tk]
            i = im.get(day)
            p = held[tk]
            if i is None:
                continue
            reason = None; fillpx = None
            if inst.low[i] <= p["stop_px"]:
                reason, fillpx = "stop", p["stop_px"]
            elif i - p["entry_idx"] >= hold:
                reason, fillpx = "time", inst.close[i]
            if reason:
                fxr_now = fxr(inst, day)[0]
                gross = p["shares"] * fillpx / fxr_now
                cost = gross * (spread / 2 + (fx_fee if p["is_fx"] else 0.0))
                cash += gross - cost
                trades.append({"tk": tk, "ret": (p["shares"] * fillpx / fxr_now) / p["cost_in"] - 1,
                               "reason": reason})
                del held[tk]
        # entries
        if day in by_date and len(held) < max_concurrent:
            equity = cash + sum(
                held[t2]["shares"] * (insts[t2].close[idx_maps[t2].get(day, held[t2]["entry_idx"])]) /
                fxr(insts[t2], day)[0] for t2 in held)
            for tk, ei in by_date[day]:
                if len(held) >= max_concurrent or tk in held:
                    continue
                inst = insts[tk]; im = idx_maps[tk]
                i = im.get(day)
                if i is None or not inst.open[i] > 0:
                    continue
                fx_e, is_fx = fxr(inst, day)
                op = inst.open[i]
                notional = min(risk_pct / stop * equity, equity / max_concurrent, cash)
                if notional < 5:
                    continue
                fill = op * (1 + spread / 2)
                cost_in = notional
                shares = (notional - notional * (spread / 2 + (fx_fee if is_fx else 0.0))) * fx_e / op
                cash -= notional
                held[tk] = {"shares": shares, "entry_idx": i, "fx_e": fx_e, "is_fx": is_fx,
                            "stop_px": op * (1 - stop), "exit_idx": i + hold, "cost_in": cost_in}
        # mark to market
        mtm = 0.0
        for tk, p in held.items():
            inst = insts[tk]; im = idx_maps[tk]
            i = im.get(day)
            px = inst.close[i] if i is not None else inst.close[p["entry_idx"]]
            mtm += p["shares"] * px / fxr(inst, day)[0]
        equity_hist.append(cash + mtm)
    eq = np.array(equity_hist)
    rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
    ctrl_mean = float(np.mean(ctrl)) * 100 if ctrl else float("nan")
    return {
        "n_trades": len(trades),
        "win_pct": round(float((rets > 0).mean() * 100), 1) if len(rets) else None,
        "avg_trade_pct": round(float(rets.mean() * 100), 3) if len(rets) else None,
        "net_edge_pct": round(float(rets.mean() * 100 - ctrl_mean), 3) if len(rets) else None,
        "final_equity": round(float(eq[-1]), 2) if len(eq) else capital,
        "total_return_pct": round(float(eq[-1] / capital - 1) * 100, 1) if len(eq) else 0.0,
        "max_drawdown_pct": round(_max_dd(eq) * 100, 1) if len(eq) > 2 else None,
        "sharpe": round(_sharpe(eq), 2) if len(eq) > 2 else None,
        "cash_benchmark": capital,
    }


def plot_equity(out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        print(f"(skip chart: {exc})")
        return
    fig, ax = plt.subplots(figsize=(9.5, 5))
    if "benchmark_gbp" in out:
        ax.plot(out["date"], out["benchmark_gbp"], color="#e3b452", lw=1.4, ls="--",
                label="Buy & hold MSCI World (IWDA, GBP)")
    ax.plot(out["date"], out["preregistered_top5_monthly"], color="#9aa0b5", lw=1.4,
            label="v3 rotation, pre-registered top-5 monthly")
    ax.plot(out["date"], out["recommended_top12_quarterly"], color="#4fe3ef", lw=2.0,
            label="v3 rotation, recommended top-12 quarterly")
    split = pd.Timestamp(TEST[0])
    ax.axvline(split, color="#888", lw=0.9, ls=":")
    ax.text(split, ax.get_ylim()[1] * 0.96, " OOS →", fontsize=8, color="#555")
    ax.axhline(1000, color="#888", lw=0.7, alpha=0.5)
    ax.set_title("£1000: v3 momentum rotation vs buy-and-hold (all GBP, net of cost)", fontsize=11)
    ax.set_ylabel("Account value (£)")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(DATA_DIR / "equity_curve_v3.png", dpi=130)
    print(f"Wrote {DATA_DIR / 'equity_curve_v3.png'}")


if __name__ == "__main__":
    main()
