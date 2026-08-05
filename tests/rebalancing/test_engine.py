"""Tests for the rebalancing backtest engine.

These are the checks that would catch an engine that quietly favours one
policy over another. They use synthetic returns so the expected answer is
known analytically rather than asserted against a previous run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.rebalancing import engine, metrics
from src.rebalancing.config import ASSETS, COST_BASE, COST_ZERO, TargetWeights
from src.rebalancing.policies import (
    POLICY_BY_NAME,
    _rolling_max,
    drawdown_trigger_mask,
    period_start_mask,
)

TARGET = np.array([0.6, 0.2, 0.2])


@pytest.fixture
def synthetic_returns() -> pd.DataFrame:
    """Ten years of seeded daily returns with realistic drift and vol."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2010-01-01", periods=2520)
    data = rng.normal(
        loc=[0.0003, 0.0001, 0.0002],
        scale=[0.011, 0.004, 0.010],
        size=(len(dates), 3),
    )
    return pd.DataFrame(data, index=dates, columns=list(ASSETS))


# ---------------------------------------------------------------------------
# Engine identities
# ---------------------------------------------------------------------------


def test_daily_rebalancing_equals_analytic_constant_mix(synthetic_returns):
    """A zero-cost daily rebalancer *is* a constant-mix portfolio."""
    result = engine.run(
        synthetic_returns, POLICY_BY_NAME["Daily (constant mix)"], TARGET, COST_ZERO
    )
    analytic = engine.constant_mix(synthetic_returns, TARGET)
    assert result.value[-1] / COST_ZERO.initial_value == pytest.approx(
        float((1 + analytic).prod()), rel=1e-12
    )


def test_drift_equals_buy_and_hold(synthetic_returns):
    """The 'never' policy must be exactly a weighted buy-and-hold."""
    result = engine.run(
        synthetic_returns, POLICY_BY_NAME["Never (drift)"], TARGET, COST_ZERO
    )
    expected = float((1 + synthetic_returns).cumprod().to_numpy()[-1] @ TARGET)
    assert result.value[-1] / COST_ZERO.initial_value == pytest.approx(
        expected, rel=1e-12
    )


@pytest.mark.parametrize(
    "policy_name",
    [
        "Monthly",
        "Annual",
        "5/25 rule (daily check)",
        "Drawdown trigger -20%",
        "Never (drift)",
    ],
)
def test_batch_path_matches_single_path(synthetic_returns, policy_name):
    """The vectorised bootstrap engine must reproduce the single path exactly.

    If these ever diverge, every bootstrap conclusion is measuring a different
    strategy from the one in the headline table.
    """
    policy = POLICY_BY_NAME[policy_name]
    single = engine.run(synthetic_returns, policy, TARGET, COST_BASE)
    index = np.tile(np.arange(len(synthetic_returns)), (2, 1))
    batch = engine.run_batch(
        synthetic_returns.to_numpy(), index, policy, TARGET, COST_BASE,
        synthetic_returns.index,
    )
    assert batch[0] == pytest.approx(single.value[-1], rel=1e-12)
    assert batch[1] == pytest.approx(single.value[-1], rel=1e-12)


def test_costs_only_ever_reduce_wealth(synthetic_returns):
    for policy in ("Monthly", "Quarterly", "5/25 rule (daily check)"):
        net = engine.run(synthetic_returns, POLICY_BY_NAME[policy], TARGET, COST_BASE)
        gross = engine.run(synthetic_returns, POLICY_BY_NAME[policy], TARGET, COST_ZERO)
        assert net.value[-1] < gross.value[-1]


def test_contributions_are_not_counted_as_return(synthetic_returns):
    """Paying money in must not show up as performance."""
    without = engine.run(
        synthetic_returns, POLICY_BY_NAME["Monthly"], TARGET, COST_ZERO
    )
    with_contrib = engine.run(
        synthetic_returns,
        POLICY_BY_NAME["Monthly"],
        TARGET,
        COST_ZERO,
        monthly_contribution=1_000.0,
    )
    assert with_contrib.value[-1] > without.value[-1]  # more money in the pot
    assert metrics.cagr(with_contrib.returns) == pytest.approx(
        metrics.cagr(without.returns), abs=1e-9
    )  # but the same return


def test_no_drift_means_no_trade_and_no_cost():
    """Rebalancing a portfolio that is already on target must be free."""
    dates = pd.bdate_range("2020-01-01", periods=300)
    flat = pd.DataFrame(0.0, index=dates, columns=list(ASSETS))
    result = engine.run(
        flat, POLICY_BY_NAME["Daily (constant mix)"], TARGET, COST_BASE
    )
    assert result.cost.sum() == 0.0
    assert result.value[-1] == pytest.approx(COST_BASE.initial_value)


def test_ruin_guard_stops_at_zero(synthetic_returns):
    """Flat commissions bigger than the pot must ruin it, not go negative.

    This is the £10k-pot / daily-rebalancing case from the report: real
    behaviour, and previously it drove portfolio value negative and made every
    downstream metric meaningless.
    """
    from dataclasses import replace

    brutal = replace(COST_BASE, commission_flat=200.0, initial_value=1_000.0)
    result = engine.run(
        synthetic_returns, POLICY_BY_NAME["Daily (constant mix)"], TARGET, brutal
    )
    assert result.value.min() >= 0.0
    assert result.value[-1] == 0.0
    assert metrics.cagr(result.returns) == -1.0
    assert np.isfinite(result.weights).all()


# ---------------------------------------------------------------------------
# Decomposition
# ---------------------------------------------------------------------------


def test_decomposition_sums_to_the_realised_difference(synthetic_returns):
    """Allocation + rebalancing + cost must equal the actual CAGR gap.

    This is the guard against the decomposition silently attributing an
    effect to 'rebalancing' that is really cost or allocation.
    """
    bench = POLICY_BY_NAME["Monthly"]
    bench_net = engine.run(synthetic_returns, bench, TARGET, COST_BASE)
    bench_gross = engine.run(synthetic_returns, bench, TARGET, COST_ZERO)
    for name in ("Never (drift)", "Annual", "Drawdown trigger -15%"):
        policy = POLICY_BY_NAME[name]
        net = engine.run(synthetic_returns, policy, TARGET, COST_BASE)
        gross = engine.run(synthetic_returns, policy, TARGET, COST_ZERO)
        parts = metrics.decompose(
            net,
            bench_net,
            synthetic_returns,
            result_gross=gross,
            benchmark_gross=bench_gross,
        )
        realised = (metrics.cagr(net.returns) - metrics.cagr(bench_net.returns)) * 1e4
        assert sum(parts) == pytest.approx(realised, abs=1e-6)


# ---------------------------------------------------------------------------
# Policy primitives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("window", [1, 5, 63, 252])
def test_rolling_max_matches_pandas(window):
    rng = np.random.default_rng(3)
    values = rng.normal(size=(4, 500)).cumsum(axis=1)
    expected = pd.DataFrame(values.T).rolling(window, min_periods=1).max().to_numpy().T
    assert np.allclose(_rolling_max(values, window), expected)


def test_schedule_counts():
    dates = pd.bdate_range("2000-01-01", "2019-12-31")
    assert period_start_mask(dates, "never").sum() == 0
    assert period_start_mask(dates, "daily").sum() == len(dates)
    assert period_start_mask(dates, "annual").sum() == 19  # day 0 never trades
    assert period_start_mask(dates, "quarterly").sum() == 79


def test_drawdown_trigger_fires_once_per_episode():
    """A long bear market should trigger once, not every day."""
    level = np.concatenate(
        [np.linspace(1, 2, 400), np.linspace(2, 1.2, 300), np.linspace(1.2, 3, 600)]
    )
    fires = drawdown_trigger_mask(level, threshold=0.20, lookback=252, lockout=252)
    assert fires.sum() == 1
    running_max = np.maximum.accumulate(level)
    fired_at = int(np.argmax(fires))
    assert 1 - level[fired_at] / running_max[fired_at] >= 0.20


def test_band_breach_uses_the_tighter_of_absolute_and_relative():
    """5/25: 5pp binds on big sleeves, 25% relative binds on small ones."""
    policy = POLICY_BY_NAME["5/25 rule (daily check)"]
    target = np.array([0.6, 0.2, 0.2])
    # Gold at 0.24 is +4pp (under the 5pp band) but +20% relative (under 25%).
    assert not policy.breached(np.array([0.56, 0.20, 0.24]), target)
    # Gold at 0.26 is +6pp and +30% relative — both trip.
    assert policy.breached(np.array([0.54, 0.20, 0.26]), target)
    # Equity at 0.655 is +5.5pp but only +9% relative — absolute band trips.
    assert policy.breached(np.array([0.655, 0.175, 0.17]), target)


def test_target_weights_must_sum_to_one():
    with pytest.raises(ValueError, match="sum to"):
        TargetWeights("bad", {"equity": 0.6, "bond": 0.5})
    with pytest.raises(ValueError, match="unknown assets"):
        TargetWeights("bad", {"equity": 0.5, "crypto": 0.5})
