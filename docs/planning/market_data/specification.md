# Specification: Market Data Collector Module

## 1. Overview

This document outlines the specifications for a Market Data Collector module. The module's primary purpose is to fetch two distinct datasets for a given financial symbol: a high-frequency intraday dataset for a specific day and a medium-term daily dataset over a recent period. This module will leverage the existing `src.broker` service for all data retrieval from the TWS API.

## 2. Core Requirements

### Inputs

The module must accept the following inputs:

-   `symbol` (str): The stock ticker symbol (e.g., 'AAPL', 'SPY').
-   `trade_date` (str or datetime.date): The specific date for which to pull intraday data, formatted as 'YYYY-MM-DD'.

### Datasets to be Fetched

#### Dataset 1: Intraday 5-Second Data

-   **Resolution**: 5-second intervals.
-   **Date**: The single `trade_date` provided as input.
-   **Time Range**: 09:00 to 13:00 UK time.
    -   This corresponds to the US pre-market session from 04:00 ET to 08:00 ET.
    -   **Note**: The implementation must be explicitly timezone-aware, using a library like `pytz` or `zoneinfo` to handle conversions and potential Daylight Saving Time shifts correctly.
-   **Data Columns**: The dataset will be sourced from the `broker` service and will include: `open`, `high`, `low`, `close`, `volume`, `vwap`, and `timestamp`. The module should return at least `open`, `high`, `low`, `close`, `volume`, and `timestamp`.

#### Dataset 2: Daily Data

-   **Resolution**: Daily (1D).
-   **Date Range**: From 45 calendar days before the execution date to the day immediately preceding the execution date ("yesterday").
    -   **Note**: "Execution date" refers to the current system time (`datetime.now()`) when the function is called, not the `trade_date` input.
-   **Data Columns**: The dataset will be sourced from the `broker` service and will include: `open`, `high`, `low`, `close`, `volume`, `vwap`, and `date`. The module should return at least `open`, `high`, `low`, `close`, `volume`, and `date`.

## 3. Technical Details

### Data Source

-   The data will be retrieved exclusively through the existing `src.broker.connection.get_historical_data` function, which interfaces with the TWS API. The `market_data` module will act as a wrapper, preparing the correct parameters for this function.

### Output

-   The primary function of this module will return a simple dictionary containing the two datasets.
-   The datasets themselves should be in a format suitable for analysis, preferably `pandas.DataFrame`.
-   To maintain a lightweight implementation, the initial version should avoid custom classes for the return object.

**Example Return Structure:**

```python
{
    'intraday_5s': pandas.DataFrame(...),
    'daily': pandas.DataFrame(...)
}
```

### Error Handling

The module must gracefully handle potential errors, including:

-   Invalid or non-existent `symbol` as reported by the `broker` service.
-   No data available for the requested `trade_date` or time ranges.
-   Connection errors or API-specific errors propagated from the `broker` service.
-   Rate limiting imposed by the TWS API, handled by the `broker` service.

## 4. Assumptions & Dependencies

-   **Dependencies**:
    -   `pandas`: For data manipulation and storage.
    -   `src.broker`: The module will depend directly on the `src.broker.connection.get_historical_data` function.
    -   A configuration module to handle TWS connection parameters (host, port, client ID) and other credentials securely.
-   **Assumptions**:
    -   The `src.broker` service is correctly configured and able to connect to a running TWS/Gateway instance.
    -   The system will have access to the necessary TWS connection parameters.
    -   The `get_historical_data` function in `src.broker.connection` provides the required 5-second and daily historical data.
