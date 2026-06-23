"""Estimation-error-robust cross-checks: resampling, Black-Litterman, HRP.

Single-point mean-variance is fragile. We compare three robust angles:

  * Michaud resampling -- perturb the inputs by their estimation noise, re-optimise
    many times, average the weights. Smooths out corner solutions.
  * Black-Litterman -- fold the CMA views into a market-implied equilibrium prior,
    then optimise the posterior. Shows what the market-neutral starting point
    pulls the answer toward.
  * Hierarchical Risk Parity -- a returns-free, risk-only allocation. A sanity
    check that does not trust the expected returns at all.

The report tabulates where the methods agree and disagree.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

from .config import PortfolioConstraints, Settings, Universe
from .optimize import OptResult


def resampled_weights(
    optimise_fn: Callable[..., OptResult],
    constraints: PortfolioConstraints,
    universe: Universe,
    mu_arith: pd.Series,
    cov: pd.DataFrame,
    settings: Settings,
    n_obs: int = 180,
) -> pd.Series:
    """Michaud resampled weights: average optimal weights over noisy redraws.

    Each draw simulates ``n_obs`` periods from N(mu, Sigma) (monthly scale),
    re-estimates mu_hat and cov_hat, and re-optimises. ``n_obs`` defaults to ~15y
    of monthly data.
    """
    keys = constraints.universe
    rng = np.random.default_rng(settings.random_seed)
    mu_m = mu_arith.loc[keys].values / settings.trading_periods
    cov_m = cov.loc[keys, keys].values / settings.trading_periods

    acc = np.zeros(len(keys))
    draws = settings.resample_draws
    ok = 0
    for _ in range(draws):
        sample = rng.multivariate_normal(mu_m, cov_m, size=n_obs)
        mu_hat = pd.Series(sample.mean(axis=0) * settings.trading_periods, index=keys)
        cov_hat = pd.DataFrame(
            np.cov(sample, rowvar=False) * settings.trading_periods,
            index=keys, columns=keys,
        )
        try:
            res = optimise_fn(constraints, universe, mu_hat, cov_hat, settings)
            acc += res.weights.loc[keys].values
            ok += 1
        except Exception:
            continue
    if ok == 0:
        raise RuntimeError("All resampling draws failed to optimise.")
    return pd.Series(acc / ok, index=keys, name="resampled")


def black_litterman(
    constraints: PortfolioConstraints,
    universe: Universe,
    mu_cma: pd.Series,
    cov: pd.DataFrame,
    settings: Settings,
    delta: float = 2.5,
    tau: float = 0.05,
    view_confidence: float = 0.5,
) -> tuple[pd.Series, pd.Series]:
    """Posterior expected returns blending a market prior with the CMA views.

    Market prior uses equal weights as a neutral cap proxy (no cap-weight data in
    the universe): Pi = delta * Sigma * w_mkt. Views are one absolute view per
    asset (P = I) equal to the CMA, with uncertainty Omega scaled by
    ``view_confidence`` and tau*diag(Sigma).

    Returns (posterior_mu, equilibrium_prior).
    """
    keys = constraints.universe
    sigma = cov.loc[keys, keys].values
    n = len(keys)
    w_mkt = np.ones(n) / n
    pi = delta * sigma @ w_mkt                       # equilibrium prior returns

    P = np.eye(n)
    q = mu_cma.loc[keys].values
    omega = np.diag(np.diag(P @ (tau * sigma) @ P.T)) / max(view_confidence, 1e-6)

    tau_sigma_inv = np.linalg.inv(tau * sigma)
    omega_inv = np.linalg.inv(omega)
    post_cov = np.linalg.inv(tau_sigma_inv + P.T @ omega_inv @ P)
    post_mu = post_cov @ (tau_sigma_inv @ pi + P.T @ omega_inv @ q)

    return (
        pd.Series(post_mu, index=keys, name="bl_posterior"),
        pd.Series(pi, index=keys, name="bl_equilibrium"),
    )


def hrp_weights(cov: pd.DataFrame, keys: list[str]) -> pd.Series:
    """Hierarchical Risk Parity (Lopez de Prado) on the covariance sub-matrix."""
    cov_sub = cov.loc[keys, keys]
    corr = _cov_to_corr(cov_sub.values)
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0, None))
    np.fill_diagonal(dist, 0.0)
    link = linkage(squareform(dist, checks=False), method="single")
    order = _quasi_diag(link, len(keys))
    ordered_keys = [keys[i] for i in order]
    w = _recursive_bisection(cov_sub.values, order)
    return pd.Series(w, index=[keys[i] for i in order], name="hrp").reindex(keys)


def _cov_to_corr(cov: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    return np.clip(corr, -1, 1)


def _quasi_diag(link: np.ndarray, n: int) -> list[int]:
    link = link.astype(int)
    items = [link[-1, 0], link[-1, 1]]
    while max(items) >= n:
        new = []
        for it in items:
            if it < n:
                new.append(it)
            else:
                row = link[it - n]
                new.extend([row[0], row[1]])
        items = new
    return items


def _recursive_bisection(cov: np.ndarray, order: list[int]) -> np.ndarray:
    w = pd.Series(1.0, index=order)
    clusters = [order]
    while clusters:
        clusters = [
            c[half] for c in clusters
            for half in (slice(0, len(c) // 2), slice(len(c) // 2, len(c)))
            if len(c) > 1
        ]
        for i in range(0, len(clusters), 2):
            left, right = clusters[i], clusters[i + 1]
            var_l = _cluster_var(cov, left)
            var_r = _cluster_var(cov, right)
            alpha = 1 - var_l / (var_l + var_r)
            w[left] *= alpha
            w[right] *= 1 - alpha
    return w.reindex(order).values


def _cluster_var(cov: np.ndarray, items: list[int]) -> float:
    sub = cov[np.ix_(items, items)]
    ivp = 1.0 / np.diag(sub)
    ivp /= ivp.sum()
    return float(ivp @ sub @ ivp)
