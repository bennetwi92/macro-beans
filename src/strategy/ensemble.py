import numpy as np
import pandas as pd
from loguru import logger

from src.strategy.base import Strategy, StrategyConfig
from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import compute_metrics


class EqualWeightEnsemble(Strategy):
    """Equal-weight average of sub-strategy signals."""

    def __init__(self, config: StrategyConfig, sub_strategies: list[Strategy]):
        super().__init__(config)
        self.sub_strategies = sub_strategies

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        threshold = self.config.params.get("threshold", 0.5)
        if not self.sub_strategies:
            return pd.Series(0.0, index=data.index)

        all_signals = []
        for strat in self.sub_strategies:
            try:
                sig = strat.generate_signals(data)
                all_signals.append(sig)
            except Exception as e:
                logger.warning(f"Ensemble sub-strategy {strat.name} failed: {e}")
                continue

        if not all_signals:
            return pd.Series(0.0, index=data.index)

        avg = pd.concat(all_signals, axis=1).mean(axis=1)
        return (avg >= threshold).astype(float)

    def required_features(self) -> list[str]:
        features = set()
        for strat in self.sub_strategies:
            features.update(strat.required_features())
        return list(features)

    def get_sub_signals(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        """Get individual signals from each sub-strategy."""
        result = {}
        for strat in self.sub_strategies:
            try:
                result[strat.name] = strat.generate_signals(data)
            except Exception:
                continue
        return result


class SharpeWeightedEnsemble(Strategy):
    """Sharpe-weighted average of sub-strategy signals."""

    def __init__(self, config: StrategyConfig, sub_strategies: list[Strategy],
                 weights: list[float]):
        super().__init__(config)
        self.sub_strategies = sub_strategies
        self.weights = weights

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        threshold = self.config.params.get("threshold", 0.5)
        if not self.sub_strategies:
            return pd.Series(0.0, index=data.index)

        all_signals = []
        valid_weights = []
        for strat, w in zip(self.sub_strategies, self.weights):
            try:
                sig = strat.generate_signals(data)
                all_signals.append(sig * w)
                valid_weights.append(w)
            except Exception as e:
                logger.warning(f"Ensemble sub-strategy {strat.name} failed: {e}")
                continue

        if not all_signals:
            return pd.Series(0.0, index=data.index)

        total_weight = sum(valid_weights)
        if total_weight == 0:
            return pd.Series(0.0, index=data.index)

        weighted_avg = pd.concat(all_signals, axis=1).sum(axis=1) / total_weight
        return (weighted_avg >= threshold).astype(float)

    def required_features(self) -> list[str]:
        features = set()
        for strat in self.sub_strategies:
            features.update(strat.required_features())
        return list(features)

    def get_sub_signals(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        result = {}
        for strat in self.sub_strategies:
            try:
                result[strat.name] = strat.generate_signals(data)
            except Exception:
                continue
        return result


class RegimeSwitchEnsemble(Strategy):
    """Use trend strategies in high-vol, mean-reversion in low-vol."""

    def __init__(self, config: StrategyConfig,
                 trend_strategies: list[Strategy],
                 mr_strategies: list[Strategy]):
        super().__init__(config)
        self.trend_strategies = trend_strategies
        self.mr_strategies = mr_strategies

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        vol_window = self.config.params.get("vol_window", 60)
        vol_pct = self.config.params.get("vol_percentile", 50)

        vol_col = f"vol_{vol_window}" if f"vol_{vol_window}" in data.columns else "vol_20"
        if vol_col not in data.columns:
            return pd.Series(0.0, index=data.index)

        vol = data[vol_col]
        vol_threshold = vol.expanding(min_periods=60).apply(
            lambda x: np.percentile(x, vol_pct), raw=True
        )
        high_vol = vol > vol_threshold

        # Get average signal from each group
        trend_sig = self._avg_signal(self.trend_strategies, data)
        mr_sig = self._avg_signal(self.mr_strategies, data)

        signal = pd.Series(0.0, index=data.index)
        signal[high_vol] = trend_sig[high_vol]
        signal[~high_vol] = mr_sig[~high_vol]
        return (signal >= 0.5).astype(float)

    def _avg_signal(self, strategies: list[Strategy], data: pd.DataFrame) -> pd.Series:
        if not strategies:
            return pd.Series(0.0, index=data.index)
        signals = []
        for s in strategies:
            try:
                signals.append(s.generate_signals(data))
            except Exception:
                continue
        if not signals:
            return pd.Series(0.0, index=data.index)
        return pd.concat(signals, axis=1).mean(axis=1)

    def required_features(self) -> list[str]:
        features = set()
        for s in self.trend_strategies + self.mr_strategies:
            features.update(s.required_features())
        return list(features)


def build_ensemble_from_results(
    results: list[BacktestResult],
    strategies: list[Strategy],
    top_n: int = 7,
    method: str = "sharpe_weighted"
) -> Strategy:
    """Build an ensemble from backtest results, selecting top N strategies by Sharpe."""
    # Map strategy name to Strategy object
    name_to_strat = {s.name: s for s in strategies}

    # Sort by Sharpe
    sorted_results = sorted(results, key=lambda r: r.metrics.get("sharpe", 0), reverse=True)
    top_results = sorted_results[:top_n]

    top_strats = []
    sharpes = []
    for r in top_results:
        if r.strategy_name in name_to_strat:
            top_strats.append(name_to_strat[r.strategy_name])
            sharpes.append(max(r.metrics.get("sharpe", 0), 0.01))

    if method == "equal":
        return EqualWeightEnsemble(
            StrategyConfig(name="Ensemble_EqualWeight", params={"threshold": 0.5, "top_n": top_n}),
            sub_strategies=top_strats,
        )
    else:
        total = sum(sharpes)
        weights = [s / total for s in sharpes] if total > 0 else [1 / len(sharpes)] * len(sharpes)
        return SharpeWeightedEnsemble(
            StrategyConfig(name="Ensemble_SharpeWeight", params={"threshold": 0.5, "top_n": top_n}),
            sub_strategies=top_strats,
            weights=weights,
        )
