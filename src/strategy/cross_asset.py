import pandas as pd

from src.strategy.base import Strategy, StrategyConfig


class EnergyRelativeStrength(Strategy):
    """Long oil when energy sector (XLE) is outperforming broad market (SPX)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "xle_vs_spx_20" not in data.columns:
            return pd.Series(0.0, index=data.index)
        return (data["xle_vs_spx_20"] > 0).astype(float)

    def required_features(self) -> list[str]:
        return ["xle_vs_spx_20"]


class OilGoldRatio(Strategy):
    """Long when oil/gold ratio is mean-reverting from a low level."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "oil_gold_zscore" not in data.columns:
            return pd.Series(0.0, index=data.index)
        threshold = self.config.params.get("entry_threshold", -1.5)
        exit_threshold = self.config.params.get("exit_threshold", 0.0)
        zscore = data["oil_gold_zscore"]

        signal = pd.Series(0.0, index=data.index)
        in_trade = False
        for i in range(len(zscore)):
            if pd.isna(zscore.iloc[i]):
                continue
            if not in_trade and zscore.iloc[i] < threshold:
                in_trade = True
            elif in_trade and zscore.iloc[i] > exit_threshold:
                in_trade = False
            signal.iloc[i] = 1.0 if in_trade else 0.0

        return signal

    def required_features(self) -> list[str]:
        return ["oil_gold_zscore"]


class EquityOverlay(Strategy):
    """Only long oil when S&P 500 is above its 200-day SMA (risk-on)."""

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        if "spx_above_200" not in data.columns:
            return pd.Series(0.0, index=data.index)
        # Combine with basic momentum: long oil when SPX risk-on AND oil momentum positive
        mom = data.get("mom_20", pd.Series(0.0, index=data.index))
        if isinstance(mom, pd.DataFrame):
            mom = mom.iloc[:, 0]
        spx_on = data["spx_above_200"]
        return ((spx_on > 0) & (mom > 0)).astype(float)

    def required_features(self) -> list[str]:
        return ["spx_above_200", "mom_20"]


def create_variants() -> list[Strategy]:
    return [
        EnergyRelativeStrength(StrategyConfig(
            name="Energy_RelStr", params={"window": 20}
        )),
        OilGoldRatio(StrategyConfig(
            name="OilGold_Ratio",
            params={"entry_threshold": -1.5, "exit_threshold": 0.0}
        )),
        EquityOverlay(StrategyConfig(
            name="Equity_Overlay", params={}
        )),
    ]
