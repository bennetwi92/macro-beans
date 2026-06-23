"""The two portfolio optimisers and a shared result container.

  * ``optimise_sipp`` -- maximise expected geometric growth (Portfolio B).
  * ``optimise_isa``  -- maximise geometric growth subject to a hard liquidity
                         floor (ballast covers the 1-yr need) and a CVaR cap
                         (Portfolio A).

Both return an ``OptResult`` with cleaned weights and summary statistics.
"""

from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np
import pandas as pd

from . import objectives as obj
from .config import PortfolioConstraints, Settings, Universe


@dataclass
class OptResult:
    name: str
    weights: pd.Series        # cleaned, sums to 1
    exp_geometric: float      # annual geometric growth
    exp_arithmetic: float     # annual arithmetic return
    volatility: float         # annual stdev
    method: str = "convex"
    diagnostics: dict | None = None


_SOLVERS = (cp.CLARABEL, cp.SCS)


def _solve(prob: cp.Problem, w: cp.Variable) -> None:
    """Try the bundled convex solvers in order until one returns a solution."""
    for solver in _SOLVERS:
        try:
            prob.solve(solver=solver)
        except Exception:
            continue
        if w.value is not None:
            return


def _sleeve_index(universe: Universe, keys: list[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, k in enumerate(keys):
        out.setdefault(universe.sleeve_of(k), []).append(i)
    return out


def _clean_weights(
    w: np.ndarray, keys: list[str], min_holding: float, weight_max: float = 1.0
) -> pd.Series:
    """Zero sub-threshold dust, renormalise, then water-fill so no weight exceeds
    the cap (renormalising after dropping dust can otherwise nudge a capped
    holding over the band)."""
    w = np.where(w < min_holding, 0.0, w)
    if w.sum() == 0:
        w = np.ones_like(w) / len(w)
    w = w / w.sum()

    # Iteratively cap and redistribute the excess to uncapped holdings.
    for _ in range(100):
        over = w > weight_max + 1e-12
        if not over.any():
            break
        excess = (w[over] - weight_max).sum()
        w[over] = weight_max
        room = ~over & (w > 0)
        if not room.any():
            break
        w[room] += excess * w[room] / w[room].sum()
    return pd.Series(w, index=keys, name="weight")


def clean_weights(
    w: pd.Series, min_holding: float, weight_max: float = 1.0
) -> pd.Series:
    """Public wrapper: tidy an arbitrary weight vector (e.g. resampled average)
    into a Pie-ready allocation (drop dust, renormalise, respect the cap)."""
    cleaned = _clean_weights(w.values.astype(float), list(w.index), min_holding, weight_max)
    return cleaned


def summarize(
    name: str, weights: pd.Series, mu_arith: pd.Series, cov: pd.DataFrame,
    method: str, diagnostics: dict | None = None,
) -> OptResult:
    """Build an OptResult (geo/arith/vol) for an externally-supplied weight set."""
    geo, arith, vol = _summary(weights, mu_arith, cov)
    return OptResult(name, weights, geo, arith, vol, method, diagnostics)


def _summary(w: pd.Series, mu: pd.Series, cov: pd.DataFrame) -> tuple[float, float, float]:
    wv = w.values
    mv = mu.loc[w.index].values
    cv = cov.loc[w.index, w.index].values
    arith = float(wv @ mv)
    var = float(wv @ cv @ wv)
    geo = arith - 0.5 * var
    return geo, arith, float(np.sqrt(var))


def optimise_sipp(
    constraints: PortfolioConstraints,
    universe: Universe,
    mu_arith: pd.Series,
    cov: pd.DataFrame,
    settings: Settings,
) -> OptResult:
    keys = constraints.universe
    mu = mu_arith.loc[keys].values
    sigma = cov.loc[keys, keys].values
    n = len(keys)

    w = cp.Variable(n)
    sleeve_idx = _sleeve_index(universe, keys)
    cons = obj.base_constraints(
        w, n, constraints.weight_min, constraints.weight_max,
        constraints.sleeve_caps, sleeve_idx, constraints.sleeve_floors,
    )
    prob = cp.Problem(cp.Maximize(obj.geometric_objective(w, mu, sigma)), cons)
    _solve(prob, w)

    weights = _clean_weights(np.asarray(w.value).flatten(), keys, settings.min_holding, constraints.weight_max)
    geo, arith, vol = _summary(weights, mu_arith, cov)
    return OptResult("SIPP", weights, geo, arith, vol, "convex_geometric",
                     {"status": prob.status})


def optimise_isa(
    constraints: PortfolioConstraints,
    universe: Universe,
    mu_arith: pd.Series,
    cov: pd.DataFrame,
    settings: Settings,
) -> OptResult:
    keys = constraints.universe
    mu = mu_arith.loc[keys].values
    sigma = cov.loc[keys, keys].values
    n = len(keys)

    w = cp.Variable(n)
    sleeve_idx = _sleeve_index(universe, keys)
    cons = obj.base_constraints(
        w, n, constraints.weight_min, constraints.weight_max,
        constraints.sleeve_caps, sleeve_idx, constraints.sleeve_floors,
    )

    # Liquidity floor: ballast sleeve weight >= floor / portfolio value.
    floor_frac = constraints.liquidity_floor_gbp / constraints.value_gbp
    ballast_idx = sleeve_idx.get(constraints.ballast_sleeve, [])
    if not ballast_idx:
        raise ValueError(
            f"No instruments in ballast sleeve '{constraints.ballast_sleeve}'."
        )
    cons.append(cp.sum(w[ballast_idx]) >= min(floor_frac, 1.0))

    # Tail constraint: CVaR of the 1-year loss <= limit.
    scen = obj.make_scenarios(mu, sigma, settings.mc_paths // 4, settings.random_seed)
    cvar_cons, _, _ = obj.cvar_constraints(w, scen, constraints.cvar_alpha, constraints.cvar_limit)
    cons += cvar_cons

    prob = cp.Problem(cp.Maximize(obj.geometric_objective(w, mu, sigma)), cons)
    _solve(prob, w)
    if w.value is None:
        raise RuntimeError(
            f"ISA optimisation infeasible (status={prob.status}). The liquidity "
            f"floor ({floor_frac:.0%} ballast) and CVaR cap ({constraints.cvar_limit:.0%}) "
            "may conflict with the per-asset caps -- relax one in constraints.toml."
        )

    weights = _clean_weights(np.asarray(w.value).flatten(), keys, settings.min_holding, constraints.weight_max)
    geo, arith, vol = _summary(weights, mu_arith, cov)

    floor_ok = weights[[keys[i] for i in ballast_idx]].sum() >= floor_frac - 1e-6
    return OptResult("ISA", weights, geo, arith, vol, "convex_geometric_cvar",
                     {"status": prob.status, "ballast_weight": float(
                         weights[[keys[i] for i in ballast_idx]].sum()),
                      "floor_frac": floor_frac, "floor_satisfied": bool(floor_ok)})
