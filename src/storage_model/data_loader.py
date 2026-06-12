"""Data loader for the storage model.

Thin wrapper over the shared MarketStore (DuckDB price cache). Kept as a
class so existing call sites (`StorageDataLoader(config).load()`) are
unchanged; the actual storage/fetch now lives in src.data.
"""

import logging

import pandas as pd

from src.data.refresh import refresh
from src.data.store import MarketStore, validate_prices
from src.storage_model.config import StorageConfig

logger = logging.getLogger(__name__)


class StorageDataLoader:
    """Loads OHLCV data for a single asset from the DuckDB price cache."""

    def __init__(self, config: StorageConfig, store: MarketStore | None = None):
        self.config = config
        self.store = store or MarketStore()

    def load(self) -> pd.DataFrame:
        """Load data from the cache, fetching from yfinance on a cache miss."""
        df = self.store.get_prices(self.config.ticker)
        if df.empty:
            logger.info(f"Cache miss — fetching {self.config.ticker} from yfinance")
            refresh([self.config.ticker], full=True)
            df = self.store.get_prices(self.config.ticker)

        df = self._filter_date_range(df)
        validate_prices(df, self.config.ticker)
        return df

    def refresh(self) -> pd.DataFrame:
        """Force a fresh download from yfinance, then reload from cache."""
        refresh([self.config.ticker], full=True)
        df = self.store.get_prices(self.config.ticker)
        df = self._filter_date_range(df)
        validate_prices(df, self.config.ticker)
        return df

    def _filter_date_range(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter to the configured date range."""
        start = pd.Timestamp(self.config.start_date)
        df = df[df.index >= start]
        if self.config.end_date:
            end = pd.Timestamp(self.config.end_date)
            df = df[df.index <= end]
        return df
