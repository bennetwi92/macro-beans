import numpy as np
import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class VolBreakout(Strategy):
    """Long when price breaks above recent low + N * ATR."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        multiplier = self.config.params["atr_multiplier"]
        lookback = self.config.params.get("lookback", 20)

        recent_low = data["low"].rolling(lookback).min()
        breakout_level = recent_low + multiplier * data["atr"]
        return (data["close"] > breakout_level).astype(float)

    def required_features(self) -> list[str]:
        return ["atr"]


class LowVolRegime(Strategy):
    """Long during low-volatility regimes (vol below historical percentile)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        vol_window = self.config.params.get("vol_window", 20)
        percentile = self.config.params.get("percentile", 50)

        vol = data[f"vol_{vol_window}"]
        expanding_pct = vol.expanding(min_periods=60).apply(
            lambda x: np.percentile(x, percentile), raw=True
        )
        return (vol < expanding_pct).astype(float)

    def required_features(self) -> list[str]:
        return [f"vol_{self.config.params.get('vol_window', 20)}"]


class VolAdjustedMomentum(Strategy):
    """Momentum signal scaled by inverse volatility. Long if positive momentum and low vol."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        mom_w = self.config.params.get("momentum_window", 20)
        vol_w = self.config.params.get("vol_window", 20)

        mom = data[f"mom_{mom_w}"]
        vol = data[f"vol_{vol_w}"]

        # Inverse vol scaling: stronger signal when vol is low
        median_vol = vol.expanding(min_periods=60).median()
        vol_scale = median_vol / vol.clip(lower=0.01)

        score = mom * vol_scale
        return (score > 0).astype(float)

    def required_features(self) -> list[str]:
        return [
            f"mom_{self.config.params.get('momentum_window', 20)}",
            f"vol_{self.config.params.get('vol_window', 20)}"
        ]


def create_variants() -> list[Strategy]:
    variants = []

    for mult in [2.0, 3.0]:
        variants.append(VolBreakout(StrategyConfig(
            name=f"VolBreakout_{mult}",
            params={"atr_multiplier": mult, "lookback": 20}
        )))

    variants.append(LowVolRegime(StrategyConfig(
        name="LowVol_Regime", params={"vol_window": 20, "percentile": 50}
    )))

    variants.append(VolAdjustedMomentum(StrategyConfig(
        name="VolAdj_Mom",
        params={"momentum_window": 20, "vol_window": 20}
    )))

    return variants
