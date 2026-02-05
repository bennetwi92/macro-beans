"""Feature engineering pipeline for mean reversion model with ATR-based targets"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Feature engineering pipeline for mean reversion signals"""

    def __init__(self, config):
        """Initialize with configuration"""
        self.config = config
        self.feature_names = []

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']

        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate ATR
        atr = tr.rolling(window=period).mean()

        return atr

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> Dict[str, pd.Series]:
        """Calculate ADX and directional indicators

        Returns:
            dict with keys: adx, plus_di, minus_di
        """
        high = df['High']
        low = df['Low']
        close = df['Close']

        # Calculate +DM and -DM
        high_diff = high.diff()
        low_diff = -low.diff()

        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)

        plus_dm[(high_diff > low_diff) & (high_diff > 0)] = high_diff
        minus_dm[(low_diff > high_diff) & (low_diff > 0)] = low_diff

        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Smooth the indicators using Wilder's smoothing
        atr = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
        minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))

        # Calculate DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.ewm(alpha=1/period, adjust=False).mean()

        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }

    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: int = 2) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()

        return {
            'middle': sma,
            'upper': sma + (std * std_dev),
            'lower': sma - (std * std_dev),
            'bandwidth': (sma + (std * std_dev) - (sma - (std * std_dev))) / sma,
            'percent_b': (prices - (sma - (std * std_dev))) / ((sma + (std * std_dev)) - (sma - (std * std_dev)) + 1e-10)
        }

    def calculate_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume-based features"""
        features = pd.DataFrame(index=df.index)

        # Volume moving averages and ratios
        for period in self.config.volume_ma_periods:
            vol_ma = df['Volume'].rolling(window=period).mean()
            features[f'volume_ma_{period}'] = vol_ma
            features[f'volume_ratio_{period}'] = df['Volume'] / (vol_ma + 1e-10)

        # Volume price trend
        features['volume_price_trend'] = (df['Volume'] * df['Close'].pct_change()).cumsum()

        # On-balance volume
        obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        features['obv'] = obv
        features['obv_ma_20'] = obv.rolling(window=20).mean()
        features['obv_ratio'] = obv / (features['obv_ma_20'] + 1e-10)

        return features

    def calculate_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate momentum and trend features"""
        features = pd.DataFrame(index=df.index)

        # Price returns over multiple periods
        for period in [1, 2, 3, 5, 10, 20]:
            features[f'return_{period}d'] = df['Close'].pct_change(period)

        # Moving averages and crosses
        for period in [5, 10, 20, 50, 200]:
            ma = df['Close'].rolling(window=period).mean()
            features[f'ma_{period}'] = ma
            features[f'price_to_ma_{period}'] = df['Close'] / (ma + 1e-10)

        # MA crosses
        features['ma_5_20_cross'] = features['ma_5'] / (features['ma_20'] + 1e-10)
        features['ma_20_50_cross'] = features['ma_20'] / (features['ma_50'] + 1e-10)

        # ADX and Directional Indicators
        adx_indicators = self.calculate_adx(df, 14)
        features['adx_14'] = adx_indicators['adx']
        features['plus_di_14'] = adx_indicators['plus_di']
        features['minus_di_14'] = adx_indicators['minus_di']
        features['di_diff'] = adx_indicators['plus_di'] - adx_indicators['minus_di']
        features['di_ratio'] = adx_indicators['plus_di'] / (adx_indicators['minus_di'] + 1e-10)

        # Trend clarity features
        features['price_above_ma50'] = (df['Close'] > features['ma_50']).astype(int)
        features['price_above_ma200'] = (df['Close'] > features['ma_200']).astype(int)
        features['ma50_above_ma200'] = (features['ma_50'] > features['ma_200']).astype(int)
        features['ma50_slope'] = features['ma_50'].pct_change(10)  # 10-day slope
        features['trend_alignment'] = ((df['Close'] > features['ma_50']) &
                                       (features['ma_50'] > features['ma_200'])).astype(int)

        # Volatility including ATR
        for period in [5, 10, 20]:
            features[f'volatility_{period}d'] = df['Close'].pct_change().rolling(window=period).std()

        # Add ATR features
        atr_14 = self.calculate_atr(df, 14)
        features['atr_14'] = atr_14
        features['atr_pct'] = atr_14 / df['Close']
        features['atr_20'] = self.calculate_atr(df, 20)
        features['atr_ratio'] = atr_14 / (features['atr_20'] + 1e-10)

        # High-low spread
        features['high_low_ratio'] = df['High'] / (df['Low'] + 1e-10)
        features['close_to_high'] = df['Close'] / (df['High'] + 1e-10)
        features['close_to_low'] = df['Close'] / (df['Low'] + 1e-10)

        return features

    def calculate_oversold_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate oversold condition features"""
        features = pd.DataFrame(index=df.index)

        # Distance from recent highs/lows
        for period in [5, 10, 20, 50]:
            rolling_high = df['High'].rolling(window=period).max()
            rolling_low = df['Low'].rolling(window=period).min()

            features[f'dist_from_high_{period}d'] = (df['Close'] - rolling_high) / (rolling_high + 1e-10)
            features[f'dist_from_low_{period}d'] = (df['Close'] - rolling_low) / (rolling_low + 1e-10)
            features[f'price_position_{period}d'] = (df['Close'] - rolling_low) / (rolling_high - rolling_low + 1e-10)

        # Consecutive down days
        daily_return = df['Close'].pct_change()
        down_days = (daily_return < 0).astype(int)
        features['consecutive_down_days'] = down_days.groupby((down_days != down_days.shift()).cumsum()).cumsum()

        # Oversold composite score
        rsi_14 = self.calculate_rsi(df['Close'], 14)
        bb_20 = self.calculate_bollinger_bands(df['Close'], 20)

        features['oversold_score'] = (
            (rsi_14 < 30).astype(int) * 0.25 +
            (rsi_14 < 40).astype(int) * 0.25 +
            (bb_20['percent_b'] < 0).astype(int) * 0.25 +
            (bb_20['percent_b'] < 0.2).astype(int) * 0.25
        )

        return features

    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create all features for the model"""
        logger.info(f"Creating features for {len(df)} rows")

        # Initialize feature dataframe
        features = pd.DataFrame(index=df.index)

        # RSI features
        for period in self.config.rsi_periods:
            rsi = self.calculate_rsi(df['Close'], period)
            features[f'rsi_{period}'] = rsi
            features[f'rsi_{period}_oversold'] = (rsi < 30).astype(int)
            features[f'rsi_{period}_overbought'] = (rsi > 70).astype(int)

        # Bollinger Bands features
        for period in self.config.bb_periods:
            bb = self.calculate_bollinger_bands(df['Close'], period)
            features[f'bb_percent_b_{period}'] = bb['percent_b']
            features[f'bb_bandwidth_{period}'] = bb['bandwidth']
            features[f'bb_lower_touch_{period}'] = (df['Low'] <= bb['lower']).astype(int)
            features[f'bb_squeeze_{period}'] = (bb['bandwidth'] < bb['bandwidth'].rolling(window=100).quantile(0.2)).astype(int)

        # Volume features
        volume_features = self.calculate_volume_features(df)
        features = pd.concat([features, volume_features], axis=1)

        # Momentum features (includes ATR)
        momentum_features = self.calculate_momentum_features(df)
        features = pd.concat([features, momentum_features], axis=1)

        # Oversold features
        oversold_features = self.calculate_oversold_features(df)
        features = pd.concat([features, oversold_features], axis=1)

        # Market regime features
        features['market_regime'] = self.identify_market_regime(df)

        # Day of week and month features (seasonality)
        if 'Date' in df.columns:
            dates = pd.to_datetime(df['Date'])
            features['day_of_week'] = dates.dt.dayofweek
            features['month'] = dates.dt.month
            features['quarter'] = dates.dt.quarter

        # Store feature names
        self.feature_names = features.columns.tolist()

        # Handle infinities and NaNs
        features = features.replace([np.inf, -np.inf], np.nan)
        features = features.ffill().fillna(0)

        logger.info(f"Created {len(features.columns)} features")

        return features

    def identify_market_regime(self, df: pd.DataFrame) -> pd.Series:
        """Identify market regime (trending up/down/sideways)"""
        ma_20 = df['Close'].rolling(window=20).mean()
        ma_50 = df['Close'].rolling(window=50).mean()

        # Calculate trend strength
        returns_20 = df['Close'].pct_change(20)
        volatility_20 = df['Close'].pct_change().rolling(window=20).std()
        trend_strength = returns_20 / (volatility_20 + 1e-10)

        # Classify regime
        regime = pd.Series(index=df.index, dtype=float)
        regime[trend_strength > 1] = 2  # Strong uptrend
        regime[trend_strength > 0.5] = 1  # Uptrend
        regime[trend_strength < -1] = -2  # Strong downtrend
        regime[trend_strength < -0.5] = -1  # Downtrend
        regime.fillna(0, inplace=True)  # Sideways

        return regime

    def generate_labels(self, df: pd.DataFrame, use_atr: bool = True) -> pd.DataFrame:
        """Generate labels for training using ATR-based or fixed targets

        Args:
            df: DataFrame with OHLCV data
            use_atr: If True, use ATR-based targets. If False, use fixed percentage targets.
        """
        logger.info(f"Generating labels for training (ATR-based: {use_atr})")

        labels = pd.DataFrame(index=df.index)
        labels['label'] = 0
        labels['actual_return'] = np.nan
        labels['holding_days'] = np.nan
        labels['target_price'] = np.nan
        labels['stop_price'] = np.nan

        if use_atr:
            # Calculate ATR for dynamic targets
            atr = self.calculate_atr(df, period=14)

            # ATR multipliers (can be adjusted in config)
            target_multiplier = getattr(self.config, 'atr_target_multiplier', 1.5)
            stop_multiplier = getattr(self.config, 'atr_stop_multiplier', 1.0)

        for i in range(len(df) - self.config.max_holding_days):
            entry_price = df['Close'].iloc[i]

            if use_atr:
                # Use ATR-based targets
                current_atr = atr.iloc[i]
                if pd.isna(current_atr) or current_atr <= 0:
                    continue

                target_price = entry_price + (current_atr * target_multiplier)
                stop_price = entry_price - (current_atr * stop_multiplier)

                # Calculate percentage for logging
                target_return_pct = (target_price - entry_price) / entry_price
                stop_loss_pct = (stop_price - entry_price) / entry_price
            else:
                # Use fixed percentage targets
                target_return_pct = self.config.target_return
                stop_loss_pct = self.config.stop_loss

                target_price = entry_price * (1 + target_return_pct)
                stop_price = entry_price * (1 + stop_loss_pct)

            labels.loc[df.index[i], 'target_price'] = target_price
            labels.loc[df.index[i], 'stop_price'] = stop_price

            # Look ahead for max_holding_days
            for j in range(1, self.config.max_holding_days + 1):
                if i + j >= len(df):
                    break

                future_high = df['High'].iloc[i + j]
                future_low = df['Low'].iloc[i + j]
                future_close = df['Close'].iloc[i + j]

                # Check if target hit
                if future_high >= target_price:
                    labels.loc[df.index[i], 'label'] = 1
                    labels.loc[df.index[i], 'actual_return'] = target_return_pct
                    labels.loc[df.index[i], 'holding_days'] = j
                    break

                # Check if stop hit
                if future_low <= stop_price:
                    labels.loc[df.index[i], 'label'] = 0
                    labels.loc[df.index[i], 'actual_return'] = stop_loss_pct
                    labels.loc[df.index[i], 'holding_days'] = j
                    break

                # If last day, record actual return
                if j == self.config.max_holding_days:
                    labels.loc[df.index[i], 'label'] = 0
                    labels.loc[df.index[i], 'actual_return'] = (future_close - entry_price) / entry_price
                    labels.loc[df.index[i], 'holding_days'] = j

        logger.info(f"Generated labels - Success rate: {labels['label'].mean():.2%}")

        return labels