# TWS API Broker Connection Specification

## 1. Objective

This document outlines the specification for a Python module that connects to the Interactive Brokers (IB) TWS API to download historical bar data. The module will provide a simple, lightweight interface for requesting daily or 5-second candlestick data for a given financial instrument within a specified date range.

## 2. Dependencies

- **Software:**
    - Trader Workstation (TWS) or IB Gateway must be running.
    - A funded IB account with appropriate market data subscriptions.
- **Python Libraries:**
    - `ibapi` (the official TWS API library)
    - `pandas` (for data handling)

## 3. Configuration

The module will require the following configuration for the TWS/Gateway connection:
- **Host:** `127.0.0.1`
- **Port:** `7496` (TWS Live), `4001` (Gateway Live), `7497` (TWS Paper), `4002` (Gateway Paper)
- **Client ID:** A unique integer to identify the API connection.

## 4. Connection Management

For simplicity and to ensure a lightweight implementation, the module will adopt a connect-request-disconnect pattern. A connection will be established for each call to `get_historical_data`, the data will be retrieved, and the connection will then be terminated.

## 5. Data Retrieval

### 5.1. `get_historical_data` Function

A primary function, `get_historical_data`, will be exposed to retrieve the data.

**Parameters:**

- `symbol`: The ticker symbol of the instrument (e.g., `"CLIK"`).
- `sec_type`: The security type (e.g., `"STK"`, `"FUT"`, `"CASH"`).
- `exchange`: The destination exchange (e.g., `"SMART"`).
- `currency`: The currency of the instrument (e.g., `"USD"`).
- `start_date`: A timezone-aware `datetime` object for the inclusive start of the data range.
- `end_date`: A timezone-aware `datetime` object for the inclusive end of the data range.
- `bar_size`: A string, either `"DAILY"` or `"5 secs"`.
- `use_rth`: A boolean indicating whether to fetch data for Regular Trading Hours only. Defaults to `False` to include all available data.
- `timezone`: A string representing the desired timezone for the output data (e.g., `"UTC"`). Defaults to `"UTC"`.

The function will construct the `ibapi.contract.Contract` object internally from these parameters.

### 5.2. API Call Strategy

- **Pagination:** The function will automatically handle pagination. It will calculate the required duration and make multiple, sequential `reqHistoricalData` calls to the TWS API to download the complete dataset between `start_date` and `end_date`. This is crucial for longer time periods and smaller bar sizes.
- **`whatToShow`:** To retrieve VWAP, the `whatToShow` parameter of the API call will be hardcoded to `"TRADES"`.
- **Bar Size Handling:**
    - **DAILY:** `barSizeSetting` will be `"1 day"`.
    - **5 seconds:** `barSizeSetting` will be `"5 secs"`.

### 5.3. Pacing and Limitations

- The module will respect the TWS API's pacing limitations.
- For 5-second bars, requests will be paced to avoid making identical requests within 15 seconds and to stay within the 60 requests per 10-minute limit.
- The module will use `reqHeadTimeStamp` to determine the earliest available data for a contract to avoid requesting non-existent data.

## 6. Data Handling

- **Time Zones:** All input `datetime` objects must be timezone-aware. The module will use this information to make correct requests to the TWS API. The output DataFrame's index will be localized to the specified `timezone` parameter.
- **Output:** The downloaded historical data will be returned as a pandas DataFrame with the following columns: `date`, `open`, `high`, `low`, `close`, `volume`, `vwap`.
- The DataFrame will be indexed by `date`.

## 7. Error Handling

- The module will implement the `error` callback from the EWrapper to catch and log API errors.
- Errors will be logged using the project's `logging` module.
- The module will handle common errors, such as connection failures, contract ambiguities, and pacing violations, and will raise appropriate exceptions.

## 8. Logging

- The module will use the existing `logging` module to provide detailed information about its operations.
- Log messages will be generated for:
    - Connection status to the TWS API.
    - Historical data requests (including pagination details).
    - The number of bars downloaded.
    - Any errors or warnings from the API.
- Log messages will be written to the `broker.log` file.