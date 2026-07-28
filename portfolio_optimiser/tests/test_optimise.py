"""Smoke + property tests for the optimisers and config, using synthetic inputs.

These do not hit the network; they build small synthetic mu/cov so CI is fast and
deterministic.
"""

import numpy as np
import pandas as pd
import pytest

from portfolio_optimiser.optimiser.config import load_all
from portfolio_optimiser.optimiser.optimize import optimise_isa, optimise_sipp


@pytest.fixture(scope="module")
def cfg():
    return load_all()


def _synthetic_inputs(keys, seed=0):
    rng = np.random.default_rng(seed)
    mu = pd.Series(0.04 + 0.04 * rng.random(len(keys)), index=keys)
    vols = 0.05 + 0.20 * rng.random(len(keys))
    corr = np.eye(len(keys))
    cov = pd.DataFrame(np.outer(vols, vols) * (0.2 + 0.8 * corr), index=keys, columns=keys)
    return mu, cov


def test_config_loads(cfg):
    assert cfg.isa.liquidity_floor_gbp == 10000
    assert cfg.isa.cvar_limit == 0.20
    # every universe key must have a CMA and a proxy
    for k in set(cfg.isa.universe) | set(cfg.sipp.universe):
        assert k in cfg.universe.instruments
        assert cfg.universe.instruments[k].proxy in cfg.universe.proxies


def test_sipp_contribution_mandate_loads(cfg):
    """The SIPP is a contribution stream to 2049, not a single-year lump."""
    c = cfg.sipp.contributions
    assert c["horizon_years"] == 23
    assert c["target_year"] == 2049
    assert c["opening_balance_gbp"] == 0
    assert c["monthly_gbp"] > 0
    # de-risking must start inside the horizon and finish by the target date
    assert 0 < c["derisk_start_years_before"] <= c["horizon_years"]
    assert 0.0 <= c["terminal_defensive_frac"] < 1.0
    # Interactive Investor execution limits must be present for the £ ladder
    e = cfg.sipp.execution
    assert e["min_instruction_gbp"] == 25
    assert e["max_instructions"] == 25


def test_sipp_weights_valid(cfg):
    mu, cov = _synthetic_inputs(cfg.sipp.universe)
    res = optimise_sipp(cfg.sipp, cfg.universe, mu, cov, cfg.settings)
    w = res.weights
    assert abs(w.sum() - 1) < 1e-6
    assert (w >= -1e-9).all()
    assert w.max() <= cfg.sipp.weight_max + 1e-6


def test_isa_respects_liquidity_floor(cfg):
    mu, cov = _synthetic_inputs(cfg.isa.universe)
    res = optimise_isa(cfg.isa, cfg.universe, mu, cov, cfg.settings)
    floor = cfg.isa.liquidity_floor_gbp / cfg.isa.value_gbp
    ballast_keys = [k for k in cfg.isa.universe
                    if cfg.universe.sleeve_of(k) == cfg.isa.ballast_sleeve]
    assert res.weights[ballast_keys].sum() >= floor - 1e-3


def test_isa_weights_valid(cfg):
    mu, cov = _synthetic_inputs(cfg.isa.universe, seed=3)
    res = optimise_isa(cfg.isa, cfg.universe, mu, cov, cfg.settings)
    assert abs(res.weights.sum() - 1) < 1e-6
    assert res.weights.max() <= cfg.isa.weight_max + 1e-6
