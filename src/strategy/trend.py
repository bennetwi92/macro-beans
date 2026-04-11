import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class SMACrossover(Strategy):
    """Long when fast SMA > slow SMA."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        fast = data[f"sma_{self.config.params['fast']}"]
        slow = data[f"sma_{self.config.params['slow']}"]
        return (fast > slow).astype(float)

    def required_features(self) -> list[str]:
        return [f"sma_{self.config.params['fast']}", f"sma_{self.config.params['slow']}"]


class EMACrossover(Strategy):
    """Long when fast EMA > slow EMA."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        fast = data[f"ema_{self.config.params['fast']}"]
        slow = data[f"ema_{self.config.params['slow']}"]
        return (fast > slow).astype(float)

    def required_features(self) -> list[str]:
        return [f"ema_{self.config.params['fast']}", f"ema_{self.config.params['slow']}"]


class Momentum(Strategy):
    """Long when price is above its level N days ago."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        period = self.config.params["period"]
        return (data[f"mom_{period}"] > 0).astype(float)

    def required_features(self) -> list[str]:
        return [f"mom_{self.config.params['period']}"]


class DonchianBreakout(Strategy):
    """Long when price breaks above Donchian high channel."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        window = self.config.params["window"]
        high_chan = data[f"donchian_high_{window}"].shift(1)
        return (data["close"] >= high_chan).astype(float)

    def required_features(self) -> list[str]:
        return [f"donchian_high_{self.config.params['window']}"]


def create_variants() -> list[Strategy]:
    variants = []

    for fast, slow in [(10, 50), (20, 100), (50, 200)]:
        variants.append(SMACrossover(StrategyConfig(
            name=f"SMA_{fast}_{slow}", params={"fast": fast, "slow": slow}
        )))

    for fast, slow in [(12, 26), (20, 50)]:
        variants.append(EMACrossover(StrategyConfig(
            name=f"EMA_{fast}_{slow}", params={"fast": fast, "slow": slow}
        )))

    for period in [10, 20, 60]:
        variants.append(Momentum(StrategyConfig(
            name=f"Momentum_{period}", params={"period": period}
        )))

    for window in [20, 50]:
        variants.append(DonchianBreakout(StrategyConfig(
            name=f"Donchian_{window}", params={"window": window}
        )))

    return variants
