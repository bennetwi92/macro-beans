"""CMA sensitivity: how much does each weight hinge on each assumption?

For every building block in the CMA we shift it up and down by ``sensitivity_shift``
(default +/- 1 ppt), re-derive expected returns, re-optimise, and record how far
the weights move. The output tells the investor which single assumption the answer
is most exposed to -- the honest counterpart to a single point estimate.
"""

from __future__ import annotations

import copy
from typing import Callable

import pandas as pd

from . import cma as cma_mod
from .config import CMA, PortfolioConstraints, Settings, Universe
from .optimize import OptResult


def _mu_from_blocks(cma: CMA, keys: list[str], ters: dict[str, float]) -> pd.Series:
    mu = cma_mod.arithmetic_returns(cma, keys)
    return cma_mod.net_of_fees(mu, ters)


def sensitivity_table(
    optimise_fn: Callable[..., OptResult],
    constraints: PortfolioConstraints,
    universe: Universe,
    base_cma: CMA,
    cov: pd.DataFrame,
    settings: Settings,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (summary, full_weights).

    summary: one row per block -> largest absolute weight move (+/-), the holding
             that moves most, and the change in portfolio geometric return.
    full_weights: block x direction -> full weight vector (for the appendix).
    """
    keys = constraints.universe
    ters = {k: universe.instruments[k].ter for k in keys}
    shift = settings.sensitivity_shift

    base_mu = _mu_from_blocks(base_cma, keys, ters)
    base = optimise_fn(constraints, universe, base_mu, cov, settings)

    summary_rows = []
    full_rows: dict[str, pd.Series] = {}
    for block in base_cma.blocks:
        moves = {}
        for direction, delta in (("up", shift), ("down", -shift)):
            cma2 = copy.deepcopy(base_cma)
            cma2.blocks[block] = cma2.blocks[block] + delta
            mu2 = _mu_from_blocks(cma2, keys, ters)
            try:
                res = optimise_fn(constraints, universe, mu2, cov, settings)
            except Exception:
                continue
            moves[direction] = res
            full_rows[f"{block}:{direction}"] = res.weights

        if "up" not in moves and "down" not in moves:
            continue
        deltas = []
        for d in ("up", "down"):
            if d in moves:
                deltas.append((moves[d].weights - base.weights).abs())
        max_delta = pd.concat(deltas, axis=1).max(axis=1) if deltas else base.weights * 0
        worst_holding = max_delta.idxmax()
        geo_up = moves["up"].exp_geometric if "up" in moves else float("nan")
        geo_dn = moves["down"].exp_geometric if "down" in moves else float("nan")
        summary_rows.append({
            "block": block,
            "shift": shift,
            "max_weight_move": float(max_delta.max()),
            "most_sensitive_holding": worst_holding,
            "geo_up": geo_up,
            "geo_down": geo_dn,
            "geo_spread": float(abs(geo_up - geo_dn)),
        })

    summary = (
        pd.DataFrame(summary_rows)
        .sort_values("max_weight_move", ascending=False)
        .reset_index(drop=True)
    )
    full = pd.DataFrame(full_rows).T
    return summary, full
