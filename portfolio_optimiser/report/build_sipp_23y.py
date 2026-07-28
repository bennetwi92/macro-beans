"""23-year SIPP — a contribution-funded, growth-maximising pension to age 57.

A bespoke driver for the July-2026 SIPP mandate, which the standing profiles in
``config/constraints.toml`` did not previously cover:

    * an Interactive Investor SIPP opened with a NIL balance;
    * funded by a monthly contribution stream from contractor income (umbrella
      salary sacrifice, employer NI passed back), not a single tax-year lump;
    * a 23-year horizon to the normal minimum pension age of 57 in 2049;
    * the maximum risk posture the account holder can sustain -- they have said
      a -40% year would prompt them to contribute MORE -- so no tail constraint
      is imposed and the geometric objective is left to do the disciplining;
    * genuinely low maintenance: a handful of accumulating LSE lines bought by
      ii's free regular-investing service and rebalanced out of contributions.

Method, in one paragraph. Expected returns come from the building-block CMAs in
``config/cma.toml``, net of each fund's TER. The covariance is a Ledoit-Wolf
shrinkage estimate on proxy-spliced GBP total returns reaching back to April
2008, so it contains the 2008 crash rather than starting after it. Weights are
the equal-weight ENSEMBLE of two return-aware optimisers -- the convex geometric
(Kelly) solution and a Black-Litterman posterior -- each first put through
Michaud resampling. That last step matters: run once on point estimates, both
optimisers return CORNER solutions, piling into the three highest-expected-return
lines and zeroing the rest, which is estimation error rather than conviction.
Resampling corrects it, so the ensemble averages two already-smoothed answers
instead of mixing smoothed and unsmoothed ones. HRP and ERC are computed too, but
as return-blind diagnostics rather than ingredients: over a universe containing
low-volatility assets they load up on them regardless of expected return, which
answers a different question from the one this mandate asks. The recommendation
is then stress-tested by a stationary block bootstrap of the real return history,
recentred onto the CMAs, which preserves fat tails and the tendency of losses to
arrive in runs; the Gaussian model is reported alongside it to show how much
downside normality hides. Finally, because the allocation leans on assumed factor
premia, everything is re-run with those premia set to zero.

Run from the repo root:

    python -m portfolio_optimiser.report.build_sipp_23y            # cached history
    python -m portfolio_optimiser.report.build_sipp_23y --refresh  # re-fetch

Outputs land in ``portfolio_optimiser/outputs/sipp_23y/``:
    results.json              every number cited in the written report
    targets_recommended.csv   weights + the ii regular-investing GBP ladder
    method_comparison.csv     all eight methods and the ensemble, side by side
    sensitivity.csv           weight response to +/- 1ppt CMA block shifts
                              (resampled engine; sensitivity_raw.csv = unsmoothed)
    sequence_risk.csv         terminal wealth when a -40% crash lands in year N
    fee_drag.csv              the flat platform fee as a % of the pot, per year
    wealth_23y.png            outcome fan, bootstrap vs normal
    glidepath.png             the de-risking schedule and what it costs/saves
    sequence_risk.png         why an early crash is survivable and a late one is not

Not financial advice. Every assumption is in ``config/`` and editable.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..optimiser import cma as cma_mod
from ..optimiser import covariance as cov_mod
from ..optimiser import data as data_mod
from ..optimiser import lifecycle as lc
from ..optimiser import robust
from ..optimiser import sensitivity as sens_mod
from ..optimiser.config import PortfolioConstraints, load_all
from ..optimiser.optimize import clean_weights, optimise_sipp, summarize

OUT = Path(__file__).resolve().parents[1] / "outputs" / "sipp_23y"
LONG_CACHE = OUT / "returns_monthly_long.csv"

# History window for this mandate. Deliberately earlier than the shared
# 2009 start in constraints.toml: a 23-year plan that models drawdowns on a
# post-crisis-only sample is flattering itself. 2003-12 is the earliest month
# with GBPUSD data, which every USD proxy needs.
LONG_START = "2003-12-01"

# The glidepath's destination. This sits OUTSIDE the optimisation universe on
# purpose -- a near-cash asset has no place in a growth optimisation, but it is
# exactly what the pot should be drifting into as 2049 approaches. ERNS was
# dropped from the mix: its history only starts in 2013 and it would have
# shortened the glidepath window for no diversification gain over IGLS.
DEFENSIVE = {"IGLS": 1.00}

# A plain global tracker to beat: developed + EM equity beta, priced at the
# UNTILTED developed-equity CMA less a typical tracker TER. Pricing it off any
# tilted line would hand the benchmark a factor premium it does not earn and
# make the comparison meaningless.
TRACKER = {"AVWC": 0.85, "EMVL": 0.15}
TRACKER_TER = 0.0012

# Recommendation-level dust threshold. Higher than the 3% global setting: this
# mandate explicitly asks for low maintenance, and a 3% line on a monthly
# contribution is a rounding error that still costs attention forever.
MIN_HOLDING = 0.05

# Methods that are averaged into the recommendation. HRP and ERC are computed
# and reported but deliberately excluded -- see the module docstring.
ENSEMBLE_METHODS = ("michaud_resampled", "michaud_black_litterman")


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def build_inputs(refresh: bool = False):
    cfg = load_all()
    U, cma, S = cfg.universe, cfg.cma, cfg.settings
    keys = list(cfg.sipp.universe)
    panel_keys = keys + list(DEFENSIVE)

    # Private long-history settings/cache so this mandate cannot alter the
    # covariance inputs of the already-published ISA build.
    S_long = dataclasses.replace(S, data_start=LONG_START)
    OUT.mkdir(parents=True, exist_ok=True)
    raw = data_mod.build_returns(
        U, S_long, keys=panel_keys, refresh=refresh, cache_path=LONG_CACHE
    )

    # The panel is ragged: each line's usable history starts when its proxy does.
    # Dropping incomplete rows across ALL keys would let the single shortest
    # series dictate the window for everything, so the growth panel and the
    # glidepath panel are trimmed separately and both windows are reported.
    growth = raw[keys].dropna(how="any")
    glide = raw[panel_keys].dropna(how="any")

    cov = cov_mod.estimate_covariance(growth, S_long)
    cov_all = cov_mod.estimate_covariance(glide, S_long)
    ters = {k: U.instruments[k].ter for k in panel_keys}
    mu = cma_mod.net_of_fees(cma_mod.arithmetic_returns(cma, panel_keys), ters)
    return cfg, U, cma, S_long, growth, glide, cov, cov_all, mu, keys, panel_keys


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

def _floored_constraints(base: PortfolioConstraints) -> PortfolioConstraints:
    """The same mandate with a forced real-asset sleeve, as a comparison case.

    The previous SIPP profile floored a managed-futures sleeve at 5% and a
    real-asset sleeve at 8%. The trend fund is gone (liquidated), so the
    equivalent test here is a single 13% floor on the real-asset sleeve -- gold
    plus infrastructure. It answers the question the floors were there to ask:
    what does compound growth give up if an uncorrelated sleeve is imposed
    rather than earned?
    """
    return dataclasses.replace(
        base, name="SIPP-floored", sleeve_floors={"real_asset": 0.13}
    )


def _bl_optimise(constraints, universe, mu_arith, cov, settings):
    """Black-Litterman posterior, then the geometric optimiser on it.

    Shaped like ``optimise_sipp`` so it can be handed to ``resampled_weights``
    and smoothed the same way.
    """
    bl_mu, _ = robust.black_litterman(constraints, universe, mu_arith, cov, settings)
    return optimise_sipp(constraints, universe, bl_mu, cov, settings)


def compute_methods(cfg, U, mu, cov, S) -> dict[str, pd.Series]:
    """Every allocation method, on the same inputs, unrounded.

    Note which two are averaged into the recommendation and why. Single-point
    mean-variance and single-point Black-Litterman both produce CORNER
    solutions here -- they pile into the three highest-expected-return lines and
    zero the rest. That is not conviction, it is estimation error: the optimiser
    is treating small, uncertain differences in assumed returns as if they were
    known exactly. Michaud resampling is the correction, so it is applied to
    BOTH before they are blended, rather than averaging smoothed and unsmoothed
    answers together. The raw versions are still reported, as evidence for why
    the smoothing is needed.
    """
    cons = cfg.sipp
    keys = list(cons.universe)
    mu_k, cov_k = mu.loc[keys], cov.loc[keys, keys]

    out: dict[str, pd.Series] = {}
    # Unsmoothed, for the diagnostic table only.
    out["max_geometric_raw"] = optimise_sipp(cons, U, mu_k, cov_k, S).weights
    bl_mu, bl_prior = robust.black_litterman(cons, U, mu_k, cov_k, S)
    out["black_litterman_raw"] = optimise_sipp(cons, U, bl_mu, cov_k, S).weights

    # Estimation-error corrected -- these are the ensemble ingredients.
    out["michaud_resampled"] = robust.resampled_weights(
        optimise_sipp, cons, U, mu_k, cov_k, S)
    out["michaud_black_litterman"] = robust.resampled_weights(
        _bl_optimise, cons, U, mu_k, cov_k, S)

    # Return-blind cross-checks.
    out["hrp"] = robust.hrp_weights(cov_k, keys)
    out["erc"] = robust.erc_weights(cov_k, keys)
    # Imposed-diversifier comparison case.
    out["floored"] = robust.resampled_weights(
        optimise_sipp, _floored_constraints(cons), U, mu_k, cov_k, S)

    out = {k: v.reindex(keys).fillna(0.0) for k, v in out.items()}
    out["ensemble"] = robust.ensemble_weights(
        {m: out[m] for m in ENSEMBLE_METHODS}
    ).reindex(keys)
    out["_bl_prior"] = bl_prior
    return out


def _zero_premia_cma(cma):
    """A copy of the CMAs with every factor/tilt premium set to zero."""
    import copy

    flat = copy.deepcopy(cma)
    for block in ("value_premium", "size_value_premium", "profitability_q",
                  "equalweight_tilt", "em_value_premium", "uk_value_premium",
                  "japan_valueup"):
        if block in flat.blocks:
            flat.blocks[block] = 0.0
    return flat


def no_premia_check(cma, U, keys, weights, cov) -> dict:
    """What the recommendation is expected to earn if the factor premia are zero.

    The allocation leans on assumed value, size, quality and EM premia. Those are
    the least certain numbers in the whole exercise, so it is worth stating
    plainly what happens to the expected return if they turn out to be worth
    nothing -- and whether the portfolio would still have been chosen.
    """
    flat = _zero_premia_cma(cma)
    ters = {k: U.instruments[k].ter for k in keys}
    mu_flat = cma_mod.net_of_fees(cma_mod.arithmetic_returns(flat, keys), ters)
    res = summarize("no_premia", weights, mu_flat, cov, "cma_premia_zeroed")
    return {
        "exp_geometric": round(res.exp_geometric, 4),
        "exp_arithmetic": round(res.exp_arithmetic, 4),
        "volatility": round(res.volatility, 4),
        "mu_by_holding": {k: round(float(mu_flat[k]), 4) for k in weights.index},
    }


def recommended_weights(methods: dict[str, pd.Series], weight_max: float) -> pd.Series:
    """Ensemble, cleaned to a low-maintenance line count."""
    w = clean_weights(methods["ensemble"], MIN_HOLDING, weight_max)
    return w[w > 0].sort_values(ascending=False)


# ---------------------------------------------------------------------------
# ii regular-investing ladder
# ---------------------------------------------------------------------------

def instruction_ladder(weights: pd.Series, monthly_gbp: float, execution: dict,
                       universe) -> pd.DataFrame:
    """Translate target weights into ii's fixed-GBP monthly instructions.

    ii takes amounts, not percentages, and fills instructions in the order they
    were added when there is not enough cash. Contractor income varies with
    billable days, so the ladder is ordered largest-first: a light month then
    degrades toward the core holdings instead of failing outright or starving
    the biggest sleeve.
    """
    min_gbp = float(execution.get("min_instruction_gbp", 25))
    max_lines = int(execution.get("max_instructions", 25))
    if len(weights) > max_lines:
        raise ValueError(f"{len(weights)} lines exceeds the ii maximum of {max_lines}.")

    amounts = (weights * monthly_gbp).round(0)
    # Push any rounding difference onto the largest line so the ladder sums exactly.
    amounts.iloc[0] += monthly_gbp - amounts.sum()

    rows = []
    for order, (key, amt) in enumerate(amounts.items(), start=1):
        inst = universe.instruments[key]
        rows.append({
            "order": order,
            "key": key,
            "ticker": inst.ticker,
            "name": inst.name,
            "sleeve": inst.sleeve,
            "weight": round(float(weights[key]), 4),
            "pct": round(float(weights[key]) * 100, 1),
            "monthly_gbp": int(amt),
            "ter": inst.ter,
            "accumulating": inst.accumulating,
            "clears_ii_minimum": bool(amt >= min_gbp),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _stream_dict(res: lc.StreamResult) -> dict:
    return {
        "total_contributed": round(res.total_contributed),
        "median_gbp": round(res.median_gbp),
        "p5_gbp": round(res.p5_gbp),
        "p25_gbp": round(res.p25_gbp),
        "p75_gbp": round(res.p75_gbp),
        "p95_gbp": round(res.p95_gbp),
        "median_multiple": round(res.median_multiple, 2),
        "p5_multiple": round(res.p5_multiple, 2),
        "prob_below_contributions": round(res.prob_below_contributions, 4),
        "money_weighted_return": round(res.money_weighted_return, 4),
        "worst_drawdown_median": round(res.worst_drawdown_median, 4),
        "worst_drawdown_p5": round(res.worst_drawdown_p5, 4),
    }


def validate(weights, growth_returns, glide_returns, mu, cov_all, contributions,
             contrib_cfg, sipp_cfg, S, cma_blocks, mu_no_premia):
    """Bootstrap the recommendation, the glidepath, the tracker and the tails."""
    keys = list(weights.index)
    panel = lc.recentre(growth_returns[keys], mu)
    n_paths, seed = S.mc_paths, S.random_seed
    n_months = len(contributions)

    fee_kw = dict(
        monthly_fee=float(sipp_cfg.get("platform_fee_monthly_gbp", 0.0)),
        monthly_fee_above=float(sipp_cfg.get("platform_fee_monthly_gbp_above_100k", 0.0)) or None,
        fee_threshold_gbp=100_000.0,
    )
    opening = float(contrib_cfg.get("opening_balance_gbp", 0.0))

    # --- headline: bootstrap vs the Gaussian model on identical inputs -------
    boot = lc.bootstrap_paths(panel, n_paths, n_months, seed, block_mean=12)
    w_path = lc.constant_weight_path(weights, n_months)
    boot_wealth = lc.accumulate(boot, w_path, contributions, opening, **fee_kw)
    boot_res = lc.summarise_stream(boot_wealth, contributions)

    norm = lc.normal_paths(mu, cov_all, keys, n_paths, n_months, seed)
    norm_res = lc.summarise_stream(
        lc.accumulate(norm, w_path, contributions, opening, **fee_kw), contributions
    )

    # --- passive global tracker, same draws, same fees ------------------------
    tracker_w = pd.Series(TRACKER)
    tracker_keys = list(tracker_w.index)
    tracker_mu = float(cma_blocks["equity_dev"]) - TRACKER_TER
    tracker_panel = lc.recentre(
        growth_returns[tracker_keys],
        pd.Series({k: tracker_mu for k in tracker_keys}),   # untilted equity beta
    )
    tracker_draws = lc.bootstrap_paths(tracker_panel, n_paths, n_months, seed, block_mean=12)
    tracker_wealth = lc.accumulate(
        tracker_draws, lc.constant_weight_path(tracker_w, n_months),
        contributions, opening, **fee_kw,
    )
    tracker_res = lc.summarise_stream(tracker_wealth, contributions)
    prob_beat = float((boot_wealth[:, -1] > tracker_wealth[:, -1]).mean())

    # --- glidepath ------------------------------------------------------------
    # Uses the (shorter) window where the defensive line also has history, so the
    # de-risking comparison is run on a panel where every asset is observed.
    glide_panel = lc.recentre(glide_returns, mu)
    derisk_start = int(
        (contrib_cfg["horizon_years"] - contrib_cfg["derisk_start_years_before"]) * 12
    )
    glide = lc.evaluate_glidepath(
        weights, pd.Series(DEFENSIVE), glide_panel, contributions, n_paths, seed,
        derisk_start_month=derisk_start,
        derisk_months=int(contrib_cfg["derisk_years"] * 12),
        terminal_defensive_frac=float(contrib_cfg["terminal_defensive_frac"]),
        opening_balance=opening, **fee_kw,
    )

    # --- sequence risk --------------------------------------------------------
    seq = lc.sequence_risk_decomposition(
        weights, panel, contributions, n_paths, seed, shock=-0.40,
        shock_years=(1, 3, 5, 10, 15, 20, 23),
        opening_balance=opening, **fee_kw,
    )

    # --- the same race with the factor premia switched off --------------------
    # P(beat tracker) above is largely a restatement of the assumed premia, since
    # both sides are recentred onto their CMAs. Re-running it with every tilt
    # premium set to zero shows what the tilt is actually risking.
    no_premia_panel = lc.recentre(growth_returns[keys], mu_no_premia)
    np_wealth = lc.accumulate(
        lc.bootstrap_paths(no_premia_panel, n_paths, n_months, seed, block_mean=12),
        w_path, contributions, opening, **fee_kw,
    )
    no_premia_res = lc.summarise_stream(np_wealth, contributions)
    no_premia_beat = float((np_wealth[:, -1] > tracker_wealth[:, -1]).mean())

    fee_table = lc.flat_fee_drag(
        np.median(boot_wealth, axis=0), fee_kw["monthly_fee"]
    )
    return {
        "bootstrap": boot_res, "normal": norm_res, "tracker": tracker_res,
        "prob_beat_tracker": prob_beat, "glidepath": glide,
        "no_premia_stream": no_premia_res, "no_premia_beat_tracker": no_premia_beat,
        "sequence_risk": seq, "fee_table": fee_table,
        "boot_wealth_median_path": np.median(boot_wealth, axis=0),
        "derisk_start_month": derisk_start,
    }


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _charts(bundle: dict, v: dict, contributions: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, accent, warm = "#16314f", "#9fb6d6", "#c2703d"

    # 1. Outcome fan: bootstrap vs normal vs tracker -------------------------
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    labels = ["Recommended\n(block bootstrap)", "Same portfolio\n(normal model)",
              "Passive global\ntracker"]
    res = [v["bootstrap"], v["normal"], v["tracker"]]
    for i, r in enumerate(res):
        ax.bar(i, r.p95_gbp - r.p5_gbp, bottom=r.p5_gbp, width=0.45,
               color=accent, alpha=0.55,
               label="5th-95th percentile" if i == 0 else None)
        ax.plot([i - 0.28, i + 0.28], [r.median_gbp] * 2, color=ink, lw=2.5,
                label="median" if i == 0 else None)
        ax.annotate(f"£{r.median_gbp:,.0f}", (i, r.median_gbp),
                    textcoords="offset points", xytext=(0, 8), ha="center",
                    fontsize=9, color=ink)
    total_in = contributions.sum()
    ax.axhline(total_in, ls="--", color=warm, lw=1.2,
               label=f"total contributed £{total_in:,.0f}")
    ax.set_xticks(range(3)); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("pot at age 57 (2049)")
    ax.yaxis.set_major_formatter(lambda x, _: f"£{x/1e6:.1f}m" if x >= 1e6 else f"£{x/1e3:.0f}k")
    ax.set_title("23-year outcome range on a monthly contribution stream", fontsize=11)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT / "wealth_23y.png", dpi=120); plt.close(fig)

    # 2. Glidepath ------------------------------------------------------------
    g = v["glidepath"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.2))
    months = np.arange(len(contributions))
    progress = np.clip(
        (months - g.derisk_start_month) / max(g.derisk_months, 1), 0, 1
    ) * g.terminal_defensive_frac
    ax1.fill_between(months / 12, 0, (1 - progress) * 100, color=accent, alpha=0.75,
                     label="growth assets")
    ax1.fill_between(months / 12, (1 - progress) * 100, 100, color=warm, alpha=0.65,
                     label="defensive (short gilts / cash-like)")
    ax1.set_xlabel("years from now"); ax1.set_ylabel("% of pot")
    ax1.set_ylim(0, 100); ax1.set_xlim(0, len(contributions) / 12)
    ax1.set_title("De-risking schedule", fontsize=10); ax1.legend(fontsize=8, loc="lower left")

    for i, (label, r) in enumerate([("Static", g.static), ("Glidepath", g.glidepath)]):
        ax2.bar(i, r.p95_gbp - r.p5_gbp, bottom=r.p5_gbp, width=0.45,
                color=accent, alpha=0.55)
        ax2.plot([i - 0.28, i + 0.28], [r.median_gbp] * 2, color=ink, lw=2.5)
        ax2.annotate(f"£{r.median_gbp:,.0f}", (i, r.median_gbp),
                     textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax2.set_xticks([0, 1]); ax2.set_xticklabels(["Static\n(never de-risks)", "Glidepath"], fontsize=9)
    ax2.yaxis.set_major_formatter(lambda x, _: f"£{x/1e6:.1f}m" if x >= 1e6 else f"£{x/1e3:.0f}k")
    ax2.set_title("What de-risking costs and saves", fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "glidepath.png", dpi=120); plt.close(fig)

    # 3. Sequence risk --------------------------------------------------------
    seq = v["sequence_risk"]
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.bar(seq["shock_year"], seq["vs_baseline_pct"] * 100, width=1.4,
           color=[accent if x > -20 else warm for x in seq["vs_baseline_pct"] * 100])
    ax.axhline(0, color=ink, lw=1)
    ax.set_xlabel("year the -40% crash lands")
    ax.set_ylabel("impact on the pot at 57 (%)")
    ax.set_title("The same crash costs far more late than early", fontsize=11)
    ax.set_ylim(seq["vs_baseline_pct"].min() * 100 - 6, 2)   # headroom for the labels
    for _, r in seq.iterrows():
        ax.annotate(f"{r['vs_baseline_pct']*100:.0f}%", (r["shock_year"], r["vs_baseline_pct"] * 100),
                    textcoords="offset points", xytext=(0, -13), ha="center", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "sequence_risk.png", dpi=120); plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(refresh: bool = False) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg, U, cma, S, growth, glide_panel, cov, cov_all, mu, keys, panel_keys = build_inputs(refresh)
    contrib = cfg.sipp.contributions
    raw_sipp = {
        "platform_fee_monthly_gbp": 5.99,
        "platform_fee_monthly_gbp_above_100k": 14.99,
    }
    # Re-read the raw TOML values that PortfolioConstraints does not carry.
    import tomllib
    with open(Path(__file__).resolve().parents[1] / "config" / "constraints.toml", "rb") as fh:
        raw_sipp.update({k: val for k, val in tomllib.load(fh)["sipp"].items()
                         if isinstance(val, (int, float))})

    methods = compute_methods(cfg, U, mu, cov, S)
    weights = recommended_weights(methods, cfg.sipp.weight_max)
    res = summarize("recommended", weights, mu, cov, "ensemble(michaud_geo + michaud_bl)")

    contributions = lc.contribution_schedule(
        float(contrib["monthly_gbp"]), int(contrib["horizon_years"]),
        float(contrib.get("escalation_annual", 0.0)),
    )
    flat_cma = _zero_premia_cma(cma)
    mu_no_premia = cma_mod.net_of_fees(
        cma_mod.arithmetic_returns(flat_cma, panel_keys),
        {k: U.instruments[k].ter for k in panel_keys})
    v = validate(weights, growth, glide_panel, mu, cov_all, contributions, contrib,
                 raw_sipp, S, cma.blocks, mu_no_premia)

    ladder = instruction_ladder(weights, float(contrib["monthly_gbp"]),
                                cfg.sipp.execution, U)
    ladder.to_csv(OUT / "targets_recommended.csv", index=False)

    # --- method comparison ---------------------------------------------------
    comp = pd.DataFrame({m: methods[m] for m in
                         ["max_geometric_raw", "black_litterman_raw",
                          "michaud_resampled", "michaud_black_litterman",
                          "ensemble", "hrp", "erc", "floored"]}).round(4)
    comp.index.name = "key"
    stats = {}
    for m in comp.columns:
        r = summarize(m, comp[m], mu, cov, m)
        stats[m] = {"exp_geometric": round(r.exp_geometric, 4),
                    "exp_arithmetic": round(r.exp_arithmetic, 4),
                    "volatility": round(r.volatility, 4)}
    comp_out = pd.concat([comp, pd.DataFrame(stats).round(4)])
    comp_out.to_csv(OUT / "method_comparison.csv")

    v["sequence_risk"].round(4).to_csv(OUT / "sequence_risk.csv", index=False)
    v["fee_table"].round(6).to_csv(OUT / "fee_drag.csv", index=False)

    # Sensitivity is run TWICE. On the raw optimiser it measures how far a corner
    # solution can jump, which overstates the instability of what we actually
    # recommend; on the resampled engine it measures how far the recommendation
    # itself moves. The second is the honest number, so both are published.
    sens_summary, sens_full = sens_mod.sensitivity_table(
        optimise_sipp, cfg.sipp, U, cma, cov.loc[keys, keys], S)
    sens_summary.round(4).to_csv(OUT / "sensitivity_raw.csv", index=False)
    sens_full.round(4).to_csv(OUT / "sensitivity_weights.csv")

    S_fast = dataclasses.replace(S, resample_draws=60)

    def _resampled_opt(constraints, universe, mu_arith, cov_in, settings):
        w = robust.resampled_weights(
            optimise_sipp, constraints, universe, mu_arith, cov_in, settings)
        return summarize("resampled", w, mu_arith, cov_in, "michaud")

    sens_smooth, _ = sens_mod.sensitivity_table(
        _resampled_opt, cfg.sipp, U, cma, cov.loc[keys, keys], S_fast)
    sens_smooth.round(4).to_csv(OUT / "sensitivity.csv", index=False)

    # --- bundle --------------------------------------------------------------
    sleeves: dict[str, float] = {}
    for k, w in weights.items():
        sleeves[U.sleeve_of(k)] = sleeves.get(U.sleeve_of(k), 0.0) + float(w)
    blended_ter = float(sum(weights[k] * U.instruments[k].ter for k in weights.index))
    g = v["glidepath"]

    bundle = {
        "meta": {
            "mandate": "Interactive Investor SIPP, monthly contributions, access at 57 in 2049",
            "horizon_years": int(contrib["horizon_years"]),
            "target_year": int(contrib["target_year"]),
            "monthly_contribution_gbp": float(contrib["monthly_gbp"]),
            "annual_contribution_gbp": float(contrib["monthly_gbp"]) * 12,
            "opening_balance_gbp": float(contrib["opening_balance_gbp"]),
            "history_start": f"{growth.index.min():%Y-%m}",
            "history_end": f"{growth.index.max():%Y-%m}",
            "history_months": int(len(growth)),
            "glidepath_history_start": f"{glide_panel.index.min():%Y-%m}",
            "glidepath_history_months": int(len(glide_panel)),
            # True when the window covers the 2008 crash itself (Sep-Dec 2008),
            # which is the stress event that matters, even if it starts after the
            # October 2007 market peak.
            "includes_gfc_crash": bool(growth.index.min() <= pd.Timestamp("2008-08-31")),
            "mc_paths": S.mc_paths,
            "resample_draws": S.resample_draws,
            "random_seed": S.random_seed,
            "block_mean_months": 12,
            "min_holding": MIN_HOLDING,
            "blended_ter": round(blended_ter, 5),
            "ensemble_methods": list(ENSEMBLE_METHODS),
            "platform_fee_monthly_gbp": raw_sipp["platform_fee_monthly_gbp"],
            "recentred": "Bootstrap panel shifted so each column's mean equals its "
                         "CMA expected return; higher moments left untouched.",
        },
        "recommended": {
            "label": "Ensemble growth portfolio",
            "exp_geometric": round(res.exp_geometric, 4),
            "exp_arithmetic": round(res.exp_arithmetic, 4),
            "volatility": round(res.volatility, 4),
            "n_holdings": int(len(weights)),
            "sleeves": {k: round(val, 4) for k, val in sorted(sleeves.items(), key=lambda x: -x[1])},
            "weights": ladder.to_dict("records"),
            "risk_contributions": {
                k: round(float(val), 4)
                for k, val in robust.risk_contributions(weights, cov).items()
            },
        },
        "outcomes": {
            "bootstrap": _stream_dict(v["bootstrap"]),
            "normal_model": _stream_dict(v["normal"]),
            "passive_tracker": _stream_dict(v["tracker"]),
            "prob_beat_tracker": round(v["prob_beat_tracker"], 3),
            "normal_vs_bootstrap_p5_gap_pct": round(
                v["normal"].p5_gbp / v["bootstrap"].p5_gbp - 1, 4),
        },
        "glidepath": {
            "derisk_start_year": round(v["derisk_start_month"] / 12, 1),
            "derisk_years": int(contrib["derisk_years"]),
            "terminal_defensive_frac": float(contrib["terminal_defensive_frac"]),
            "defensive_mix": DEFENSIVE,
            "static": _stream_dict(g.static),
            "glidepath": _stream_dict(g.glidepath),
            "median_cost_pct": round(g.glidepath.median_gbp / g.static.median_gbp - 1, 4),
            "p5_benefit_pct": round(g.glidepath.p5_gbp / g.static.p5_gbp - 1, 4),
        },
        "stability": {
            "max_weight_move_raw_engine": round(float(sens_summary["max_weight_move"].max()), 4),
            "max_weight_move_resampled_engine": round(float(sens_smooth["max_weight_move"].max()), 4),
            "most_sensitive_block": str(sens_smooth.iloc[0]["block"]),
            "geo_spread_worst_block": round(float(sens_smooth["geo_spread"].max()), 4),
        },
        "no_premia_check": {
            **no_premia_check(cma, U, keys, weights, cov),
            "bootstrap": _stream_dict(v["no_premia_stream"]),
            "prob_beat_tracker": round(v["no_premia_beat_tracker"], 3),
        },
        "sequence_risk": v["sequence_risk"].round(4).to_dict("records"),
        "method_comparison": {m: stats[m] for m in comp.columns},
        "instruments": {
            k: {"ticker": U.instruments[k].ticker, "name": U.instruments[k].name,
                "sleeve": U.instruments[k].sleeve, "role": U.instruments[k].role,
                "ter": U.instruments[k].ter, "accumulating": U.instruments[k].accumulating,
                "mu_arith": round(float(mu[k]), 4),
                "vol": round(float(cov_mod.annual_vol(cov_all)[k]), 4)}
            for k in panel_keys
        },
    }

    (OUT / "results.json").write_text(json.dumps(bundle, indent=2))
    _charts(bundle, v, contributions)
    _write_refresh_note(bundle, refresh)
    _print_summary(bundle)
    print(f"\nWrote {OUT}/results.json (+ 5 CSVs, 3 PNGs, REFRESH_NOTE.md)")
    return bundle


def _write_refresh_note(bundle: dict, refresh: bool) -> None:
    m = bundle["meta"]
    (OUT / "REFRESH_NOTE.md").write_text(
        f"""# SIPP 23y build — data provenance

- Data path: **{"live refresh from yfinance" if refresh else "cached panel"}**
  (`returns_monthly_long.csv`, private to this mandate).
- History: **{m['history_start']} to {m['history_end']}** ({m['history_months']} months).
- Includes the 2008 global financial crisis: **{'yes' if m['includes_gfc_crash'] else 'NO -- modelled drawdowns are optimistic'}**.
- Bootstrap: stationary block bootstrap, mean block {m['block_mean_months']} months,
  {m['mc_paths']:,} paths, seed {m['random_seed']}.
- {m['recentred']}

This cache is separate from `outputs/returns_monthly.csv` on purpose: the ISA
build uses a 2009 start, and a longer window here must not silently change the
covariance behind an already-published allocation.

Regenerate with:

    python -m portfolio_optimiser.report.build_sipp_23y --refresh
""")


def _print_summary(b: dict) -> None:
    m, r, o, g = b["meta"], b["recommended"], b["outcomes"], b["glidepath"]
    print("\n" + "=" * 78)
    print(f"{r['label']} — £{m['monthly_contribution_gbp']:,.0f}/month for "
          f"{m['horizon_years']} years to {m['target_year']}")
    print(f"  history {m['history_start']}..{m['history_end']} ({m['history_months']} mo, "
          f"GFC crash included: {m['includes_gfc_crash']})")
    print(f"  exp {r['exp_geometric']:.2%} geo / {r['exp_arithmetic']:.2%} arith · "
          f"vol {r['volatility']:.2%} · TER {m['blended_ter']:.2%} · "
          f"{r['n_holdings']} holdings")
    print("  sleeves: " + ", ".join(f"{k} {val:.0%}" for k, val in r["sleeves"].items()))
    print("  ladder:  " + ", ".join(
        f"{w['ticker']} {w['pct']}% (£{w['monthly_gbp']})" for w in r["weights"]))
    bt, nm, tr = o["bootstrap"], o["normal_model"], o["passive_tracker"]
    print(f"\n  paid in            £{bt['total_contributed']:,}")
    print(f"  bootstrap  median  £{bt['median_gbp']:,}  p5 £{bt['p5_gbp']:,}  "
          f"p95 £{bt['p95_gbp']:,}  (x{bt['median_multiple']} of contributions)")
    print(f"  normal     median  £{nm['median_gbp']:,}  p5 £{nm['p5_gbp']:,}"
          f"   <- p5 is {o['normal_vs_bootstrap_p5_gap_pct']:+.0%} vs bootstrap")
    print(f"  tracker    median  £{tr['median_gbp']:,}   P(beat) {o['prob_beat_tracker']:.0%}")
    print(f"  money-weighted return {bt['money_weighted_return']:.2%} · "
          f"worst DD median {bt['worst_drawdown_median']:.0%} / p5 {bt['worst_drawdown_p5']:.0%}")
    print(f"\n  glidepath from year {g['derisk_start_year']:.0f} to "
          f"{g['terminal_defensive_frac']:.0%} defensive: "
          f"median {g['median_cost_pct']:+.1%}, p5 {g['p5_benefit_pct']:+.1%}")
    print("  method comparison (geo / vol):")
    for name, s in b["method_comparison"].items():
        print(f"    {name:20s} {s['exp_geometric']:.2%} / {s['volatility']:.2%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch market data")
    main(refresh=ap.parse_args().refresh)
