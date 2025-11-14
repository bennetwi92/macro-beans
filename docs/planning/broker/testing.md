# Broker Module Test Plan

This document outlines the testing strategy for the TWS API broker connection module.

## 1. Testing Strategy

A combination of unit and integration tests will be used to ensure the module is robust, reliable, and correct.

-   **Unit Tests:** These will test individual functions and logic in isolation from the live TWS API. The TWS connection will be mocked to allow for predictable testing of pagination, data formatting, and error handling logic.
-   **Integration Tests:** These will test the end-to-end functionality of the module by connecting to a live or paper TWS/Gateway instance. These tests will verify that the module can successfully request and receive data from the TWS API.

## 2. Test Cases

### 2.1. Unit Tests

-   **Contract Creation:**
    -   Verify that the `Contract` object is created correctly from the simplified function parameters (`symbol`, `sec_type`, etc.).
-   **Time Zone Conversion:**
    -   Test that input `datetime` objects are correctly handled.
    -   Test that the output DataFrame index is correctly localized to the specified `timezone`.
-   **Pagination Logic:**
    -   Using a mocked API, verify that a request for a long date range is correctly broken down into multiple smaller requests.
    -   Verify that the results from paginated calls are correctly stitched together in the correct chronological order.
-   **Error Handling:**
    -   Test that the module raises the correct exception for mocked TWS error codes (e.g., invalid contract, connection failed).

### 2.2. Integration Tests (Requires TWS/Gateway Connection)

These tests will use the specific examples provided.

**Test Instrument:** CLIK (assuming this is a valid symbol for testing)

-   **Test Case 1: 5-Second Bars**
    -   **Description:** Request 5-second data for a one-hour period.
    -   **Parameters:**
        -   `symbol`: "CLIK"
        -   `start_date`: `2025-10-27 09:00:00`
        -   `end_date`: `2025-10-27 10:00:00`
        -   `bar_size`: `"5 secs"`
    -   **Expected Result:** A pandas DataFrame containing 5-second bars for the specified period. The DataFrame should have the columns `date`, `open`, `high`, `low`, `close`, `volume`, and `vwap`. The `date` index should be continuous and correctly spaced.

-   **Test Case 2: Daily Bars**
    -   **Description:** Request daily data for a three-month period.
    -   **Parameters:**
        -   `symbol`: "CLIK"
        -   `start_date`: `2025-07-27`
        -   `end_date`: `2025-10-26`
        -   `bar_size`: `"DAILY"`
    -   **Expected Result:** A pandas DataFrame containing daily bars for the specified period. The DataFrame should have the correct number of trading days and the specified columns.

-   **Test Case 3: Invalid Symbol**
    -   **Description:** Request data for a symbol that does not exist.
    -   **Parameters:**
        -   `symbol`: "INVALID_SYMBOL_XYZ"
        -   `sec_type`: "STK"
        -   ...
    -   **Expected Result:** The function should raise a specific, informative exception (e.g., `ContractNotFound`) indicating that the security could not be found.

-   **Test Case 4: Data Not Available**
    -   **Description:** Request data for a time period where no data exists.
    -   **Parameters:**
        -   `symbol`: "CLIK"
        -   `start_date`: A date far in the past (e.g., `1980-01-01`)
    -   **Expected Result:** The function should return an empty DataFrame and log a warning that no data was found for the requested period.
