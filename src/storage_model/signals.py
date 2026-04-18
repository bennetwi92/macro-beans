"""Signal engine for storage model — seasonal, mean reversion, and momentum signals"""

import pandas as pd
import numpy as np

from src.storage_model.config import StorageConfig


class StorageSignalEngine:
    """Generates composite injection/withdrawal signals from three components:
    1. Seasonal score — data-driven signal based on empirical monthly returns
    2. Mean reversion z-score — price deviation from rolling mean
    3. Momentum filter — short-term rate of change to avoid catching falling knives
    """

    def __init__(self, config: StorageConfig):
        self.config = config

    def compute_seasonal_score(self, df: pd.DataFrame) -> pd.Series:
        """Data-driven seasonal signal in [-1, +1].

        Uses empirical monthly return statistics to assign a continuous score:
        months with lower-than-average returns get positive scores (inject = buy cheap),
        months with higher-than-average returns get negative scores (withdraw = sell expensive).

        This is more accurate than a pure sinusoidal fit because it reflects the
        asset's actual seasonal pattern rather than assuming a smooth cycle.
        """
        monthly_stats = self.compute_monthly_seasonality(df)
        mean_returns = monthly_stats["mean_return"]

        # Center returns around zero and negate:
        # below-average return months → positive (inject signal)
        # above-average return months → negative (withdraw signal)
        centered = -(mean_returns - mean_returns.mean())

        # Normalize to [-1, 1]
        max_abs = centered.abs().max()
        if max_abs > 0:
            normalized = centered / max_abs
        else:
            normalized = centered * 0

        # Map each day to its month's score
        month_to_score = normalized.to_dict()
        seasonal = df.index.month.map(month_to_score)
        seasonal = pd.Series(seasonal, index=df.index, name="seasonal_score", dtype=float)
        return seasonal

    def compute_zscore(self, df: pd.DataFrame) -> pd.Series:
        """Rolling z-score of Close price vs its moving average.

        Reuses the Bollinger Bands concept from src/models/features.py:
        z = (price - SMA) / rolling_std

        Negative z-score -> price is cheap -> inject signal.
        Positive z-score -> price is expensive -> withdraw signal.
        """
        window = self.config.zscore_window
        close = df["Close"]
        sma = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()
        zscore = (close - sma) / (std + 1e-10)
        zscore.name = "zscore"
        return zscore

    def compute_momentum(self, df: pd.DataFrame) -> pd.Series:
        """Short-term rate of change as a momentum filter.

        Prevents injecting into an accelerating decline or withdrawing
        into a strong rally continuation.
        """
        window = self.config.momentum_window
        close = df["Close"]
        momentum = close.pct_change(periods=window)
        momentum.name = "momentum"
        return momentum

    def compute_composite_signal(self, df: pd.DataFrame) -> pd.DataFrame:
        """Combine all three signals into a composite in [-1, +1].

        Returns a DataFrame with columns:
            seasonal_score, zscore, momentum, composite
        Sign convention: positive = inject (buy), negative = withdraw (sell).
        """
        seasonal = self.compute_seasonal_score(df)
        zscore = self.compute_zscore(df)
        momentum = self.compute_momentum(df)

        cfg = self.config

        # Normalize each signal to roughly [-1, 1] using percentile-based scaling
        # Z-score: already roughly in [-3, 3], clip and scale
        zscore_norm = (-zscore).clip(-3, 3) / 3  # negated: low z = inject

        # Momentum: scale by rolling 95th percentile of absolute momentum
        mom_abs_95 = momentum.abs().rolling(252, min_periods=63).quantile(0.95)
        mom_abs_95 = mom_abs_95.clip(lower=0.01)  # floor to avoid division by zero
        momentum_norm = (-momentum / mom_abs_95).clip(-1, 1)  # negated: falling = discourage inject

        # Build composite
        composite = (
            cfg.seasonal_weight * seasonal
            + cfg.zscore_weight * zscore_norm
            + cfg.momentum_weight * momentum_norm
        )
        composite = composite.clip(-1, 1)

        signals = pd.DataFrame({
            "seasonal_score": seasonal,
            "zscore": zscore,
            "momentum": momentum,
            "composite": composite,
        }, index=df.index)

        return signals

    def compute_monthly_seasonality(self, df: pd.DataFrame) -> pd.DataFrame:
        """Empirical monthly return statistics for the asset.

        Returns DataFrame indexed by month (1-12) with columns:
            mean_return, median_return, std, count, month_name
        """
        monthly_returns = df["Close"].resample("ME").last().pct_change()
        monthly_returns = monthly_returns.dropna()

        stats = monthly_returns.groupby(monthly_returns.index.month).agg(
            mean_return="mean",
            median_return="median",
            std="std",
            count="count",
        ).round(4)

        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        stats["month_name"] = month_names
        stats.index.name = "month"
        return stats
