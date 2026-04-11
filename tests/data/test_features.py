import numpy as np
import pandas as pd
import pytest

from src.data.features import FeatureEngine


@pytest.fixture
def engine():
    return FeatureEngine()


class TestFeatureEngine:
    def test_compute_all_adds_columns(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert len(result.columns) > len(sample_ohlcv.columns)
        assert len(result) == len(sample_ohlcv)

    def test_moving_averages_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        for w in [10, 20, 50, 100, 200]:
            assert f"sma_{w}" in result.columns

    def test_ema_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        for s in [12, 20, 26, 50]:
            assert f"ema_{s}" in result.columns

    def test_rsi_in_range(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        for p in [7, 14, 21]:
            col = f"rsi_{p}"
            assert col in result.columns
            valid = result[col].dropna()
            assert (valid >= 0).all() and (valid <= 100).all()

    def test_bollinger_bands_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "bb_mid" in result.columns
        assert "bb_upper" in result.columns
        assert "bb_lower" in result.columns
        assert "bb_pct" in result.columns

    def test_macd_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_donchian_channels(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "donchian_high_20" in result.columns
        assert "donchian_low_20" in result.columns

    def test_atr_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "atr" in result.columns
        valid = result["atr"].dropna()
        assert (valid > 0).all()

    def test_zscore_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "zscore_20" in result.columns
        assert "zscore_50" in result.columns

    def test_volatility_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        for w in [10, 20, 60]:
            assert f"vol_{w}" in result.columns

    def test_momentum_present(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        for p in [5, 10, 20, 60]:
            assert f"mom_{p}" in result.columns

    def test_seasonal_features(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "month" in result.columns
        assert "day_of_week" in result.columns
        assert result["month"].between(1, 12).all()
        assert result["day_of_week"].between(0, 4).all()

    def test_cross_asset_features(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        assert "vix" in result.columns
        assert "dxy_mom_20" in result.columns
        assert "xle_vs_spx_20" in result.columns
        assert "oil_gold_zscore" in result.columns
        assert "spx_above_200" in result.columns
        assert "roll_yield_proxy" in result.columns

    def test_no_unexpected_nans_after_warmup(self, engine, sample_ohlcv, sample_related):
        result = engine.compute_all(sample_ohlcv, sample_related)
        # After 200-day warmup, most features should not be NaN
        after_warmup = result.iloc[200:]
        core_cols = ["sma_200", "rsi_14", "bb_mid", "macd", "atr", "zscore_50", "vol_60"]
        for col in core_cols:
            assert col in result.columns, f"{col} missing"
            nans = after_warmup[col].isna().sum()
            assert nans == 0, f"{col} has {nans} NaNs after warmup"
