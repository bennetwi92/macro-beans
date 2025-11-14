# src/market_data/collector.py

import pandas as pd
import pytz
from datetime import datetime, timedelta, date, time

from src.logging.core import get_logger
from src.broker.connection import get_historical_data, BrokerError

# Initialize a logger for this module
logger = get_logger("market_data")

# Default parameters for TWS contracts
DEFAULT_SEC_TYPE = "STK"
DEFAULT_EXCHANGE = "SMART"
DEFAULT_CURRENCY = "USD"

def _fetch_daily_data(symbol: str, **kwargs) -> pd.DataFrame:
    """
    Fetches the last 45 days of daily data for a given symbol.
    """
    utc_tz = pytz.utc
    today = datetime.now(utc_tz).date()
    end_date = utc_tz.localize(datetime.combine(today - timedelta(days=1), time.max))
    start_date = utc_tz.localize(datetime.combine(end_date.date() - timedelta(days=45), time.min))

    logger.info(f"Fetching daily data for {symbol} from {start_date} to {end_date}")
    return get_historical_data(
        symbol=symbol,
        sec_type=kwargs.get("sec_type", DEFAULT_SEC_TYPE),
        exchange=kwargs.get("exchange", DEFAULT_EXCHANGE),
        currency=kwargs.get("currency", DEFAULT_CURRENCY),
        start_date=start_date,
        end_date=end_date,
        bar_size="DAILY",
        use_rth=True,
        host=kwargs.get("host", "127.0.0.1"),
        port=kwargs.get("port", 7496),
        client_id=kwargs.get("client_id", 1),
        timezone="UTC"
    )

def _fetch_intraday_data(symbol: str, trade_date: date, **kwargs) -> pd.DataFrame:
    """
    Fetches 5-second intraday data for a given symbol and date between
    09:00 and 13:00 UK time.
    """
    uk_tz = pytz.timezone("Europe/London")
    
    # Define start and end times in UK timezone
    start_date_uk = uk_tz.localize(datetime.combine(trade_date, time(9, 0)))
    end_date_uk = uk_tz.localize(datetime.combine(trade_date, time(13, 0)))

    logger.info(f"Fetching intraday data for {symbol} on {trade_date} from {start_date_uk} to {end_date_uk}")
    return get_historical_data(
        symbol=symbol,
        sec_type=kwargs.get("sec_type", DEFAULT_SEC_TYPE),
        exchange=kwargs.get("exchange", DEFAULT_EXCHANGE),
        currency=kwargs.get("currency", DEFAULT_CURRENCY),
        start_date=start_date_uk,
        end_date=end_date_uk,
        bar_size="5 secs",
        use_rth=False, # Must be False to get pre-market data
        host=kwargs.get("host", "127.0.0.1"),
        port=kwargs.get("port", 7496),
        client_id=kwargs.get("client_id", 1),
        timezone="UTC"
    )


def fetch_market_data(
    symbol: str,
    trade_date: str | date,
    sec_type: str = DEFAULT_SEC_TYPE,
    exchange: str = DEFAULT_EXCHANGE,
    currency: str = DEFAULT_CURRENCY,
    host: str = "127.0.0.1",
    port: int = 7496,
    client_id: int = 1
) -> dict[str, pd.DataFrame]:
    """
    Collects two datasets for a given symbol by wrapping the broker service:
    1. 5-second intraday data for a specific date (09:00-13:00 UK time).
    2. Daily data for the last 45 days.

    Args:
        symbol: The stock ticker symbol (e.g., 'AAPL').
        trade_date: The date for intraday data ('YYYY-MM-DD' or date object).
        sec_type: The security type (default: "STK").
        exchange: The exchange (default: "SMART").
        currency: The currency (default: "USD").
        host: TWS host address.
        port: TWS port number.
        client_id: TWS client ID.

    Returns:
        A dictionary containing the two datasets as pandas DataFrames:
        {'intraday_5s': df_intraday, 'daily': df_daily}
    """
    if isinstance(trade_date, str):
        trade_date_obj = datetime.strptime(trade_date, "%Y-%m-%d").date()
    else:
        trade_date_obj = trade_date

    common_params = {
        "sec_type": sec_type,
        "exchange": exchange,
        "currency": currency,
        "host": host,
        "port": port,
        "client_id": client_id
    }

    try:
        df_daily = _fetch_daily_data(symbol, **common_params)
        df_intraday = _fetch_intraday_data(symbol, trade_date_obj, **common_params)

        logger.success(f"Successfully fetched data for {symbol}")
        return {
            "daily": df_daily,
            "intraday_5s": df_intraday
        }
    except BrokerError as e:
        # Log the error from the broker service
        logger.error(f"An error occurred while fetching data for {symbol} from the broker: {e}")
        # Return empty DataFrames as a fallback
        return {
            "daily": pd.DataFrame(),
            "intraday_5s": pd.DataFrame()
        }
