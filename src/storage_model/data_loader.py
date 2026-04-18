"""Data loader for the storage model — yfinance with CSV cache"""

import pandas as pd
import yfinance as yf
from pathlib import Path
import logging

from src.storage_model.config import StorageConfig

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/stock_history")


class StorageDataLoader:
    """Loads OHLCV data for a single asset from CSV cache or yfinance."""

    def __init__(self, config: StorageConfig, cache_dir: Path = CACHE_DIR):
        self.config = config
        self.cache_dir = Path(cache_dir)

    def load(self) -> pd.DataFrame:
        """Load data from cache if available, otherwise download."""
        cache_path = self.cache_dir / f"{self.config.ticker}.csv"

        if cache_path.exists():
            logger.info(f"Loading {self.config.ticker} from cache: {cache_path}")
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        else:
            logger.info(f"Cache miss — downloading {self.config.ticker} from yfinance")
            df = self._download()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_path)

        df = self._filter_date_range(df)
        self._validate(df)
        return df

    def refresh(self) -> pd.DataFrame:
        """Force download fresh data from yfinance."""
        df = self._download()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / f"{self.config.ticker}.csv"
        df.to_csv(cache_path)
        df = self._filter_date_range(df)
        self._validate(df)
        return df

    def _download(self) -> pd.DataFrame:
        """Download full history from yfinance."""
        ticker = yf.Ticker(self.config.ticker)
        df = ticker.history(period="max", auto_adjust=True)
        if df.empty:
            raise ValueError(f"No data returned from yfinance for {self.config.ticker}")
        # Drop timezone info from index for consistency
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df

    def _filter_date_range(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter to the configured date range."""
        start = pd.Timestamp(self.config.start_date)
        df = df[df.index >= start]
        if self.config.end_date:
            end = pd.Timestamp(self.config.end_date)
            df = df[df.index <= end]
        return df

    def _validate(self, df: pd.DataFrame):
        """Check required columns exist."""
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        if len(df) < 100:
            raise ValueError(
                f"Only {len(df)} rows for {self.config.ticker} — need at least 100 "
                f"for meaningful analysis (start_date={self.config.start_date})"
            )
