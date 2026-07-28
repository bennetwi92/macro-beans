"""Property tests for the contribution-stream lifecycle machinery.

Offline and deterministic: every test builds its own synthetic return panel, so
nothing here touches the network or the cached history.
"""

import numpy as np
import pandas as pd
import pytest

from portfolio_optimiser.optimiser import lifecycle as lc
from portfolio_optimiser.optimiser import robust


KEYS = ["A", "B", "C"]


@pytest.fixture
def panel():
    """60 months of synthetic, mildly correlated returns."""
    rng = np.random.default_rng(11)
    common = rng.normal(0.005, 0.03, size=60)
    data = {
        k: common * beta + rng.normal(0.0, 0.02, size=60)
        for k, beta in zip(KEYS, (1.0, 0.8, 0.3))
    }
    idx = pd.date_range("2015-01-31", periods=60, freq="ME")
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def crash_panel(panel):
    """The same panel with a clustered six-month drawdown bolted in.

    Real return histories are not iid: losses arrive in runs. This fixture makes
    that explicit so the bootstrap can be tested against a Gaussian model fitted
    to identical moments.
    """
    out = panel.copy()
    out.iloc[30:36] = -0.10
    return out


@pytest.fixture
def equal_weights():
    return pd.Series(1.0 / len(KEYS), index=KEYS)


# ---------------------------------------------------------------------------
# Accumulation identities
# ---------------------------------------------------------------------------

def test_zero_returns_give_back_exactly_the_contributions(equal_weights):
    """The load-bearing accounting check: no growth, no fee -> pot == paid in."""
    n_months = 36
    draws = np.zeros((5, n_months, len(KEYS)))
    contributions = np.full(n_months, 100.0)
    wealth = lc.accumulate(
        draws, lc.constant_weight_path(equal_weights, n_months), contributions
    )
    assert np.allclose(wealth[:, -1], contributions.sum())


def test_opening_balance_and_flat_fee_are_applied(equal_weights):
    n_months = 12
    draws = np.zeros((3, n_months, len(KEYS)))
    contributions = np.full(n_months, 100.0)
    wealth = lc.accumulate(
        draws, lc.constant_weight_path(equal_weights, n_months), contributions,
        opening_balance=500.0, monthly_fee=10.0,
    )
    expected = 500.0 + contributions.sum() - 10.0 * n_months
    assert np.allclose(wealth[:, -1], expected)


def test_constant_growth_compounds_as_an_annuity(equal_weights):
    """Closed-form check against the future value of an ordinary annuity."""
    n_months, rate, contribution = 24, 0.01, 100.0
    draws = np.full((2, n_months, len(KEYS)), rate)
    contributions = np.full(n_months, contribution)
    wealth = lc.accumulate(
        draws, lc.constant_weight_path(equal_weights, n_months), contributions
    )
    # Contributions are invested at the START of the month -> annuity-due.
    expected = contribution * ((1 + rate) ** n_months - 1) / rate * (1 + rate)
    assert wealth[0, -1] == pytest.approx(expected, rel=1e-9)


def test_tiered_fee_switches_above_the_threshold(equal_weights):
    n_months = 12
    draws = np.zeros((1, n_months, len(KEYS)))
    contributions = np.full(n_months, 1_000.0)
    wealth = lc.accumulate(
        draws, lc.constant_weight_path(equal_weights, n_months), contributions,
        monthly_fee=10.0, monthly_fee_above=100.0, fee_threshold_gbp=5_000.0,
    )
    # Months 1-5 sit under the threshold (£10), months 6-12 above it (£100).
    expected = 12_000.0 - (5 * 10.0 + 7 * 100.0)
    assert wealth[0, -1] == pytest.approx(expected)


def test_recentre_matches_the_target_mean_without_touching_higher_moments(panel):
    target = pd.Series({"A": 0.09, "B": 0.07, "C": 0.04})
    shifted = lc.recentre(panel, target)
    assert np.allclose(shifted.mean().values * 12, target.loc[list(panel.columns)].values)
    # variance, skew and correlation are untouched by a location shift
    assert np.allclose(shifted.std().values, panel.std().values)
    assert np.allclose(shifted.corr().values, panel.corr().values)


def test_recentre_rejects_a_missing_expected_return(panel):
    with pytest.raises(ValueError, match="No expected return"):
        lc.recentre(panel, pd.Series({"A": 0.09}))


def test_contribution_schedule_escalates_annually():
    sched = lc.contribution_schedule(100.0, horizon_years=3, escalation_annual=0.10)
    assert len(sched) == 36
    assert sched[0] == pytest.approx(100.0)
    assert sched[11] == pytest.approx(100.0)      # still year 1
    assert sched[12] == pytest.approx(110.0)      # year 2
    assert sched[-1] == pytest.approx(121.0)      # year 3


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def test_bootstrap_shape_and_membership(panel):
    draws = lc.bootstrap_paths(panel, n_paths=20, n_months=48, seed=1, block_mean=6)
    assert draws.shape == (20, 48, len(KEYS))
    # every resampled month must be a real historical month, vector intact
    observed = {tuple(np.round(r, 12)) for r in panel.values}
    sampled = {tuple(np.round(r, 12)) for r in draws.reshape(-1, len(KEYS))}
    assert sampled <= observed


def test_bootstrap_preserves_cross_sectional_correlation(panel):
    draws = lc.bootstrap_paths(panel, n_paths=400, n_months=60, seed=2, block_mean=12)
    flat = draws.reshape(-1, len(KEYS))
    resampled_corr = np.corrcoef(flat, rowvar=False)
    observed_corr = panel.corr().values
    assert np.allclose(resampled_corr, observed_corr, atol=0.05)


def test_bootstrap_is_deterministic_for_a_seed(panel):
    a = lc.bootstrap_paths(panel, 10, 24, seed=7)
    b = lc.bootstrap_paths(panel, 10, 24, seed=7)
    assert np.array_equal(a, b)


def test_bootstrap_rejects_a_short_panel(panel):
    with pytest.raises(ValueError, match="at least 24"):
        lc.bootstrap_paths(panel.head(10), 5, 12, seed=0)


def test_bootstrap_preserves_crash_clustering_that_the_normal_model_averages_away(
    crash_panel, equal_weights
):
    """The whole point of the bootstrap.

    A normal model calibrated on the same panel sees only the mean and
    covariance, so it spreads the crash's variance evenly across independent
    months. The block bootstrap keeps the losing months adjacent, so a
    12-month stretch can be far worse than anything the Gaussian produces.
    """
    cov = pd.DataFrame(
        np.cov(crash_panel.values, rowvar=False) * 12, index=KEYS, columns=KEYS
    )
    mu = pd.Series(crash_panel.mean().values * 12, index=KEYS)

    boot = lc.bootstrap_paths(crash_panel, 3000, 120, seed=3, block_mean=12) @ equal_weights.values
    norm = lc.normal_paths(mu, cov, KEYS, 3000, 120, seed=3) @ equal_weights.values

    def worst_year(x):
        rolled = np.lib.stride_tricks.sliding_window_view(x, 12, axis=1)
        return np.percentile(np.prod(1 + rolled, axis=-1).min(axis=1) - 1, 1)

    assert worst_year(boot) < worst_year(norm)


def test_shorter_blocks_destroy_the_clustering(crash_panel, equal_weights):
    """Sanity check on the mechanism: block length is what carries the tail."""
    def worst_year(x):
        rolled = np.lib.stride_tricks.sliding_window_view(x, 12, axis=1)
        return np.percentile(np.prod(1 + rolled, axis=-1).min(axis=1) - 1, 1)

    long_blocks = lc.bootstrap_paths(crash_panel, 3000, 120, seed=4, block_mean=12)
    short_blocks = lc.bootstrap_paths(crash_panel, 3000, 120, seed=4, block_mean=1)
    assert worst_year(long_blocks @ equal_weights.values) < worst_year(
        short_blocks @ equal_weights.values
    )


# ---------------------------------------------------------------------------
# Glidepath
# ---------------------------------------------------------------------------

def test_glidepath_weights_are_valid_and_reach_the_target():
    growth = pd.Series({"A": 0.6, "B": 0.4})
    defensive = pd.Series({"C": 1.0})
    n_months = 120
    path = lc.glidepath_weight_path(
        growth, defensive, n_months,
        derisk_start_month=60, derisk_months=36, terminal_defensive_frac=0.30,
    )
    assert path.shape == (n_months, 3)
    assert np.allclose(path.sum(axis=1), 1.0)
    assert (path >= -1e-12).all()

    keys = sorted(set(growth.index) | set(defensive.index))
    c = keys.index("C")
    assert path[0, c] == pytest.approx(0.0)          # flat while contributions dominate
    assert path[59, c] == pytest.approx(0.0)
    assert path[96, c] == pytest.approx(0.30)        # ramp complete at 60 + 36
    assert path[-1, c] == pytest.approx(0.30)        # and holds


def test_glidepath_ramp_is_monotonic():
    growth = pd.Series({"A": 1.0})
    defensive = pd.Series({"C": 1.0})
    path = lc.glidepath_weight_path(growth, defensive, 60, 12, 24, 0.4)
    defensive_share = path[:, sorted(["A", "C"]).index("C")]
    assert np.all(np.diff(defensive_share) >= -1e-12)


def test_glidepath_lowers_dispersion_versus_static(panel):
    """De-risking near the end should narrow the outcome range."""
    growth = pd.Series({"A": 0.5, "B": 0.5})
    defensive = pd.Series({"C": 1.0})
    contributions = lc.contribution_schedule(100.0, horizon_years=10)
    cmp_ = lc.evaluate_glidepath(
        growth, defensive, panel, contributions, n_paths=600, seed=5,
        derisk_start_month=72, derisk_months=48, terminal_defensive_frac=0.35,
    )
    static_spread = cmp_.static.p95_gbp - cmp_.static.p5_gbp
    glide_spread = cmp_.glidepath.p95_gbp - cmp_.glidepath.p5_gbp
    assert glide_spread < static_spread


# ---------------------------------------------------------------------------
# Sequence risk
# ---------------------------------------------------------------------------

def test_late_crashes_hurt_more_than_early_ones(panel, equal_weights):
    """The inverted sequence-risk result that justifies the flat-then-glide shape."""
    contributions = lc.contribution_schedule(100.0, horizon_years=20)
    table = lc.sequence_risk_decomposition(
        equal_weights, panel, contributions, n_paths=800, seed=9,
        shock=-0.40, shock_years=(1, 10, 20),
    )
    damage = table.set_index("shock_year")["vs_baseline_pct"]
    assert damage[1] > damage[10] > damage[20]     # less negative = less damage
    assert damage[20] < 0


# ---------------------------------------------------------------------------
# ERC and ensembling
# ---------------------------------------------------------------------------

def test_erc_equalises_risk_contributions(panel):
    cov = pd.DataFrame(np.cov(panel.values, rowvar=False) * 12, index=KEYS, columns=KEYS)
    w = robust.erc_weights(cov, KEYS)
    assert abs(w.sum() - 1) < 1e-8
    assert (w > 0).all()
    rc = robust.risk_contributions(w, cov)
    assert rc.max() - rc.min() < 0.01


def test_erc_gives_the_lowest_vol_asset_the_largest_weight(panel):
    cov = pd.DataFrame(np.cov(panel.values, rowvar=False) * 12, index=KEYS, columns=KEYS)
    w = robust.erc_weights(cov, KEYS)
    vols = pd.Series(np.sqrt(np.diag(cov.values)), index=KEYS)
    assert w.idxmax() == vols.idxmin()


def test_ensemble_lies_in_the_convex_hull_of_its_inputs():
    methods = {
        "a": pd.Series({"A": 0.7, "B": 0.3, "C": 0.0}),
        "b": pd.Series({"A": 0.1, "B": 0.4, "C": 0.5}),
        "c": pd.Series({"A": 0.4, "B": 0.2, "C": 0.4}),
    }
    ens = robust.ensemble_weights(methods)
    assert abs(ens.sum() - 1) < 1e-12
    frame = pd.DataFrame(methods)
    assert (ens >= frame.min(axis=1) - 1e-12).all()
    assert (ens <= frame.max(axis=1) + 1e-12).all()


def test_ensemble_honours_explicit_blend_weights():
    methods = {
        "a": pd.Series({"A": 1.0, "B": 0.0}),
        "b": pd.Series({"A": 0.0, "B": 1.0}),
    }
    ens = robust.ensemble_weights(methods, {"a": 3.0, "b": 1.0})
    assert ens["A"] == pytest.approx(0.75)
    assert ens["B"] == pytest.approx(0.25)


def test_ensemble_rejects_a_missing_blend_weight():
    methods = {"a": pd.Series({"A": 1.0}), "b": pd.Series({"A": 1.0})}
    with pytest.raises(ValueError, match="No blend weight"):
        robust.ensemble_weights(methods, {"a": 1.0})


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def test_stream_summary_reports_a_sane_irr(equal_weights):
    n_months, rate = 120, 0.005
    draws = np.full((4, n_months, len(KEYS)), rate)
    contributions = np.full(n_months, 100.0)
    wealth = lc.accumulate(
        draws, lc.constant_weight_path(equal_weights, n_months), contributions
    )
    res = lc.summarise_stream(wealth, contributions)
    assert res.total_contributed == pytest.approx(12_000.0)
    assert res.prob_below_contributions == 0.0
    assert res.money_weighted_return == pytest.approx((1 + rate) ** 12 - 1, rel=1e-3)


def test_flat_fee_drag_falls_as_the_pot_grows():
    median_path = np.linspace(1_000, 500_000, 240)
    table = lc.flat_fee_drag(median_path, monthly_fee=5.99)
    assert len(table) == 20
    assert table["fee_drag_pct"].iloc[0] > table["fee_drag_pct"].iloc[-1]
    assert table["fee_drag_pct"].is_monotonic_decreasing
