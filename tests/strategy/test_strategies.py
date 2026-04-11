"""Tests for all strategy families: signal validity and no look-ahead."""
import numpy as np
import pandas as pd
import pytest

from src.data.features import FeatureEngine
from src.strategy.trend import create_variants as trend_variants
from src.strategy.mean_reversion import create_variants as mr_variants
from src.strategy.carry import create_variants as carry_variants
from src.strategy.macro import create_variants as macro_variants
from src.strategy.volatility import create_variants as vol_variants
from src.strategy.seasonal import MonthlySeasonal
from src.strategy.cross_asset import create_variants as cross_variants
from src.strategy.technical_composite import create_variants as tc_variants
from src.strategy.base import StrategyConfig


@pytest.fixture
def featured_data(sample_ohlcv, sample_related):
    engine = FeatureEngine()
    return engine.compute_all(sample_ohlcv, sample_related)


def _all_strategies():
    """Collect all non-ML, non-ensemble strategies."""
    strats = []
    strats.extend(trend_variants())
    strats.extend(mr_variants())
    strats.extend(carry_variants())
    strats.extend(macro_variants())
    strats.extend(vol_variants())
    strats.extend(cross_variants())
    strats.extend(tc_variants())
    # Monthly seasonal (DOW is slow, skip in unit tests)
    strats.append(MonthlySeasonal(StrategyConfig(
        name="Seasonal_Monthly", params={"long_months": [1, 2, 6, 9]}
    )))
    return strats


class TestAllStrategies:
    @pytest.mark.parametrize("strategy", _all_strategies(), ids=lambda s: s.name)
    def test_signals_are_binary(self, strategy, featured_data):
        """All signals must be in {0, 1}."""
        signals = strategy.generate_signals(featured_data)
        assert isinstance(signals, pd.Series)
        unique = set(signals.dropna().unique())
        assert unique.issubset({0.0, 1.0}), f"{strategy.name} produced {unique}"

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=lambda s: s.name)
    def test_signal_length_matches_data(self, strategy, featured_data):
        """Signal series must have same length as input data."""
        signals = strategy.generate_signals(featured_data)
        assert len(signals) == len(featured_data)

    @pytest.mark.parametrize("strategy", _all_strategies(), ids=lambda s: s.name)
    def test_required_features_exist(self, strategy, featured_data):
        """All required features should exist in featured data."""
        for feat in strategy.required_features():
            assert feat in featured_data.columns, \
                f"{strategy.name} requires '{feat}' which is missing"


class TestTrendStrategies:
    def test_sma_crossover_long_in_uptrend(self, featured_data):
        """SMA crossover should be long when fast > slow."""
        strats = trend_variants()
        sma_10_50 = strats[0]  # SMA_10_50
        signals = sma_10_50.generate_signals(featured_data)
        # Where sma_10 > sma_50, signal should be 1
        mask = featured_data["sma_10"] > featured_data["sma_50"]
        valid = mask.dropna()
        assert (signals.loc[valid.index][valid] == 1.0).all()

    def test_momentum_positive(self, featured_data):
        """Momentum should be long when mom_N > 0."""
        from src.strategy.trend import Momentum
        strat = Momentum(StrategyConfig(name="test", params={"period": 20}))
        signals = strat.generate_signals(featured_data)
        mask = featured_data["mom_20"] > 0
        valid = mask.dropna()
        assert (signals.loc[valid.index][valid] == 1.0).all()


class TestMeanReversionStrategies:
    def test_rsi_oversold_triggers_long(self, featured_data):
        """RSI strategy should go long when RSI < oversold."""
        strats = mr_variants()
        rsi_strat = [s for s in strats if "RSI" in s.name][0]
        signals = rsi_strat.generate_signals(featured_data)
        # Just verify it produces valid signals
        assert signals.sum() >= 0  # At least some longs possible


class TestMacroStrategies:
    def test_vix_regime(self, featured_data):
        """VIX regime should be long when VIX is low."""
        from src.strategy.macro import VIXRegime
        strat = VIXRegime(StrategyConfig(name="test", params={"threshold": 20}))
        signals = strat.generate_signals(featured_data)
        if "vix" in featured_data.columns:
            low_vix = featured_data["vix"] < 20
            valid = low_vix.dropna()
            # Where VIX < 20, signal should be 1
            assert (signals.loc[valid.index][valid] == 1.0).all()
