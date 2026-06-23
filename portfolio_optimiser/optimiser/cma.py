"""Expected returns from capital-market assumptions, and arith<->geo conversion.

The CMA config gives building blocks (cash, ERP, factor premia) and a simple
formula per instrument. We evaluate the formula against the blocks to get an
ARITHMETIC expected return, then convert to GEOMETRIC using the covariance-implied
variance:

    g_i ~= mu_i - 0.5 * sigma_i^2        (single asset)
    g(w) ~= w'mu - 0.5 * w'Sigma w       (portfolio; the objective for the SIPP)

The portfolio form is what the optimiser maximises -- it already rewards
diversification and the variance drag, which is why the managed-futures sleeve
earns its place via the rebalancing bonus rather than via a high mu.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CMA


def _eval_formula(formula: str, blocks: dict[str, float]) -> float:
    """Evaluate a block formula like 'equity_dev + value_premium' safely.

    Only names present in ``blocks`` and basic arithmetic are allowed.
    """
    allowed = dict(blocks)
    code = compile(formula, "<cma-formula>", "eval")
    for name in code.co_names:
        if name not in allowed:
            raise ValueError(f"Unknown CMA block '{name}' in formula: {formula!r}")
    return float(eval(code, {"__builtins__": {}}, allowed))


def arithmetic_returns(cma: CMA, keys: list[str]) -> pd.Series:
    """Annual ARITHMETIC nominal GBP expected return per instrument key."""
    out: dict[str, float] = {}
    for key in keys:
        if key in cma.explicit:
            out[key] = cma.explicit[key]
        elif key in cma.formulas:
            out[key] = _eval_formula(cma.formulas[key], cma.blocks)
        else:
            raise KeyError(f"No CMA (mu or formula) defined for instrument '{key}'")
    return pd.Series(out, name="mu_arith")


def net_of_fees(mu: pd.Series, ters: dict[str, float]) -> pd.Series:
    """Subtract the ongoing charge (TER) from each expected return."""
    return mu - pd.Series({k: ters[k] for k in mu.index})


def to_geometric(mu_arith: pd.Series, cov: pd.DataFrame) -> pd.Series:
    """Per-asset geometric return g_i = mu_i - 0.5 sigma_i^2 (annual cov)."""
    var = pd.Series(np.diag(cov.loc[mu_arith.index, mu_arith.index]), index=mu_arith.index)
    return (mu_arith - 0.5 * var).rename("mu_geo")


def portfolio_geometric(weights: np.ndarray, mu_arith: np.ndarray, cov: np.ndarray) -> float:
    """g(w) = w'mu - 0.5 w'Sigma w  (annualised geometric growth approximation)."""
    return float(weights @ mu_arith - 0.5 * weights @ cov @ weights)
