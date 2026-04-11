from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class StrategyConfig:
    """Immutable parameter container for a strategy variant."""
    name: str
    params: dict = field(default_factory=dict)


class Strategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.name = config.name

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals from feature-augmented OHLCV data.

        Returns a Series with values in {0, 1}:
            1 = long, 0 = flat
        Index must align with the input DataFrame's index.
        """
        ...

    @abstractmethod
    def required_features(self) -> list[str]:
        """Return list of feature column names this strategy needs."""
        ...
