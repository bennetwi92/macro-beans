import os
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf
from loguru import logger


class DataProvider:
    """Fetches and caches OHLCV data from yfinance."""

    def __init__(self, cache_dir: str = ".cache/data"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Fetch daily OHLCV for a single ticker, using CSV cache."""
        cache_key = f"{ticker.replace('.', '_').replace('^', '_')}_{start}_{end}"
        cache_path = self.cache_dir / f"{cache_key}.csv"

        if cache_path.exists():
            logger.debug(f"Loading cached data for {ticker}")
            return pd.read_csv(cache_path, index_col="date", parse_dates=True)

        logger.info(f"Downloading {ticker} from {start} to {end}")
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)

        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return df

        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Standardize column names
        df.columns = [c.lower() for c in df.columns]
        df.index.name = "date"

        # Forward-fill gaps up to 5 days
        df = df.ffill(limit=5)

        df.to_csv(cache_path)
        logger.debug(f"Cached {len(df)} rows for {ticker}")
        return df

    def fetch_universe(self, config_path: str = "config/tickers.yml",
                       start: str = "2016-01-01",
                       end: str = "2026-04-10") -> dict[str, pd.DataFrame]:
        """Fetch data for all tickers defined in the config."""
        with open(config_path) as f:
            config = yaml.safe_load(f)

        result = {}

        # Primary tickers
        for name, symbol in config.get("primary", {}).items():
            result[name] = self.fetch(symbol, start, end)

        # Related tickers
        for name, symbol in config.get("related", {}).items():
            result[name] = self.fetch(symbol, start, end)

        return result
