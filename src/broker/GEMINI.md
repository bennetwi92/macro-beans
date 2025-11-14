# Broker Module

## Overview

This module provides a high-level interface to connect to the Interactive Brokers (IB) Trader Workstation (TWS) API and download historical bar data.

It handles the complexities of the TWS API, including:
- Connection and disconnection.
- Pagination to download data over long date ranges.
- Robust error handling with custom exceptions.
- Data parsing into a clean pandas DataFrame.

## Primary Interface

The main function is `get_historical_data()`.

```python
def get_historical_data(
    symbol: str,
    sec_type: str,
    exchange: str,
    currency: str,
    start_date: datetime,
    end_date: datetime,
    bar_size: str,
    use_rth: bool = False,
    host: str = "127.0.0.1",
    port: int = 7496,
    client_id: int = 1,
    timezone: str = "UTC"
) -> pd.DataFrame:
```

## Example Usage

```python
from datetime import datetime
import pytz
from src.broker.connection import get_historical_data, ContractNotFoundError

utc = pytz.utc
start = datetime(2025, 10, 20, tzinfo=utc)
end = datetime(2025, 10, 24, tzinfo=utc)

try:
    clik_data = get_historical_data(
        symbol="CLIK",
        sec_type="STK",
        exchange="SMART",
        currency="USD",
        start_date=start,
        end_date=end,
        bar_size="DAILY"
    )
    print(clik_data.head())
except ContractNotFoundError as e:
    print(f"Could not find the contract: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

```

## Return Value

The function returns a `pandas.DataFrame` indexed by date, with the following columns:
- `open`
- `high`
- `low`
- `close`
- `volume`
- `vwap`

## Error Handling

The module will raise specific exceptions for common failures:
- `ContractNotFoundError`: If the requested security cannot be found.
- `DataRequestError`: For general API errors during a data request.
- `ConnectionTimeoutError`: If a connection to TWS cannot be established in time.

## Prerequisites

A running instance of TWS or IB Gateway is required, with the API enabled for connections.

## Testing

Unit tests for this module are located in `tests/broker/`. They can be executed by running `pytest` from the project root directory.
