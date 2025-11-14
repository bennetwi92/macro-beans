import pandas as pd
from src.logging import get_logger

log = get_logger("aggregation")

def aggregate_data(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Aggregates 5-second intraday market data into higher timeframes (1-minute and 5-minute bars).

    Args:
        data (dict[str, pd.DataFrame]): A dictionary containing market data.
                                        Expected to have an 'intraday_5s' key
                                        with a pandas DataFrame containing
                                        'open', 'high', 'low', 'close', 'volume', 'vwap' columns
                                        and a DatetimeIndex.

    Returns:
        dict[str, pd.DataFrame]: A new dictionary containing the original data
                                 plus 'intraday_1m' and 'intraday_5m' DataFrames.
                                 Returns the original dictionary unmodified if
                                 'intraday_5s' data is missing or empty.
    """
    if 'intraday_5s' not in data or data['intraday_5s'].empty:
        log.warning("Missing or empty 'intraday_5s' DataFrame in input data. Returning original data.")
        return data

    # Create a copy of the input data to avoid modifying the original
    result = data.copy()
    intraday_5s_df = data['intraday_5s']

    # Define aggregation rules
    aggregation_rules = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'vwap': 'last'
    }

    # Resample to 1-minute bars
    intraday_1m_df = intraday_5s_df.resample('1min').apply(aggregation_rules).dropna()
    result['intraday_1m'] = intraday_1m_df

    # Resample to 5-minute bars
    intraday_5m_df = intraday_5s_df.resample('5min').apply(aggregation_rules).dropna()
    result['intraday_5m'] = intraday_5m_df

    return result
