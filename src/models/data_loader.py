"""Data loader for stock price data.

Sources prices from the shared MarketStore (DuckDB cache) rather than reading
CSVs directly, so the model side and the rest of the repo share one cache and
one universe definition (the registry).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

from src.data.store import MarketStore

logger = logging.getLogger(__name__)


class DataLoader:
    """Load and prepare stock data for model training"""

    def __init__(self, store: MarketStore = None):
        """Initialize data loader backed by the DuckDB price cache."""
        self.store = store or MarketStore()

        # Available universe = whatever is cached in the store.
        self.available_symbols = self.store.available_tickers()
        logger.info(f"Found {len(self.available_symbols)} symbols in the price cache")

    def load_symbol(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """Load data for a single symbol as a Date-column frame (legacy shape)."""
        try:
            prices = self.store.get_prices(symbol, start=start_date, end=end_date)

            if prices.empty:
                logger.warning(f"No cached data for {symbol}")
                return pd.DataFrame()

            # Legacy contract: 'Date' is a column (not the index), plus 'Symbol'.
            df = prices.reset_index().sort_values('Date')
            df['Symbol'] = symbol

            required_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_cols):
                logger.warning(f"Missing required columns for {symbol}")
                return pd.DataFrame()

            # Remove any rows with invalid prices
            df = df[(df['Open'] > 0) & (df['High'] > 0) & (df['Low'] > 0) & (df['Close'] > 0)]

            # Ensure High >= Low
            df = df[df['High'] >= df['Low']]

            logger.debug(f"Loaded {len(df)} rows for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Error loading {symbol}: {e}")
            return pd.DataFrame()

    def load_multiple_symbols(self, symbols: List[str] = None, start_date: str = None,
                            end_date: str = None, min_volume: float = 1e6) -> Dict[str, pd.DataFrame]:
        """Load data for multiple symbols"""
        if symbols is None:
            symbols = self.available_symbols

        data = {}
        for symbol in symbols:
            df = self.load_symbol(symbol, start_date, end_date)

            if not df.empty:
                # Filter by minimum volume
                avg_volume = df['Volume'].rolling(window=20).mean()
                if avg_volume.iloc[-20:].mean() >= min_volume:
                    data[symbol] = df
                    logger.debug(f"Loaded {symbol} with avg volume {avg_volume.iloc[-20:].mean():,.0f}")
                else:
                    logger.debug(f"Skipped {symbol} - low volume")

        logger.info(f"Loaded data for {len(data)} symbols")
        return data

    def prepare_training_data(self, symbols: List[str] = None, start_date: str = None,
                            end_date: str = None) -> pd.DataFrame:
        """Prepare combined training data from multiple symbols"""
        logger.info("Preparing training data")

        # Load data for all symbols
        all_data = self.load_multiple_symbols(symbols, start_date, end_date)

        # Combine into single DataFrame
        combined_data = []
        for symbol, df in all_data.items():
            df['Symbol'] = symbol
            combined_data.append(df)

        if not combined_data:
            logger.warning("No data loaded")
            return pd.DataFrame()

        combined_df = pd.concat(combined_data, ignore_index=True)
        combined_df = combined_df.sort_values(['Date', 'Symbol'])

        logger.info(f"Prepared {len(combined_df)} rows from {len(all_data)} symbols")
        return combined_df

    def get_latest_data(self, symbols: List[str] = None, lookback_days: int = 60) -> pd.DataFrame:
        """Get latest data for prediction"""
        if symbols is None:
            symbols = self.available_symbols

        latest_data = []
        for symbol in symbols:
            df = self.load_symbol(symbol)
            if not df.empty and len(df) >= lookback_days:
                # Get last lookback_days of data
                recent_df = df.tail(lookback_days).copy()
                recent_df['Symbol'] = symbol
                latest_data.append(recent_df)

        if latest_data:
            return pd.concat(latest_data, ignore_index=True)
        else:
            return pd.DataFrame()

    def validate_data_quality(self, df: pd.DataFrame) -> Dict:
        """Validate data quality and return statistics"""
        stats = {
            'total_rows': len(df),
            'unique_symbols': df['Symbol'].nunique() if 'Symbol' in df.columns else 1,
            'date_range': f"{df['Date'].min()} to {df['Date'].max()}",
            'missing_values': df.isnull().sum().to_dict(),
            'negative_prices': ((df[['Open', 'High', 'Low', 'Close']] < 0).sum()).to_dict(),
            'invalid_high_low': (df['High'] < df['Low']).sum(),
            'zero_volume_days': (df['Volume'] == 0).sum(),
            'avg_daily_volume': df['Volume'].mean()
        }

        return stats