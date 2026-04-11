import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class TechnicalComposite(Strategy):
    """Multi-indicator composite score: long when score >= threshold."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        threshold = self.config.params.get("threshold", 2)

        score = pd.Series(0.0, index=data.index)

        # RSI oversold recovery (+1)
        if "rsi_14" in data.columns:
            score += (data["rsi_14"] < 40).astype(float)

        # MACD bullish (+1)
        if "macd_hist" in data.columns:
            score += (data["macd_hist"] > 0).astype(float)

        # Price above 50-day SMA (+1)
        if "sma_50" in data.columns:
            score += (data["close"] > data["sma_50"]).astype(float)

        # Volume above average (+1)
        if "volume_ratio" in data.columns:
            score += (data["volume_ratio"] > 1.0).astype(float)

        return (score >= threshold).astype(float)

    def required_features(self) -> list[str]:
        return ["rsi_14", "macd_hist", "sma_50", "volume_ratio"]


def create_variants() -> list[Strategy]:
    return [
        TechnicalComposite(StrategyConfig(
            name="TechComposite_2", params={"threshold": 2}
        )),
        TechnicalComposite(StrategyConfig(
            name="TechComposite_3", params={"threshold": 3}
        )),
    ]
