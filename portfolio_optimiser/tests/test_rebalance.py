"""Tests for the contribution-driven rebalancer."""

import numpy as np

from portfolio_optimiser.rebalancer import rebalance


def test_buys_sum_to_contribution():
    plan = rebalance(
        current={"A": 600, "B": 400},
        contribution=200,
        target_weights={"A": 0.5, "B": 0.5},
    )
    assert abs(plan.buys.sum() - 200) < 1e-6
    # B is underweight (40%) so it should receive the lion's share.
    assert plan.buys["B"] > plan.buys["A"]


def test_water_fill_prioritises_underweight():
    # A hugely underweight; small contribution all flows to A.
    plan = rebalance(
        current={"A": 100, "B": 900},
        contribution=100,
        target_weights={"A": 0.5, "B": 0.5},
    )
    assert plan.buys["A"] == 100
    assert plan.buys["B"] == 0


def test_overweight_raises_drift_flag():
    # A is 80% vs 50% target and cannot be fixed by buying B alone with tiny money.
    plan = rebalance(
        current={"A": 800, "B": 200},
        contribution=10,
        target_weights={"A": 0.5, "B": 0.5},
        drift_abs_pts=0.05,
    )
    assert any("A:" in f for f in plan.flags)


def test_no_flag_when_on_target():
    plan = rebalance(
        current={"A": 500, "B": 500},
        contribution=100,
        target_weights={"A": 0.5, "B": 0.5},
    )
    assert plan.flags == []
    assert np.isclose(plan.post_weights["A"], 0.5)


def test_pie_targets_in_percent():
    plan = rebalance(
        current={"A": 0, "B": 0},
        contribution=100,
        target_weights={"A": 0.3, "B": 0.7},
    )
    assert np.isclose(plan.pie_targets["A"], 30.0)
    assert np.isclose(plan.pie_targets["B"], 70.0)


def test_empty_portfolio_first_contribution():
    plan = rebalance(
        current={},
        contribution=1000,
        target_weights={"A": 0.6, "B": 0.4},
    )
    assert np.isclose(plan.buys["A"], 600)
    assert np.isclose(plan.buys["B"], 400)
