"""Convex building blocks shared by the two optimisers.

We use cvxpy. The geometric-growth objective is a concave quadratic; the CVaR
constraint (Rockafellar-Uryasev) is linear in the weights once we add the
auxiliary VaR/shortfall variables, so the ISA problem stays a single convex
program.
"""

from __future__ import annotations

import cvxpy as cp
import numpy as np


def geometric_objective(w: cp.Variable, mu_arith: np.ndarray, cov: np.ndarray) -> cp.Expression:
    """Maximand: g(w) = mu'w - 0.5 w'Sigma w (geometric growth approximation)."""
    return mu_arith @ w - 0.5 * cp.quad_form(w, cp.psd_wrap(cov))


def base_constraints(
    w: cp.Variable,
    n: int,
    weight_min: float,
    weight_max: float,
    sleeve_caps: dict[str, float],
    sleeve_index: dict[str, list[int]],
    sleeve_floors: dict[str, float] | None = None,
) -> list:
    """Long-only, fully invested, per-asset band, per-sleeve caps and floors.

    Sleeve floors encode investor-preference structure (e.g. "always hold a crash
    diversifier sleeve") that a pure return objective would otherwise skip; they
    are convex (linear >=) so they keep the problem and its resampled average
    feasible.
    """
    cons = [cp.sum(w) == 1, w >= weight_min, w <= weight_max]
    for sleeve, cap in sleeve_caps.items():
        idx = sleeve_index.get(sleeve, [])
        if idx:
            cons.append(cp.sum(w[idx]) <= cap)
    for sleeve, floor in (sleeve_floors or {}).items():
        idx = sleeve_index.get(sleeve, [])
        if idx:
            cons.append(cp.sum(w[idx]) >= floor)
    return cons


def cvar_constraints(
    w: cp.Variable,
    scenarios: np.ndarray,
    alpha: float,
    limit: float,
) -> tuple[list, cp.Variable, cp.Variable]:
    """Rockafellar-Uryasev CVaR <= limit on a scenario matrix.

    ``scenarios`` is (S, N) of asset returns. Portfolio loss in scenario s is
    -(scenarios[s] @ w). CVaR_alpha is the expected loss in the worst (1-alpha)
    tail. Returns the constraint list plus the auxiliary variables.
    """
    s = scenarios.shape[0]
    zeta = cp.Variable()             # value-at-risk level
    u = cp.Variable(s, nonneg=True)  # tail excess losses
    losses = -(scenarios @ w)
    cvar = zeta + cp.sum(u) / ((1 - alpha) * s)
    cons = [u >= losses - zeta, cvar <= limit]
    return cons, zeta, u


def make_scenarios(
    mu_annual: np.ndarray, cov_annual: np.ndarray, n_scen: int, seed: int
) -> np.ndarray:
    """Draw (n_scen, N) one-year asset returns ~ N(mu, Sigma)."""
    rng = np.random.default_rng(seed)
    return rng.multivariate_normal(mu_annual, cov_annual, size=n_scen)
