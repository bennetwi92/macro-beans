import pandas as pd
import numpy as np

from src.strategy.base import Strategy, StrategyConfig


class BollingerMeanReversion(Strategy):
    """Long when price dips below lower Bollinger band, flat when above mid."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        num_std = self.config.params["num_std"]
        window = self.config.params.get("window", 20)

        mid = data["close"].rolling(window).mean()
        std = data["close"].rolling(window).std()
        lower = mid - num_std * std

        signal = pd.Series(np.nan, index=data.index)
        signal[data["close"] < lower] = 1.0
        signal[data["close"] > mid] = 0.0
        signal = signal.ffill().fillna(0.0)
        return signal

    def required_features(self) -> list[str]:
        return ["bb_lower", "bb_mid"]


class RSIMeanReversion(Strategy):
    """Long when RSI is oversold, flat when RSI recovers above exit level."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        oversold = self.config.params["oversold"]
        exit_level = self.config.params.get("exit", 50)
        rsi = data["rsi_14"]

        signal = pd.Series(np.nan, index=data.index)
        signal[rsi < oversold] = 1.0
        signal[rsi > exit_level] = 0.0
        signal = signal.ffill().fillna(0.0)
        return signal

    def required_features(self) -> list[str]:
        return ["rsi_14"]


class ZScoreMeanReversion(Strategy):
    """Long when z-score is deeply negative, flat when it reverts to threshold."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        window = self.config.params["window"]
        entry = self.config.params["entry_threshold"]
        exit_threshold = self.config.params.get("exit_threshold", 0.0)
        zscore = data[f"zscore_{window}"]

        signal = pd.Series(np.nan, index=data.index)
        signal[zscore < entry] = 1.0
        signal[zscore > exit_threshold] = 0.0
        signal = signal.ffill().fillna(0.0)
        return signal

    def required_features(self) -> list[str]:
        return [f"zscore_{self.config.params['window']}"]


def create_variants() -> list[Strategy]:
    variants = []

    for num_std in [1.5, 2.0, 2.5]:
        variants.append(BollingerMeanReversion(StrategyConfig(
            name=f"Bollinger_{num_std}", params={"num_std": num_std, "window": 20}
        )))

    for oversold in [25, 30]:
        variants.append(RSIMeanReversion(StrategyConfig(
            name=f"RSI_MR_{oversold}", params={"oversold": oversold, "exit": 50}
        )))

    for window in [20, 50]:
        for entry in [-1.5, -2.0]:
            variants.append(ZScoreMeanReversion(StrategyConfig(
                name=f"ZScore_{window}_{entry}",
                params={"window": window, "entry_threshold": entry, "exit_threshold": 0.0}
            )))

    return variants
