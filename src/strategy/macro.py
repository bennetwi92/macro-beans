import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class USDInverse(Strategy):
    """Long oil when USD is weakening (negative momentum)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "dxy_mom_20" not in data.columns:
            return pd.Series(0.0, index=data.index)
        return (data["dxy_mom_20"] < 0).astype(float)

    def required_features(self) -> list[str]:
        return ["dxy_mom_20"]


class VIXRegime(Strategy):
    """Long oil in risk-on environments (low VIX)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "vix" not in data.columns:
            return pd.Series(0.0, index=data.index)
        threshold = self.config.params["threshold"]
        return (data["vix"] < threshold).astype(float)

    def required_features(self) -> list[str]:
        return ["vix"]


class USDVIXCombo(Strategy):
    """Long when both USD weakening AND VIX is low."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "dxy_mom_20" not in data.columns or "vix" not in data.columns:
            return pd.Series(0.0, index=data.index)
        vix_threshold = self.config.params["vix_threshold"]
        usd_weak = data["dxy_mom_20"] < 0
        vix_low = data["vix"] < vix_threshold
        return (usd_weak & vix_low).astype(float)

    def required_features(self) -> list[str]:
        return ["dxy_mom_20", "vix"]


def create_variants() -> list[Strategy]:
    return [
        USDInverse(StrategyConfig(name="USD_Inverse", params={"window": 20})),
        VIXRegime(StrategyConfig(name="VIX_Low_20", params={"threshold": 20})),
        VIXRegime(StrategyConfig(name="VIX_Low_25", params={"threshold": 25})),
        USDVIXCombo(StrategyConfig(name="USD_VIX_Combo", params={"vix_threshold": 22})),
    ]
