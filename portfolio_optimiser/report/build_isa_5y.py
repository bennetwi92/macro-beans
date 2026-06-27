"""Five-year ISA options — build three horizon-appropriate allocations.

A bespoke driver for a specific mandate that the standing ISA/SIPP profiles in
``config/constraints.toml`` do **not** cover:

    * ~GBP 20,000 transferred into a Trading 212 Stocks & Shares ISA;
    * a single 5-year horizon, after which the whole pot is withdrawn;
    * fully invested (an emergency-cash buffer sits OUTSIDE this pot, so no
      bond "liquidity floor" is imposed here);
    * maximise return while staying genuinely diversified;
    * a tilt toward out-of-favour / undervalued themes with low overlap with
      today's crowded mega-cap-tech / AI trade.

It reuses the same engine as ``build_report`` (forward-looking CMAs, Ledoit-Wolf
shrinkage covariance on proxy-spliced GBP total returns, Michaud-resampled
weights) but solves THREE options across a risk ladder:

    Growth       max geometric growth, themes-forward, no tail cap   (high octane)
    Balanced     geometric growth s.t. a 1-yr 95% CVaR <= 15%        (RECOMMENDED)
    All-Weather  geometric growth s.t. a 1-yr 95% CVaR <=  9%        (smoothest)

For each it reports the Pie-ready weights, expected geo/arith/vol, the 1-year
CVaR, the **5-year** max-drawdown distribution (the risk that actually bites a
withdraw-at-year-5 investor), and a 5-year terminal-wealth distribution vs a
passive global-tracker proxy.

Run from the repo root (offline-friendly — uses the cached return history):

    python -m portfolio_optimiser.report.build_isa_5y

Outputs land in ``portfolio_optimiser/outputs/isa_5y/``:
    results.json            every number cited in the written report
    targets_<option>.csv    Pie-ready weights per option
    wealth_5y.png           5-year terminal-wealth fan, three options

Not financial advice. Every assumption is in ``config/`` and editable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from ..optimiser import cma as cma_mod
from ..optimiser import covariance as cov_mod
from ..optimiser import data as data_mod
from ..optimiser import robust
from ..optimiser.config import PortfolioConstraints, load_all
from ..optimiser.optimize import clean_weights, optimise_isa, optimise_sipp, summarize
from . import validate

OUT = Path(__file__).resolve().parents[1] / "outputs" / "isa_5y"

SEED_GBP = 20_000
HORIZON_YEARS = 5

# Full ISA-eligible working set. AVWC (Avantis Global Equity, AVCG.L) is a GBP LSE
# UCITS Acc ETF and so is ISA-eligible on Trading 212 despite the conservative
# `isa_eligible=false` flag in the universe (kept there for the legacy SIPP/ISA
# split); confirm it is searchable in your ISA before funding.
ALL = ["AVWC", "AVSG", "XDEW", "EMIM", "IWQU", "MVOL", "JMFP", "SGLN", "GLIN",
       "DFND_EU", "URNM", "IGLS", "ERNS"]
# Growth option holds no dedicated bond ballast (fully invested for growth).
GROWTH_SET = [k for k in ALL if k not in ("IGLS", "ERNS")]


@dataclass
class Option:
    key: str
    label: str
    tagline: str
    solver: str                       # "max_geometric" | "cvar"
    constraints: PortfolioConstraints


def _mk(name, **kw) -> PortfolioConstraints:
    base = dict(name=name, value_gbp=SEED_GBP, objective="x", weight_min=0.0,
                sleeve_caps={}, sleeve_floors={})
    base.update(kw)
    return PortfolioConstraints(**base)


def options() -> list[Option]:
    growth = _mk(
        "Growth", weight_max=0.28, universe=GROWTH_SET,
        sleeve_caps={"theme": 0.20, "diversifier": 0.10, "real_asset": 0.12,
                     "equity_defensive": 0.08},
        sleeve_floors={"theme": 0.12, "real_asset": 0.04})
    balanced = _mk(
        "Balanced", weight_max=0.22, universe=ALL,
        sleeve_caps={"theme": 0.14, "diversifier": 0.15, "real_asset": 0.18,
                     "equity_defensive": 0.12, "ballast": 0.12},
        sleeve_floors={"theme": 0.09, "diversifier": 0.08, "real_asset": 0.12},
        liquidity_floor_gbp=0.0, ballast_sleeve="ballast",
        cvar_alpha=0.95, cvar_limit=0.15)
    allweather = _mk(
        "AllWeather", weight_max=0.18, universe=ALL,
        sleeve_caps={"theme": 0.10, "diversifier": 0.20, "real_asset": 0.22,
                     "equity_defensive": 0.16, "ballast": 0.35},
        sleeve_floors={"theme": 0.06, "diversifier": 0.12, "real_asset": 0.16,
                       "equity_defensive": 0.08},
        liquidity_floor_gbp=0.0, ballast_sleeve="ballast",
        cvar_alpha=0.95, cvar_limit=0.09)
    return [
        Option("growth", "Option 1 — Global Growth Engine",
               "Maximise return; mostly value/EM equities + themes. The high-octane end.",
               "max_geometric", growth),
        Option("balanced", "Option 2 — Balanced Growth",
               "Growth core plus real-asset & trend diversifiers. The recommended core.",
               "cvar", balanced),
        Option("allweather", "Option 3 — All-Weather Diversified",
               "Diversifier-heavy, smoothest ride, lowest expected return.",
               "cvar", allweather),
    ]


def _build_inputs(refresh: bool):
    cfg = load_all()
    U, cma, S = cfg.universe, cfg.cma, cfg.settings
    returns = data_mod.build_returns(U, S, keys=ALL, refresh=refresh)
    cov = cov_mod.estimate_covariance(returns[ALL], S)
    ters = {k: U.instruments[k].ter for k in ALL}
    mu = cma_mod.net_of_fees(cma_mod.arithmetic_returns(cma, ALL), ters)
    vol = cov_mod.annual_vol(cov)
    # Transparent passive global-tracker proxy from the cached series: a
    # developed-value core + US + EM blend (~13% annualised vol), priced at the
    # plain developed-equity CMA (no factor tilt) — i.e. "what a Vanguard-style
    # global tracker would do". Used only for the path-by-path P(beat) stat.
    bench = (0.65 * returns["AVWC"] + 0.20 * returns["XDEW"]
             + 0.15 * returns["EMIM"]).dropna().rename("BENCH")
    bench_mu = cma.blocks["equity_dev"]
    return cfg, U, cma, S, returns, cov, mu, vol, bench, bench_mu


def _dd_percentiles(maxdd: np.ndarray) -> dict:
    return {
        "median": float(np.median(maxdd)),
        "p25": float(np.percentile(maxdd, 25)),
        "p5": float(np.percentile(maxdd, 5)),
        "worst": float(maxdd.min()),
    }


def _solve_option(opt: Option, U, mu, cov, S) -> pd.Series:
    fn = optimise_sipp if opt.solver == "max_geometric" else optimise_isa
    resampled = robust.resampled_weights(fn, opt.constraints, U, mu, cov, S)
    return clean_weights(resampled, S.min_holding, opt.constraints.weight_max)


def main(refresh: bool = False) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg, U, cma, S, returns, cov, mu, vol, bench, bench_mu = _build_inputs(refresh)
    hist_start = returns.dropna(how="all").index.min()

    bundle = {
        "meta": {
            "seed_gbp": SEED_GBP,
            "horizon_years": HORIZON_YEARS,
            "history_start": f"{hist_start:%Y-%m}",
            "history_end": f"{returns.dropna(how='all').index.max():%Y-%m}",
            "resample_draws": S.resample_draws,
            "mc_paths": S.mc_paths,
            "random_seed": S.random_seed,
            "bench_note": "Passive global-tracker proxy: 0.65 AVWC + 0.20 XDEW "
                          "+ 0.15 EMIM, priced at the developed-equity CMA "
                          f"({bench_mu:.1%} arith).",
        },
        "instruments": {},
        "options": [],
    }
    for k in ALL:
        inst = U.instruments[k]
        bundle["instruments"][k] = {
            "ticker": inst.ticker, "name": inst.name, "sleeve": inst.sleeve,
            "role": inst.role, "ter": inst.ter,
            "mu_arith": round(float(mu[k]), 4),
            "mu_geo": round(float(cma_mod.to_geometric(mu, cov)[k]), 4),
            "vol": round(float(vol[k]), 4),
        }

    for opt in options():
        print(f"[*] {opt.label} — resampling {S.resample_draws} draws ...")
        w = _solve_option(opt, U, mu, cov, S)
        res = summarize(opt.key, w, mu, cov, "resampled_michaud")

        held = res.weights[res.weights > 0].sort_values(ascending=False)
        sleeves: dict[str, float] = {}
        for k, v in held.items():
            sleeves[U.sleeve_of(k)] = sleeves.get(U.sleeve_of(k), 0.0) + float(v)

        dd1, _ = validate.drawdown_distribution(
            res.weights, mu, cov, returns, S, 0.20, 0.95, horizon_months=12)
        _, maxdd5 = validate.drawdown_distribution(
            res.weights, mu, cov, returns, S, 0.20, 0.95, horizon_months=HORIZON_YEARS * 12)
        tw = validate.terminal_wealth(
            res.weights, mu, cov, bench, bench_mu, returns, S, years=HORIZON_YEARS)

        rows = [{
            "key": k, "ticker": U.instruments[k].ticker, "name": U.instruments[k].name,
            "sleeve": U.instruments[k].sleeve, "weight": round(float(v), 4),
            "pie_pct": round(float(v) * 100, 1),
        } for k, v in held.items()]
        pd.DataFrame(rows).to_csv(OUT / f"targets_{opt.key}.csv", index=False)

        bundle["options"].append({
            "key": opt.key, "label": opt.label, "tagline": opt.tagline,
            "exp_geometric": round(res.exp_geometric, 4),
            "exp_arithmetic": round(res.exp_arithmetic, 4),
            "volatility": round(res.volatility, 4),
            "cvar_1y_95": round(dd1.cvar_95, 4),
            "maxdd_5y": {kk: round(vv, 4) for kk, vv in _dd_percentiles(maxdd5).items()},
            "wealth_5y": {
                "median_multiple": round(tw.median_multiple, 3),
                "p5_multiple": round(tw.p5_multiple, 3),
                "p95_multiple": round(tw.p95_multiple, 3),
                "median_gbp": round(SEED_GBP * tw.median_multiple),
                "p5_gbp": round(SEED_GBP * tw.p5_multiple),
                "p95_gbp": round(SEED_GBP * tw.p95_multiple),
                "realised_geo": round(tw.realised_geo, 4),
                "prob_beat_tracker": round(tw.prob_beat_benchmark, 3),
                "tracker_median_multiple": round(tw.median_benchmark_multiple, 3),
            },
            "sleeves": {k: round(v, 4) for k, v in
                        sorted(sleeves.items(), key=lambda x: -x[1])},
            "weights": rows,
        })

    (OUT / "results.json").write_text(json.dumps(bundle, indent=2))
    _fan_chart(bundle)
    _print_summary(bundle)
    print(f"\nWrote {OUT/'results.json'} (+ targets_*.csv, wealth_5y.png)")
    return bundle


def _fan_chart(bundle: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    labels = [o["label"].split("—")[-1].strip() for o in bundle["options"]]
    x = np.arange(len(labels))
    p5 = [o["wealth_5y"]["p5_gbp"] for o in bundle["options"]]
    med = [o["wealth_5y"]["median_gbp"] for o in bundle["options"]]
    p95 = [o["wealth_5y"]["p95_gbp"] for o in bundle["options"]]
    ax.bar(x, [a - b for a, b in zip(p95, p5)], bottom=p5, width=0.5,
           color="#9fb6d6", alpha=0.6, label="5th–95th percentile")
    ax.scatter(x, med, color="#16314f", zorder=3, label="median")
    ax.axhline(SEED_GBP, ls="--", color="#888", label=f"£{SEED_GBP:,} seed")
    for xi, m in zip(x, med):
        ax.annotate(f"£{m:,.0f}", (xi, m), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("portfolio value after 5 years")
    ax.set_title("5-year outcome range on a £20,000 ISA (no further contributions)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "wealth_5y.png", dpi=120)
    plt.close(fig)


def _print_summary(bundle: dict) -> None:
    print("\n" + "=" * 78)
    for o in bundle["options"]:
        w = o["wealth_5y"]; d = o["maxdd_5y"]
        print(f"\n{o['label']}")
        print(f"  exp return {o['exp_geometric']:.2%} geo / {o['exp_arithmetic']:.2%} arith"
              f" · vol {o['volatility']:.2%} · 1y CVaR {o['cvar_1y_95']:.1%}")
        print(f"  5y maxDD  median {d['median']:.0%}  p25 {d['p25']:.0%}"
              f"  p5(tail) {d['p5']:.0%}  worst {d['worst']:.0%}")
        print(f"  5y wealth median £{w['median_gbp']:,} (x{w['median_multiple']})"
              f"  p5 £{w['p5_gbp']:,}  p95 £{w['p95_gbp']:,}"
              f"  P(beat tracker) {w['prob_beat_tracker']:.0%}")
        print("  sleeves: " + ", ".join(f"{k} {v:.0%}" for k, v in o["sleeves"].items()))
        print("  pie: " + ", ".join(f"{r['ticker']} {r['pie_pct']}%" for r in o["weights"]))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch market data")
    main(refresh=ap.parse_args().refresh)
