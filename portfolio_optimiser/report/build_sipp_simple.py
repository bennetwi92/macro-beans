"""Simplified SIPP: exhaustive k-of-n subset search for a small, holdable book.

The 8-holding SIPP target is optimal but fiddly to run by hand. This driver asks
a narrower question: **if the SIPP may hold only k funds, which k, and in what
weights?**

Method
------
* Enumerate every k-subset of ``[sipp].universe`` (C(8,4) = 70 by default).
* For each subset, estimate the covariance **on that subset's own keys**. This
  matters: ``estimate_covariance`` is complete-case (``dropna(how="any")``), so
  pricing the full 19-instrument matrix collapses the window to the shortest
  series in it -- currently 79 months, because Yahoo's JMFP.L feed dies in
  2020-12. Scoring each subset on its own keys recovers the full common history
  for subsets that exclude the broken series (211 months for most).
* Optimise each subset with the same max-geometric-growth objective and the same
  Michaud resampling the main report recommends, then Monte Carlo the shortlist.
* Rank on geometric growth, but report the estimation window alongside, because
  a headline built on 119 months is not comparable to one built on 211.

Per-holding cap
---------------
``[sipp].weight_max`` (0.30) is arithmetically infeasible at k=4: the diversifier
and real-asset sleeve caps (15% each) leave >=70% for at most two equity slots,
so a cap below 0.35 admits no solution. This driver therefore uses ``--weight-max``
(default 0.40). That is a consequence of holding fewer funds, not a change of
risk appetite.

Run:
    python -m portfolio_optimiser.report.build_sipp_simple            # k=4
    python -m portfolio_optimiser.report.build_sipp_simple --k 5
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
from pathlib import Path

import pandas as pd

from ..optimiser import cma as cma_mod
from ..optimiser import covariance as cov_mod
from ..optimiser import data as data_mod
from ..optimiser.config import load_all
from ..optimiser.optimize import _summary, clean_weights, optimise_sipp
from ..optimiser.robust import resampled_weights
from . import validate

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs" / "sipp_simple"
HEDGE_SLEEVES = {"diversifier", "real_asset"}


def _score(keys, wmax, cfg, returns, mu):
    """Resampled weights + summary for one subset, priced on its own history."""
    keys = list(keys)
    sub = returns[keys].dropna(how="any")
    cov = cov_mod.estimate_covariance(sub, cfg.settings)
    c = dataclasses.replace(cfg.sipp, universe=keys, weight_max=wmax)
    w = resampled_weights(optimise_sipp, c, cfg.universe, mu, cov, cfg.settings)
    w = clean_weights(w, cfg.settings.min_holding, wmax)
    geo, arith, vol = _summary(w, mu, cov)
    return w, cov, dict(geo=geo, arith=arith, vol=vol, months=len(sub))


def main(k: int = 4, weight_max: float = 0.40, refresh: bool = False,
         shortlist: int = 5) -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    cfg = load_all()
    U, S, CMA = cfg.universe, cfg.settings, cfg.cma

    all_keys = sorted(set(cfg.isa.universe) | set(cfg.sipp.universe))
    returns = data_mod.build_returns(U, S, keys=all_keys, refresh=refresh)
    mu = cma_mod.net_of_fees(
        cma_mod.arithmetic_returns(CMA, all_keys),
        {kk: U.instruments[kk].ter for kk in all_keys},
    )
    full = cfg.sipp.universe
    combos = list(itertools.combinations(full, k))
    print(f"Scoring {len(combos)} {k}-fund subsets of {len(full)} ...")

    rows = []
    for combo in combos:
        try:
            w, _, st = _score(combo, weight_max, cfg, returns, mu)
        except Exception as exc:
            print(f"  skip {'+'.join(combo)}: {type(exc).__name__}")
            continue
        if w is None or abs(w.sum() - 1) > 1e-4:
            continue
        sleeves = {U.sleeve_of(x) for x in combo}
        rows.append({
            "combo": "+".join(combo),
            **st,
            "min_weight": float(w.min()),
            "genuine_k": bool(w.min() >= 0.05),
            "hedge_sleeves": len(sleeves & HEDGE_SLEEVES),
            **{f"w_{x}": float(w.get(x, 0.0)) for x in full},
        })

    df = pd.DataFrame(rows).sort_values("geo", ascending=False)
    df.round(4).to_csv(OUTPUTS / f"candidates_k{k}.csv", index=False)
    print(f"Wrote {OUTPUTS / f'candidates_k{k}.csv'} ({len(df)} feasible)")

    # ---- Monte Carlo the shortlist + the full-universe baseline --------------
    bench = data_mod.benchmark_returns(S)
    bench_mu = CMA.blocks.get("equity_dev", 0.07)
    years = CMA.meta.get("horizon_years", 25)

    picks = list(df[df.genuine_k].head(shortlist)["combo"])
    best_hedged = df[df.genuine_k & (df.hedge_sleeves > 0)].head(1)["combo"].tolist()
    for c in best_hedged:
        if c not in picks:
            picks.append(c)
    picks.append("+".join(full))

    mc_rows = []
    for combo in picks:
        keys = combo.split("+")
        wmax = weight_max if len(keys) == k else cfg.sipp.weight_max
        w, cov, st = _score(keys, wmax, cfg, returns, mu)
        tw = validate.terminal_wealth(w, mu, cov, bench, bench_mu,
                                      returns, S, years=years)
        mc_rows.append({
            "combo": combo, "n": len(keys), **st,
            "median_multiple": tw.median_multiple,
            "p5_multiple": tw.p5_multiple,
            "prob_beat_benchmark": tw.prob_beat_benchmark,
            **{f"w_{x}": float(w.get(x, 0.0)) for x in full},
        })
    mc = pd.DataFrame(mc_rows)
    mc.round(4).to_csv(OUTPUTS / f"shortlist_k{k}.csv", index=False)

    print(f"\n{'build':38} {'n':>2} {'geo':>7} {'vol':>7} {'med':>7} {'P(beat)':>8} {'months':>7}")
    for _, r in mc.iterrows():
        print(f"{r.combo:38} {r.n:2.0f} {r.geo*100:6.2f}% {r.vol*100:6.2f}% "
              f"{r.median_multiple:6.2f}x {r.prob_beat_benchmark:7.0%} {r.months:7.0f}")
    print(f"\nWrote {OUTPUTS / f'shortlist_k{k}.csv'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4, help="number of holdings")
    ap.add_argument("--weight-max", type=float, default=0.40)
    ap.add_argument("--refresh", action="store_true", help="re-fetch market data")
    ap.add_argument("--shortlist", type=int, default=5)
    a = ap.parse_args()
    main(k=a.k, weight_max=a.weight_max, refresh=a.refresh, shortlist=a.shortlist)
