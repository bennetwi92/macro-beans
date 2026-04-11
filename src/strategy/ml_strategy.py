import numpy as np
import pandas as pd
from loguru import logger

from src.strategy.base import Strategy, StrategyConfig


class MLStrategy(Strategy):
    """Machine learning strategy using expanding-window classification."""

    FEATURE_COLS = [
        "rsi_14", "macd", "macd_hist", "bb_pct", "atr",
        "zscore_20", "zscore_50", "vol_20", "vol_60",
        "mom_5", "mom_10", "mom_20", "mom_60",
    ]

    CROSS_ASSET_COLS = [
        "dxy_mom_20", "vix", "xle_vs_spx_20", "oil_gold_zscore",
        "spx_above_200", "roll_yield_proxy",
    ]

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        model_type = self.config.params.get("model", "random_forest")
        n_estimators = self.config.params.get("n_estimators", 200)
        max_depth = self.config.params.get("max_depth", 5)
        min_train = self.config.params.get("min_train_days", 504)
        retrain_freq = self.config.params.get("retrain_frequency", 21)

        # Select available features
        feature_cols = [c for c in self.FEATURE_COLS + self.CROSS_ASSET_COLS
                        if c in data.columns]

        if len(feature_cols) < 3:
            logger.warning(f"ML strategy: not enough features, returning flat")
            return pd.Series(0.0, index=data.index)

        # Target: next-day return positive = 1, else 0
        returns = data["close"].pct_change().shift(-1)
        target = (returns > 0).astype(int)

        features = data[feature_cols].copy()

        signal = pd.Series(0.0, index=data.index)
        model = None
        last_train = 0

        for i in range(min_train, len(data)):
            # Retrain periodically
            if model is None or (i - last_train) >= retrain_freq:
                train_X = features.iloc[:i].dropna()
                train_y = target.loc[train_X.index].dropna()
                common = train_X.index.intersection(train_y.index)
                train_X = train_X.loc[common]
                train_y = train_y.loc[common]

                if len(train_X) < min_train // 2:
                    continue

                model = self._build_model(model_type, n_estimators, max_depth)
                model.fit(train_X.values, train_y.values)
                last_train = i

            # Predict
            if model is not None:
                row = features.iloc[i:i + 1].dropna()
                if len(row) == 1:
                    pred = model.predict(row.values)[0]
                    signal.iloc[i] = float(pred)

        return signal

    def _build_model(self, model_type, n_estimators, max_depth):
        if model_type == "gradient_boosting":
            from sklearn.ensemble import GradientBoostingClassifier
            return GradientBoostingClassifier(
                n_estimators=n_estimators, max_depth=max_depth, random_state=42
            )
        else:
            from sklearn.ensemble import RandomForestClassifier
            return RandomForestClassifier(
                n_estimators=n_estimators, max_depth=max_depth,
                random_state=42, n_jobs=-1
            )

    def required_features(self) -> list[str]:
        return self.FEATURE_COLS


def create_variants() -> list[Strategy]:
    return [
        MLStrategy(StrategyConfig(
            name="ML_RF",
            params={"model": "random_forest", "n_estimators": 200,
                    "max_depth": 5, "min_train_days": 504, "retrain_frequency": 21}
        )),
        MLStrategy(StrategyConfig(
            name="ML_GBM",
            params={"model": "gradient_boosting", "n_estimators": 200,
                    "max_depth": 3, "min_train_days": 504, "retrain_frequency": 21}
        )),
    ]
