import numpy as np
import pandas as pd
from loguru import logger


class FeatureEngine:
    """Computes technical and macro features for strategy consumption."""

    def compute_all(self, primary: pd.DataFrame,
                    related: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Augment the primary OHLCV DataFrame with all feature columns."""
        df = primary.copy()

        df = self._add_moving_averages(df)
        df = self._add_ema(df)
        df = self._add_rsi(df)
        df = self._add_bollinger_bands(df)
        df = self._add_macd(df)
        df = self._add_donchian(df)
        df = self._add_atr(df)
        df = self._add_zscore(df)
        df = self._add_volatility(df)
        df = self._add_momentum(df)
        df = self._add_seasonal(df)
        df = self._add_volume_features(df)
        df = self._add_cross_asset(df, related)

        logger.info(f"Computed {len(df.columns)} total columns, {len(df)} rows")
        return df

    def _add_moving_averages(self, df: pd.DataFrame,
                              windows: list[int] = None) -> pd.DataFrame:
        if windows is None:
            windows = [10, 20, 50, 100, 200]
        for w in windows:
            df[f"sma_{w}"] = df["close"].rolling(w).mean()
        return df

    def _add_ema(self, df: pd.DataFrame,
                 spans: list[int] = None) -> pd.DataFrame:
        if spans is None:
            spans = [12, 20, 26, 50]
        for s in spans:
            df[f"ema_{s}"] = df["close"].ewm(span=s, adjust=False).mean()
        return df

    def _add_rsi(self, df: pd.DataFrame,
                 periods: list[int] = None) -> pd.DataFrame:
        if periods is None:
            periods = [7, 14, 21]
        for p in periods:
            delta = df["close"].diff()
            gain = delta.clip(lower=0)
            loss = (-delta).clip(lower=0)
            avg_gain = gain.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / p, min_periods=p, adjust=False).mean()
            rs = avg_gain / avg_loss
            df[f"rsi_{p}"] = 100 - (100 / (1 + rs))
        return df

    def _add_bollinger_bands(self, df: pd.DataFrame,
                              window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
        mid = df["close"].rolling(window).mean()
        std = df["close"].rolling(window).std()
        df["bb_mid"] = mid
        df["bb_upper"] = mid + num_std * std
        df["bb_lower"] = mid - num_std * std
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        return df

    def _add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        return df

    def _add_donchian(self, df: pd.DataFrame,
                       windows: list[int] = None) -> pd.DataFrame:
        if windows is None:
            windows = [20, 50]
        for w in windows:
            df[f"donchian_high_{w}"] = df["high"].rolling(w).max()
            df[f"donchian_low_{w}"] = df["low"].rolling(w).min()
        return df

    def _add_atr(self, df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window).mean()
        return df

    def _add_zscore(self, df: pd.DataFrame,
                     windows: list[int] = None) -> pd.DataFrame:
        if windows is None:
            windows = [20, 50]
        for w in windows:
            mean = df["close"].rolling(w).mean()
            std = df["close"].rolling(w).std()
            df[f"zscore_{w}"] = (df["close"] - mean) / std
        return df

    def _add_volatility(self, df: pd.DataFrame,
                         windows: list[int] = None) -> pd.DataFrame:
        if windows is None:
            windows = [10, 20, 60]
        returns = df["close"].pct_change()
        for w in windows:
            df[f"vol_{w}"] = returns.rolling(w).std() * np.sqrt(252)
        return df

    def _add_momentum(self, df: pd.DataFrame,
                       periods: list[int] = None) -> pd.DataFrame:
        if periods is None:
            periods = [5, 10, 20, 60]
        for p in periods:
            df[f"mom_{p}"] = df["close"].pct_change(p)
        return df

    def _add_seasonal(self, df: pd.DataFrame) -> pd.DataFrame:
        df["month"] = df.index.month
        df["day_of_week"] = df.index.dayofweek
        return df

    def _add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if "volume" in df.columns:
            df["volume_sma_20"] = df["volume"].rolling(20).mean()
            df["volume_ratio"] = df["volume"] / df["volume_sma_20"]
        return df

    def _add_cross_asset(self, df: pd.DataFrame,
                          related: dict[str, pd.DataFrame]) -> pd.DataFrame:
        # Align all related data to the primary index
        for name, rel_df in related.items():
            if rel_df.empty or "close" not in rel_df.columns:
                continue

            rel_close = rel_df["close"].reindex(df.index, method="ffill")

            # Daily returns of related asset
            df[f"{name.lower()}_ret_1d"] = rel_close.pct_change()

            # 20-day momentum of related asset
            df[f"{name.lower()}_mom_20"] = rel_close.pct_change(20)

        # Specific cross-asset features
        if "XLE" in related and "SPX" in related:
            xle = related["XLE"]["close"].reindex(df.index, method="ffill")
            spx = related["SPX"]["close"].reindex(df.index, method="ffill")
            xle_ret = xle.pct_change(20)
            spx_ret = spx.pct_change(20)
            df["xle_vs_spx_20"] = xle_ret - spx_ret

        if "GOLD" in related:
            gold = related["GOLD"]["close"].reindex(df.index, method="ffill")
            df["oil_gold_ratio"] = df["close"] / gold
            ratio = df["oil_gold_ratio"]
            mean = ratio.rolling(60).mean()
            std = ratio.rolling(60).std()
            df["oil_gold_zscore"] = (ratio - mean) / std

        if "SPX" in related:
            spx = related["SPX"]["close"].reindex(df.index, method="ffill")
            df["spx_sma_200"] = spx.rolling(200).mean()
            df["spx_above_200"] = (spx > df["spx_sma_200"]).astype(float)

        if "VIX" in related:
            vix = related["VIX"]["close"].reindex(df.index, method="ffill")
            df["vix"] = vix

        if "DXY" in related:
            dxy = related["DXY"]["close"].reindex(df.index, method="ffill")
            df["dxy_mom_20"] = dxy.pct_change(20)

        if "CL" in related and "BZ" in related:
            cl = related["CL"]["close"].reindex(df.index, method="ffill")
            bz = related["BZ"]["close"].reindex(df.index, method="ffill")
            # Roll yield proxy: ETF underperformance vs spot = negative roll yield (contango)
            etf_ret_20 = df["close"].pct_change(20)
            spot_ret_20 = bz.pct_change(20)
            df["roll_yield_proxy"] = etf_ret_20 - spot_ret_20

        return df
