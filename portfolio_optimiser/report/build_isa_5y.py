"""Five-year ISA — Balanced CORE that compounds + a 20% ROTATING theme sleeve.

A bespoke driver for a specific, refreshed mandate (July 2026) that the standing
ISA/SIPP profiles in ``config/constraints.toml`` do **not** cover:

    * ~GBP 20,400 transferred into a Trading 212 Stocks & Shares ISA;
    * a single 5-year horizon, after which the whole pot is withdrawn;
    * fully invested (an emergency-cash buffer sits OUTSIDE this pot, so no
      bond "liquidity floor" is imposed here);
    * a BALANCED risk budget (the account holder's choice), expressed as an
      explicit two-part structure:
         - a ~80% CORE that is meant to sit and compound indefinitely
           (global value/quality/small-value + UK + EM-value equity, plus a
           permanent gold / trend / infrastructure diversifier sleeve), and
         - a ~20% ROTATING thematic sleeve reviewed and rotated ~annually.
    * a deliberate tilt AWAY from the crowded US mega-cap / AI-semiconductor
      trade, and toward fresher, less-saturated second-order themes.

The 2026 rotating sleeve (equal ~5% each) is:
    GRIDN  grid & electrification (picks-and-shovels of AI power demand)
    NUKE   nuclear fuel cycle + utilities (broader than the now-crowded miners)
    JPNV   Japan value-up (governance re-rating; GBP-hedged, no JPY FX)
    WATER  global water infra/utilities (structural, defensive, low AI overlap)

Defence (DFND_EU), uranium miners (URNM) and silver (SLVR) remain in the universe
as BENCH ALTERNATES for future rotations. Silver was dropped from the active
sleeve after the July-2026 analyst review (its ~0.8% modelled return / ~28% vol
made it a return-drag) and replaced with WATER, which the review recommended as a
genuinely orthogonal, non-AI-capex theme.

NOTE: WATER (IH2O.L) is a new line with no entry in the committed return cache, so
regenerating the outputs below requires a network refresh:
    python -m portfolio_optimiser.report.build_isa_5y --refresh
Until that runs online, the committed outputs/isa_5y/ risk artifacts still reflect
the prior SLVR-in build -- see outputs/isa_5y/REFRESH_NOTE.md.

Method: the CORE is optimised with the same engine as ``build_report``
(forward-looking CMAs, Ledoit-Wolf shrinkage covariance on proxy-spliced GBP
total returns, Michaud-resampled weights, geometric objective s.t. a 1-year 95%
CVaR cap). The fixed ROTATING sleeve is then overlaid, and the COMBINED book is
validated by 20k-path Monte-Carlo (5-year drawdown + terminal wealth vs a
passive global tracker).

Run from the repo root (offline-friendly -- uses the cached return history):

    python -m portfolio_optimiser.report.build_isa_5y

Outputs land in ``portfolio_optimiser/outputs/isa_5y/``:
    results.json            every number cited in the written report
    targets_recommended.csv Pie-ready weights (core + rotating sleeve)
    wealth_5y.png           5-year terminal-wealth range vs a passive tracker

Not financial advice. Every assumption is in ``config/`` and editable.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..optimiser import cma as cma_mod
from ..optimiser import covariance as cov_mod
from ..optimiser import data as data_mod
from ..optimiser import robust
from ..optimiser.config import PortfolioConstraints
from ..optimiser.config import load_all
from ..optimiser.optimize import clean_weights, optimise_isa, summarize
from . import validate

OUT = Path(__file__).resolve().parents[1] / "outputs" / "isa_5y"

SEED_GBP = 20_400
HORIZON_YEARS = 5

# ---------------------------------------------------------------------------
# Two-part structure.
# ---------------------------------------------------------------------------
# CORE (~80%): the compound-forever engine. Equity value/quality/small-value +
# UK (cheapest DM, GBP) + EM-value, plus the PERMANENT diversifier sleeve
# (gold / trend / infrastructure). ERNS is present only to satisfy the engine's
# ballast-sleeve requirement (the liquidity floor is 0, so it can sit at ~0).
CORE = ["AVWC", "AVSG", "XDEW", "IWQU", "UKEQ", "EMVL", "SGLN", "JMFP", "GLIN", "ERNS"]
# ROTATING sleeve (~20%): four fresher second-order themes, equal-weighted, and
# reviewed/rotated ~annually.
THEMES = ["GRIDN", "NUKE", "JPNV", "WATER"]
THEME_SLEEVE_FRAC = 0.20

ALL = CORE + THEMES


def _mk(name, **kw) -> PortfolioConstraints:
    base = dict(name=name, value_gbp=SEED_GBP, objective="x", weight_min=0.0,
                sleeve_caps={}, sleeve_floors={})
    base.update(kw)
    return PortfolioConstraints(**base)


def core_constraints() -> PortfolioConstraints:
    """Balanced budget over the CORE universe (pre-scaling to ~80%).

    The CVaR cap is deliberately set a touch tighter than the 15% Balanced
    budget because the high-vol 20% theme overlay adds risk on top; the COMBINED
    book is what we measure and report against the ~15% Balanced level.
    """
    return _mk(
        "BalancedCore", weight_max=0.24, universe=CORE,
        sleeve_caps={"real_asset": 0.30, "diversifier": 0.16, "ballast": 0.12},
        sleeve_floors={"real_asset": 0.18, "diversifier": 0.11},
        liquidity_floor_gbp=0.0, ballast_sleeve="ballast",
        cvar_alpha=0.95, cvar_limit=0.13)


def _build_inputs(refresh: bool):
    cfg = load_all()
    U, cma, S = cfg.universe, cfg.cma, cfg.settings
    returns = data_mod.build_returns(U, S, keys=ALL, refresh=refresh)
    cov = cov_mod.estimate_covariance(returns[ALL], S)
    ters = {k: U.instruments[k].ter for k in ALL}
    mu = cma_mod.net_of_fees(cma_mod.arithmetic_returns(cma, ALL), ters)
    vol = cov_mod.annual_vol(cov)
    # Transparent passive global-tracker proxy from the cached series: a
    # developed + US-equal-weight + EM blend, priced at the plain developed-
    # equity CMA (no factor tilt) -- "what a Vanguard-style global tracker would
    # do". Used only for the path-by-path P(beat) statistic.
    bench = (0.60 * returns["AVWC"] + 0.25 * returns["XDEW"]
             + 0.15 * returns["EMVL"]).dropna().rename("BENCH")
    bench_mu = cma.blocks["equity_dev"]
    return cfg, U, cma, S, returns, cov, mu, vol, bench, bench_mu


def _dd_percentiles(maxdd: np.ndarray) -> dict:
    return {
        "median": float(np.median(maxdd)),
        "p25": float(np.percentile(maxdd, 25)),
        "p5": float(np.percentile(maxdd, 5)),
        "worst": float(maxdd.min()),
    }


def build_combined(U, mu, cov, S) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (combined, core_scaled, theme) weight Series that sum to 1.0."""
    cons = core_constraints()
    resampled = robust.resampled_weights(optimise_isa, cons, U, mu, cov, S)
    core_w = clean_weights(resampled, S.min_holding, cons.weight_max)
    core_scaled = core_w * (1.0 - THEME_SLEEVE_FRAC)
    theme_w = pd.Series(
        {k: THEME_SLEEVE_FRAC / len(THEMES) for k in THEMES}, name="weight")
    combined = pd.concat([core_scaled, theme_w])
    combined = combined[combined > 0].rename("weight")
    combined = combined / combined.sum()
    return combined, core_scaled[core_scaled > 0], theme_w


def main(refresh: bool = False) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg, U, cma, S, returns, cov, mu, vol, bench, bench_mu = _build_inputs(refresh)
    hist_start = returns.dropna(how="all").index.min()

    combined, core_scaled, theme_w = build_combined(U, mu, cov, S)
    res = summarize("recommended", combined, mu, cov, "resampled_michaud_core+overlay")

    sleeves: dict[str, float] = {}
    for k, v in combined.items():
        sleeves[U.sleeve_of(k)] = sleeves.get(U.sleeve_of(k), 0.0) + float(v)

    dd1, _ = validate.drawdown_distribution(
        combined, mu, cov, returns, S, 0.20, 0.95, horizon_months=12)
    _, maxdd5 = validate.drawdown_distribution(
        combined, mu, cov, returns, S, 0.20, 0.95, horizon_months=HORIZON_YEARS * 12)
    tw = validate.terminal_wealth(
        combined, mu, cov, bench, bench_mu, returns, S, years=HORIZON_YEARS)

    held = combined.sort_values(ascending=False)
    rows = [{
        "key": k, "ticker": U.instruments[k].ticker, "name": U.instruments[k].name,
        "sleeve": U.instruments[k].sleeve,
        "bucket": "rotating" if k in THEMES else "core",
        "weight": round(float(v), 4), "pie_pct": round(float(v) * 100, 1),
        "ter": U.instruments[k].ter,
    } for k, v in held.items()]
    pd.DataFrame(rows).to_csv(OUT / "targets_recommended.csv", index=False)

    blended_ter = float(sum(r["weight"] * r["ter"] for r in rows))
    core_frac = float(core_scaled.sum())

    bundle = {
        "meta": {
            "seed_gbp": SEED_GBP,
            "horizon_years": HORIZON_YEARS,
            "history_start": f"{hist_start:%Y-%m}",
            "history_end": f"{returns.dropna(how='all').index.max():%Y-%m}",
            "resample_draws": S.resample_draws,
            "mc_paths": S.mc_paths,
            "random_seed": S.random_seed,
            "core_frac": round(core_frac, 4),
            "theme_frac": round(THEME_SLEEVE_FRAC, 4),
            "blended_ter": round(blended_ter, 5),
            "bench_note": "Passive global-tracker proxy: 0.60 AVWC + 0.25 XDEW "
                          "+ 0.15 EMVL, priced at the developed-equity CMA "
                          f"({bench_mu:.1%} arith).",
        },
        "instruments": {},
        "recommended": {
            "label": "Balanced Core + Rotating Themes",
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
                "tracker_median_gbp": round(SEED_GBP * tw.median_benchmark_multiple),
            },
            "sleeves": {k: round(v, 4) for k, v in
                        sorted(sleeves.items(), key=lambda x: -x[1])},
            "weights": rows,
        },
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

    (OUT / "results.json").write_text(json.dumps(bundle, indent=2))
    _fan_chart(bundle)
    _print_summary(bundle)
    print(f"\nWrote {OUT/'results.json'} (+ targets_recommended.csv, wealth_5y.png)")
    return bundle


def _fan_chart(bundle: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    r = bundle["recommended"]["wealth_5y"]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    labels = ["Balanced Core\n+ Rotating Themes", "Passive global\ntracker"]
    x = np.arange(len(labels))
    p5 = [r["p5_gbp"], None]
    med = [r["median_gbp"], r["tracker_median_gbp"]]
    p95 = [r["p95_gbp"], None]
    ax.bar(0, p95[0] - p5[0], bottom=p5[0], width=0.5,
           color="#9fb6d6", alpha=0.6, label="5th-95th percentile")
    ax.scatter(x, med, color="#16314f", zorder=3, label="median")
    ax.axhline(SEED_GBP, ls="--", color="#888", label=f"£{SEED_GBP:,} seed")
    for xi, m in zip(x, med):
        ax.annotate(f"£{m:,.0f}", (xi, m), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("portfolio value after 5 years")
    ax.set_title(f"5-year outcome range on a £{SEED_GBP:,} ISA (no further contributions)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "wealth_5y.png", dpi=120)
    plt.close(fig)


def _print_summary(bundle: dict) -> None:
    m = bundle["meta"]; o = bundle["recommended"]
    w = o["wealth_5y"]; d = o["maxdd_5y"]
    print("\n" + "=" * 78)
    print(f"{o['label']}   (core {m['core_frac']:.0%} / rotating {m['theme_frac']:.0%})")
    print(f"  exp return {o['exp_geometric']:.2%} geo / {o['exp_arithmetic']:.2%} arith"
          f" · vol {o['volatility']:.2%} · 1y CVaR {o['cvar_1y_95']:.1%}"
          f" · blended TER {m['blended_ter']:.2%}")
    print(f"  5y maxDD  median {d['median']:.0%}  p25 {d['p25']:.0%}"
          f"  p5(tail) {d['p5']:.0%}  worst {d['worst']:.0%}")
    print(f"  5y wealth median £{w['median_gbp']:,} (x{w['median_multiple']})"
          f"  p5 £{w['p5_gbp']:,}  p95 £{w['p95_gbp']:,}"
          f"  P(beat tracker) {w['prob_beat_tracker']:.0%}")
    print("  sleeves: " + ", ".join(f"{k} {v:.0%}" for k, v in o["sleeves"].items()))
    print("  CORE:  " + ", ".join(
        f"{r['ticker']} {r['pie_pct']}%" for r in o["weights"] if r["bucket"] == "core"))
    print("  THEMES:" + ", ".join(
        f" {r['ticker']} {r['pie_pct']}%" for r in o["weights"] if r["bucket"] == "rotating"))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch market data")
    main(refresh=ap.parse_args().refresh)
