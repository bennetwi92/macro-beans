import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class RollYieldStrategy(Strategy):
    """Long when roll yield proxy suggests backwardation (positive for ETF)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        lookback = self.config.params["lookback"]
        if "roll_yield_proxy" not in data.columns:
            return pd.Series(0.0, index=data.index)

        # Smooth the roll yield proxy
        smoothed = data["roll_yield_proxy"].rolling(lookback).mean()

        # Long when in backwardation (ETF outperforming spot = positive roll yield)
        # Actually for commodity ETFs, negative roll yield proxy means contango
        # (ETF underperforms spot) => we want to be flat
        # Positive means backwardation => long
        return (smoothed > 0).astype(float)

    def required_features(self) -> list[str]:
        return ["roll_yield_proxy"]


def create_variants() -> list[Strategy]:
    variants = []
    for lookback in [20, 60]:
        variants.append(RollYieldStrategy(StrategyConfig(
            name=f"Carry_{lookback}", params={"lookback": lookback}
        )))
    return variants
