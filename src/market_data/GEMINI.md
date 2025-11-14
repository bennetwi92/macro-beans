# `src/market_data` Module for Agents

This document provides guidance for agents interacting with the `src/market_data` module.

## Purpose

The `market_data` module is designed to collect specific financial datasets by wrapping the project's existing `src.broker` service, which interfaces with the TWS API. Its primary function is to provide:
1.  **5-second intraday data** for a specified trading date and time window (09:00-13:00 UK time).
2.  **Daily historical data** for the last 45 calendar days.

## How to Use

The main entry point for this module is the `fetch_market_data` function located in `src/market_data/collector.py`.

### `fetch_market_data` Function

```python
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
```

**Arguments:**
-   `symbol` (str): The stock ticker symbol (e.g., 'AAPL', 'SPY').
-   `trade_date` (str or `datetime.date`): The specific date for which to pull intraday data. Can be a string in 'YYYY-MM-DD' format or a `date` object.
-   `sec_type` (str, optional): The security type (default: "STK").
-   `exchange` (str, optional): The exchange (default: "SMART").
-   `currency` (str, optional): The currency (default: "USD").
-   `host` (str, optional): TWS host address (default: "127.0.0.1").
-   `port` (int, optional): TWS port number (default: 7496).
-   `client_id` (int, optional): TWS client ID (default: 1).

**Returns:**
A dictionary containing two `pandas.DataFrame` objects:
-   `'daily'`: Contains daily historical data.
-   `'intraday_5s'`: Contains 5-second intraday data.

**Example Usage:**

```python
from src.market_data.collector import fetch_market_data
from datetime import date

# Fetch data for SPY for a specific date
data = fetch_market_data(symbol="SPY", trade_date=date(2025, 11, 12))

if data["daily"].empty:
    print("No daily data fetched or an error occurred.")
else:
    print("Daily Data Head:\n", data["daily"].head())

if data["intraday_5s"].empty:
    print("No intraday data fetched or an error occurred.")
else:
    print("Intraday 5s Data Head:\n", data["intraday_5s"].head())
```

## Important Considerations for Agents

-   **TWS/IB Gateway Connection**: This module relies on a running TWS or IB Gateway instance. Ensure it is active and accessible at the specified `host` and `port`.
-   **Timezone Awareness**: The module handles timezone conversions internally (UK time to UTC for TWS requests). Be mindful of the `trade_date` input and how it aligns with market hours.
-   **Error Handling**: The `fetch_market_data` function includes a `try-except` block for `BrokerError` (errors originating from the `src.broker` service). If an error occurs, it logs the error and returns empty DataFrames. Agents should check if the returned DataFrames are empty.
-   **Dependencies**: The module depends on `pandas`, `pytz`, and `src.broker`. Ensure these are correctly installed and configured in the environment.
-   **Logging**: The module uses the project's centralized `src.logging` module. Check the `logs/market_data.log` file for detailed operational information and errors.
