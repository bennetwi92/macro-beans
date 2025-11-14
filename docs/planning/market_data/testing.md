# Test Plan: Market Data Collector Module

This document describes the testing strategy for the Market Data Collector module to ensure its correctness, reliability, and robustness.

## 1. Testing Objectives

-   Verify that the module correctly fetches both intraday and daily datasets according to the specifications, by leveraging the `broker` service.
-   Ensure that data is parsed and structured correctly into `pandas.DataFrame` objects.
-   Confirm that all date and time calculations, including timezone handling, are accurate.
-   Validate the module's resilience by testing its error-handling capabilities, including those propagated from the `broker` service.
-   Prevent regressions by establishing a comprehensive suite of automated tests.

## 2. Testing Levels

### 2.1. Unit Tests

Unit tests will form the core of the testing strategy. The external `src.broker.connection.get_historical_data` function **must be mocked** to ensure tests are fast, deterministic, and do not incur costs or network dependencies with the TWS API.

**Test Cases:**

-   **Date/Time Logic:**
    -   Test the function that calculates the daily data range (`today - 45 days` to `yesterday`).
    -   Verify that the UK to ET time conversion for the intraday range is correct.

-   **Broker Service Mocking:**
    -   Mock `src.broker.connection.get_historical_data` to return predefined `pandas.DataFrame` objects.
    -   Test that the `market_data` module's wrapper functions (for daily and intraday) correctly call the mocked `get_historical_data` with the expected parameters (e.g., `symbol`, `sec_type`, `exchange`, `currency`, `start_date`, `end_date`, `bar_size`).

-   **Data Processing & Validation:**
    -   Test with a valid, mocked `broker` service response for intraday data. Verify the resulting DataFrame has the correct columns (`open`, `high`, `low`, `close`, `volume`, `vwap`, `timestamp`) and data types.
    -   Test with a valid, mocked `broker` service response for daily data. Verify the resulting DataFrame has the correct columns and data types.
    -   Check that the timestamps in the intraday DataFrame are within the 09:00-13:00 UK time window.
    -   Check that the number of rows in the daily DataFrame is correct (e.g., ~45, accounting for weekends/holidays).

-   **Orchestrator Function:**
    -   Test the main `fetch_market_data` function. Verify that it returns a dictionary with the keys `'intraday_5s'` and `'daily'`, and that the values are the expected DataFrames.

### 2.2. Integration Tests

Integration tests will be limited and will focus on the module's interaction with other parts of the application, not the external API.

**Test Cases:**

-   **Configuration:**
    -   Test that the module can correctly read TWS connection parameters from the project's configuration system.
-   **Logging:**
    -   Verify that successful data fetches and errors are logged correctly through the project's logging module.

### 2.3. Error Handling Tests

These tests are critical for ensuring the module is robust.

**Test Cases:**

-   **Invalid Inputs:**
    -   Call the main function with an invalid symbol format, an invalid date format, or `None` values. The module should raise appropriate errors (e.g., `ValueError`, `TypeError`).

-   **Broker Service Errors (Mocked):**
    -   Simulate `src.broker.connection.get_historical_data` raising `ContractNotFoundError` or `DataRequestError`. The `market_data` module should propagate or handle these errors gracefully.
    -   Simulate `get_historical_data` returning an empty DataFrame for a valid request. The `market_data` module should handle this gracefully (e.g., return empty DataFrames).

## 3. Tools & Environment

-   **Framework**: `pytest`
-   **Mocking**:
    -   `pytest-mock` or Python's built-in `unittest.mock` for mocking objects and functions, specifically `src.broker.connection.get_historical_data`.
    -   **Recommendation**: Store mock API responses as static JSON files (e.g., in `tests/market_data/mock_responses/`) to keep test code clean.
-   **Time Handling**:
    -   `freezegun`: To pin the current time during tests involving relative dates (e.g., "yesterday"), ensuring tests are deterministic.
-   **Test Location**: All tests for this module will be located in `tests/market_data/`.
