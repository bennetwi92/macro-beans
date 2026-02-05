"""Configuration for mean reversion model"""

from dataclasses import dataclass
from typing import List, Optional
import numpy as np


@dataclass
class ModelConfig:
    """Model configuration parameters"""
    # Data parameters
    lookback_days: int = 60  # Days of history for feature calculation
    min_volume: float = 1e6  # Minimum average volume

    # Label generation - Option B: 2% target in 10 days
    target_return: float = 0.02  # 2% profit target
    stop_loss: float = -0.03  # -3% stop loss
    max_holding_days: int = 10  # Maximum days to hold position (increased from 5)

    # ATR-based targets (DISABLED - using fixed % instead)
    use_atr_targets: bool = False  # Use fixed percentage targets
    atr_target_multiplier: float = 1.5  # Multiply ATR by this for profit target
    atr_stop_multiplier: float = 1.0  # Multiply ATR by this for stop loss

    # Feature engineering
    rsi_periods: List[int] = None
    bb_periods: List[int] = None
    volume_ma_periods: List[int] = None

    # Model parameters
    model_type: str = "lightgbm"  # "lightgbm" or "xgboost"
    n_estimators: int = 500
    max_depth: int = 6
    learning_rate: float = 0.05
    min_child_samples: int = 20
    subsample: float = 0.8
    colsample_bytree: float = 0.8

    # Cross-validation
    n_splits: int = 5
    gap_days: int = 5  # Gap between train and test to avoid lookahead
    test_days: int = 60  # Days in each test fold

    # Backtesting
    initial_capital: float = 100000
    position_size: float = 0.1  # 10% per position
    max_positions: int = 5
    confidence_threshold: float = 0.60  # Minimum probability to enter trade (lowered from 0.65)

    # Production
    model_save_path: str = "models/mean_reversion_model.pkl"
    feature_names_path: str = "models/feature_names.pkl"

    def __post_init__(self):
        """Set default values for list parameters"""
        if self.rsi_periods is None:
            self.rsi_periods = [5, 10, 14, 20]
        if self.bb_periods is None:
            self.bb_periods = [10, 20, 50]
        if self.volume_ma_periods is None:
            self.volume_ma_periods = [5, 10, 20]


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    transaction_cost: float = 0.001  # 0.1% per trade
    slippage: float = 0.001  # 0.1% slippage