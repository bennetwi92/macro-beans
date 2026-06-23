"""End-to-end pipeline: build inputs, optimise, cross-check, validate, report.

Run from the repo root:

    python -m portfolio_optimiser.report.build_report
    python -m portfolio_optimiser.report.build_report --refresh   # re-fetch data

Outputs land in ``portfolio_optimiser/outputs/``:
    returns_monthly.csv         cached total-return history (the data input)
    expected_returns.csv        CMA arithmetic + geometric + vol per instrument
    correlation.csv             shrinkage correlation matrix
    targets_isa.csv             ISA target weights (+ T212 Pie %)
    targets_sipp.csv            SIPP target weights (+ T212 Pie %)
    method_comparison_*.csv     convex vs resampled vs BL vs HRP
    sensitivity_*.csv           CMA sensitivity (what the answer hinges on)
    montecarlo_sipp.csv/.png    25y terminal-wealth distribution
    drawdown_isa.csv/.png       1y drawdown distribution
    REPORT.md                   the human-readable summary
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ..optimiser import cma as cma_mod
from ..optimiser import covariance as cov_mod
from ..optimiser import data as data_mod
from ..optimiser import robust
from ..optimiser import sensitivity
from ..optimiser.config import load_all
from ..optimiser.objectives import make_scenarios
from ..optimiser.optimize import (
    OptResult, clean_weights, optimise_isa, optimise_sipp, summarize,
)
from . import validate

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


def _pie_frame(res: OptResult, universe) -> pd.DataFrame:
    rows = []
    for k, w in res.weights.items():
        inst = universe.instruments[k]
        rows.append({
            "key": k, "ticker": inst.ticker, "name": inst.name,
            "sleeve": inst.sleeve, "weight": round(w, 4),
            "pie_pct": round(w * 100, 1),
        })
    df = pd.DataFrame(rows).sort_values("weight", ascending=False).reset_index(drop=True)
    return df[df["weight"] > 0]


def _isa_diagnostics(weights, cfg, universe, mu_arith, cov, settings) -> dict:
    """Ballast-floor and CVaR checks for an arbitrary ISA weight vector."""
    keys = cfg.isa.universe
    w = weights.reindex(keys).fillna(0.0)
    floor_frac = cfg.isa.liquidity_floor_gbp / cfg.isa.value_gbp
    ballast_keys = [k for k in keys if universe.sleeve_of(k) == cfg.isa.ballast_sleeve]
    ballast_w = float(w[ballast_keys].sum())

    # CVaR of the 1-year loss from the same normal scenario model.
    scen = make_scenarios(
        mu_arith.loc[keys].values, cov.loc[keys, keys].values,
        settings.mc_paths, settings.random_seed)
    losses = -(scen @ w.values)
    var = float(np.quantile(losses, cfg.isa.cvar_alpha))
    cvar = float(losses[losses >= var].mean())
    return {
        "ballast_weight": ballast_w,
        "floor_frac": floor_frac,
        "floor_satisfied": bool(ballast_w >= floor_frac - 1e-3),
        "cvar": cvar,
        "cvar_ok": bool(cvar <= cfg.isa.cvar_limit + 1e-6),
    }


def _method_table(keys, **series) -> pd.DataFrame:
    df = pd.DataFrame({name: s.reindex(keys) for name, s in series.items()})
    return (df.fillna(0.0) * 100).round(1)


def _matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def main(refresh: bool = False) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    cfg = load_all()
    universe, cma, settings = cfg.universe, cfg.cma, cfg.settings

    all_keys = sorted(set(cfg.isa.universe) | set(cfg.sipp.universe))
    print(f"[1/7] Fetching/loading returns for {len(all_keys)} instruments ...")
    returns = data_mod.build_returns(universe, settings, keys=all_keys, refresh=refresh)
    bench = data_mod.benchmark_returns(settings) if refresh or not (OUTPUTS / "returns_monthly.csv").exists() else _bench_cached(settings)

    print("[2/7] Estimating shrinkage covariance + CMAs ...")
    cov = cov_mod.estimate_covariance(returns[all_keys], settings)
    ters = {k: universe.instruments[k].ter for k in all_keys}
    mu_arith = cma_mod.net_of_fees(cma_mod.arithmetic_returns(cma, all_keys), ters)
    mu_geo = cma_mod.to_geometric(mu_arith, cov)
    vol = cov_mod.annual_vol(cov)

    exp_df = pd.DataFrame({
        "mu_arith_net": mu_arith, "mu_geo": mu_geo, "vol": vol,
        "ter": pd.Series(ters),
    }).round(4)
    exp_df.to_csv(OUTPUTS / "expected_returns.csv")
    cov_mod.correlation(cov).round(3).to_csv(OUTPUTS / "correlation.csv")

    # ---- Optimise both portfolios (convex point optima = aggressive reference) -
    print("[3/7] Optimising SIPP (max geometric) and ISA (geo + liquidity + CVaR) ...")
    sipp_convex = optimise_sipp(cfg.sipp, universe, mu_arith, cov, settings)
    isa_convex = optimise_isa(cfg.isa, universe, mu_arith, cov, settings)

    # ---- Robust cross-checks; resampled (Michaud) is the RECOMMENDED target ----
    print("[4/7] Cross-checking: resampled (Michaud), Black-Litterman, HRP ...")
    sipp_resamp = robust.resampled_weights(optimise_sipp, cfg.sipp, universe, mu_arith, cov, settings)
    isa_resamp = robust.resampled_weights(optimise_isa, cfg.isa, universe, mu_arith, cov, settings)

    sipp_bl_mu, _ = robust.black_litterman(cfg.sipp, universe, mu_arith, cov, settings)
    isa_bl_mu, _ = robust.black_litterman(cfg.isa, universe, mu_arith, cov, settings)
    sipp_bl = optimise_sipp(cfg.sipp, universe, sipp_bl_mu, cov, settings).weights
    isa_bl = optimise_isa(cfg.isa, universe, isa_bl_mu, cov, settings).weights

    sipp_hrp = robust.hrp_weights(cov, cfg.sipp.universe)
    isa_hrp = robust.hrp_weights(cov, cfg.isa.universe)

    # Recommended targets = cleaned resampled weights, summarised + constraint-checked.
    sipp_target_w = clean_weights(sipp_resamp, settings.min_holding, cfg.sipp.weight_max)
    isa_target_w = clean_weights(isa_resamp, settings.min_holding, cfg.isa.weight_max)
    sipp_res = summarize("SIPP", sipp_target_w, mu_arith, cov, "resampled_michaud")
    isa_res = summarize("ISA", isa_target_w, mu_arith, cov, "resampled_michaud",
                        _isa_diagnostics(isa_target_w, cfg, universe, mu_arith, cov, settings))

    _pie_frame(sipp_res, universe).to_csv(OUTPUTS / "targets_sipp.csv", index=False)
    _pie_frame(isa_res, universe).to_csv(OUTPUTS / "targets_isa.csv", index=False)

    sipp_methods = _method_table(
        cfg.sipp.universe, recommended=sipp_res.weights, convex=sipp_convex.weights,
        resampled_raw=sipp_resamp, black_litterman=sipp_bl, hrp=sipp_hrp)
    isa_methods = _method_table(
        cfg.isa.universe, recommended=isa_res.weights, convex=isa_convex.weights,
        resampled_raw=isa_resamp, black_litterman=isa_bl, hrp=isa_hrp)
    sipp_methods.to_csv(OUTPUTS / "method_comparison_sipp.csv")
    isa_methods.to_csv(OUTPUTS / "method_comparison_isa.csv")

    # ---- Sensitivity ---------------------------------------------------------
    print("[5/7] CMA sensitivity sweep ...")
    sipp_sens, sipp_sens_full = sensitivity.sensitivity_table(
        optimise_sipp, cfg.sipp, universe, cma, cov, settings)
    isa_sens, isa_sens_full = sensitivity.sensitivity_table(
        optimise_isa, cfg.isa, universe, cma, cov, settings)
    sipp_sens.to_csv(OUTPUTS / "sensitivity_sipp.csv", index=False)
    isa_sens.to_csv(OUTPUTS / "sensitivity_isa.csv", index=False)

    # ---- Validation ----------------------------------------------------------
    print("[6/7] Monte Carlo validation ...")
    bench_mu = cma.blocks.get("equity_dev", 0.07)
    tw = validate.terminal_wealth(
        sipp_res.weights, mu_arith, cov, bench, bench_mu, returns, settings, years=cma.meta.get("horizon_years", 25))
    dd, max_dd = validate.drawdown_distribution(
        isa_res.weights, mu_arith, cov, returns, settings, cfg.isa.cvar_limit, cfg.isa.cvar_alpha)

    pd.DataFrame([tw.__dict__]).to_csv(OUTPUTS / "montecarlo_sipp.csv", index=False)
    pd.DataFrame([dd.__dict__]).to_csv(OUTPUTS / "drawdown_isa.csv", index=False)

    _make_plots(tw, max_dd, sipp_res, isa_res, cfg)

    # ---- Report --------------------------------------------------------------
    print("[7/7] Writing REPORT.md ...")
    _write_report(cfg, universe, exp_df, sipp_res, isa_res, sipp_methods, isa_methods,
                  sipp_sens, isa_sens, tw, dd, returns)
    print(f"Done. See {OUTPUTS / 'REPORT.md'}")


def _bench_cached(settings):
    """Benchmark returns from cache if present, else fetch."""
    try:
        return data_mod.benchmark_returns(settings)
    except Exception:
        # As a last resort use the cached asset returns' mean as a flat proxy.
        cached = pd.read_csv(data_mod.CACHE, index_col=0, parse_dates=True)
        return cached.mean(axis=1).rename("benchmark")


def _make_plots(tw, max_dd, sipp_res, isa_res, cfg):
    plt = _matplotlib()

    # SIPP terminal wealth (lognormal summary as a fan around realised geo).
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["5th pct", "median", "95th pct"]
    vals = [tw.p5_multiple, tw.median_multiple, tw.p95_multiple]
    ax.bar(labels, vals, color=["#c0392b", "#2c3e50", "#27ae60"])
    ax.axhline(tw.median_benchmark_multiple, ls="--", color="#888",
               label=f"tracker median x{tw.median_benchmark_multiple:.1f}")
    ax.set_title(f"SIPP terminal wealth over {tw.years}y (multiple of starting value)")
    ax.set_ylabel("multiple")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUTS / "montecarlo_sipp.png", dpi=120)
    plt.close(fig)

    # ISA max-drawdown distribution.
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(max_dd * 100, bins=60, color="#2c3e50", alpha=0.85)
    ax.axvline(-abs(cfg.isa.cvar_limit) * 100, color="#c0392b", ls="--",
               label=f"limit {cfg.isa.cvar_limit:.0%}")
    ax.set_title("ISA simulated 1-year max drawdown")
    ax.set_xlabel("max drawdown (%)")
    ax.set_ylabel("paths")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUTS / "drawdown_isa.png", dpi=120)
    plt.close(fig)


def _weights_md(res: OptResult, universe) -> str:
    df = _pie_frame(res, universe)
    lines = ["| Holding | Ticker | Sleeve | Weight | Pie % |",
             "|---|---|---|---:|---:|"]
    for _, r in df.iterrows():
        lines.append(f"| {r['name']} | {r['ticker']} | {r['sleeve']} | "
                     f"{r['weight']:.1%} | {r['pie_pct']:.1f} |")
    return "\n".join(lines)


def _df_md(df: pd.DataFrame, index: bool = True) -> str:
    return df.to_markdown(index=index)


def _write_report(cfg, universe, exp_df, sipp_res, isa_res, sipp_methods, isa_methods,
                  sipp_sens, isa_sens, tw, dd, returns):
    isa, sipp, settings = cfg.isa, cfg.sipp, cfg.settings
    floor_frac = isa.liquidity_floor_gbp / isa.value_gbp
    hist_start = returns.dropna(how="all").index.min()

    md = f"""# Portfolio allocation optimiser — results

*Generated by `portfolio_optimiser`. Not financial advice. Every input is in
`config/` and editable; re-run with `python -m portfolio_optimiser.report.build_report`.*

## Investor parameters used

| Parameter | Value | Source |
|---|---|---|
| ISA 1-year liquidity floor | £{isa.liquidity_floor_gbp:,.0f} ({floor_frac:.0%} of the £{isa.value_gbp:,.0f} seed) | investor-supplied |
| ISA tail limit (95% CVaR / max drawdown) | {isa.cvar_limit:.0%} | investor-supplied |
| SIPP funding (2026/27) | £{sipp.value_gbp:,.0f} | investor-supplied |
| SIPP operator fee | £{sipp.fixed_fee_gbp:,.0f} (no Gaudi fee — T212 self-operated SIPP) | investor-supplied |

## Method in one paragraph

Expected returns are **forward-looking CMAs** (building-block premia in `config/cma.toml`),
net of TER — never raw historical means. The covariance is a **Ledoit-Wolf shrinkage**
estimate on month-end GBP total returns from {hist_start:%Y-%m}, with young funds **spliced
onto longer-history proxies** (mapping in `config/universe.toml`). Arithmetic returns are
converted to **geometric** (g = μ − ½σ²). The **SIPP** maximises portfolio geometric growth
g(w)=μ'w−½w'Σw (long-only, per-holding ≤ {sipp.weight_max:.0%}, sleeve caps). The **ISA**
maximises the same objective **subject to** a hard ballast floor (≥ {floor_frac:.0%}) and a
**95% CVaR ≤ {isa.cvar_limit:.0%}** tail cap (Rockafellar–Uryasev).

**The recommended target weights below are the resampled (Michaud) solution**, not the
single-point convex optimum. The convex optimum is a concentrated corner (it piles into
the few highest-expected-return holdings up to the caps — exactly the estimation-error
fragility the brief warns about). Resampling re-optimises over hundreds of noise-perturbed
input draws and averages the results, giving a diversified, estimation-robust allocation
that still respects every hard constraint (caps, the ballast floor, the CVaR cap are all
convex, so their average stays feasible) and naturally earns slots for the gold /
managed-futures crash diversifiers. Black-Litterman and HRP are shown as further
cross-checks; everything is validated by Monte Carlo and stress-tested against
±{settings.sensitivity_shift*100:.0f}ppt CMA shifts.

---

## Portfolio B — SIPP (maximise terminal wealth)

Objective: maximise expected geometric growth. **Recommended (resampled) target:**
**geometric return {sipp_res.exp_geometric:.2%}/yr · arithmetic {sipp_res.exp_arithmetic:.2%} · vol {sipp_res.volatility:.2%}.**

{_weights_md(sipp_res, universe)}

### Method comparison (weights %, recommended vs reference methods)

{_df_md(sipp_methods)}

### Monte Carlo — {tw.years}-year terminal wealth (£{sipp.value_gbp:,.0f} seed, no future contributions)

| Metric | Value |
|---|---|
| Median terminal multiple | ×{tw.median_multiple:.2f} (≈ £{sipp.value_gbp*tw.median_multiple:,.0f}) |
| 5th percentile | ×{tw.p5_multiple:.2f} |
| 95th percentile | ×{tw.p95_multiple:.2f} |
| Realised geometric return | {tw.realised_geo:.2%}/yr |
| Tracker (VWRP proxy) median | ×{tw.median_benchmark_multiple:.2f} |
| **P(beat the global tracker)** | **{tw.prob_beat_benchmark:.0%}** |

### What the answer hinges on (top CMA sensitivities)

{_df_md(sipp_sens.head(6), index=False)}

---

## Portfolio A — ISA (liquidity-aware, crash-averse)

Objective: geometric growth subject to a £{isa.liquidity_floor_gbp:,.0f} ballast floor and a
{isa.cvar_limit:.0%} tail cap. **Recommended (resampled) target:**
**geometric return {isa_res.exp_geometric:.2%}/yr · arithmetic {isa_res.exp_arithmetic:.2%} · vol {isa_res.volatility:.2%}.**
Ballast weight {isa_res.diagnostics['ballast_weight']:.1%} (floor {floor_frac:.0%}, satisfied: {isa_res.diagnostics['floor_satisfied']}); modelled 95% CVaR {isa_res.diagnostics['cvar']:.1%} (limit {isa.cvar_limit:.0%}, satisfied: {isa_res.diagnostics['cvar_ok']}).

{_weights_md(isa_res, universe)}

> **Glidepath note.** The £{isa.liquidity_floor_gbp:,.0f} floor is an *absolute* amount, so on
> the £{isa.value_gbp:,.0f} seed it forces **{floor_frac:.0%} in ballast** — a heavy drag on the
> 25-year mandate. As monthly contributions grow the ISA the floor stays fixed in £ terms,
> so its share falls (e.g. at £40k it is {isa.liquidity_floor_gbp/40000:.0%}, at £100k it is
> {isa.liquidity_floor_gbp/100000:.0%}). If the external ~£30k cash buffer in fact covers the
> 1-year need, lowering `liquidity_floor_gbp` frees this sleeve for growth — see the
> sensitivity of that single knob.

### Method comparison (weights %)

{_df_md(isa_methods)}

### Monte Carlo — 1-year tail (does it breach the {isa.cvar_limit:.0%} limit?)

| Metric | Value |
|---|---|
| Mean 1-year loss (negative = gain) | {dd.mean_loss:.2%} |
| 95% VaR (1-year loss) | {dd.var_95:.2%} |
| **95% CVaR (1-year expected shortfall)** | **{dd.cvar_95:.2%}** (limit {isa.cvar_limit:.0%}) |
| 5th-percentile max drawdown | {dd.p95_max_drawdown:.2%} |
| Worst simulated max drawdown | {dd.worst_max_drawdown:.2%} |
| **P(max drawdown worse than {isa.cvar_limit:.0%})** | **{dd.prob_breach_dd:.1%}** |

### What the answer hinges on (top CMA sensitivities)

{_df_md(isa_sens.head(6), index=False)}

---

## Expected returns & risk (per instrument, net of TER)

{_df_md(exp_df)}

## Caveats

- CMAs are a transparent prior, **not a forecast**. The sensitivity tables show which
  weights depend on which assumption; revisit `config/cma.toml` annually.
- Covariance uses proxy-spliced history; the proxy mapping (esp. the European-defence and
  managed-futures proxies) is documented in `config/universe.toml` and is imperfect.
- Monte Carlo assumes multivariate-normal monthly returns (thin tails). The CVaR cap and
  the gold/managed-futures diversifiers are the deliberate hedge against the fat-tailed
  AI-crash scenario the normal model understates.
- **SIPP eligibility of SGLN (ETC) and JMFP (managed futures) inside Trading 212 is not
  fully confirmed** — see `report/UNIVERSE_VERIFICATION.md`. Confirm before funding; the
  config has same-role fallbacks.
"""
    (OUTPUTS / "REPORT.md").write_text(md)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch market data")
    args = ap.parse_args()
    main(refresh=args.refresh)
