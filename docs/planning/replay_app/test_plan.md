# Streamlit Replay App Test Plan

## 1. Objective

To ensure the Streamlit Replay App functions correctly, provides a responsive user interface, accurately fetches and aggregates market data, and displays candlestick charts as specified.

## 2. Test Framework & Location

-   **Framework:** `pytest` (for backend logic, if any can be isolated)
-   **Location:** `tests/replay/test_app.py` (for unit tests of any isolated functions)
-   **Manual Testing:** Due to the interactive nature of Streamlit applications, significant manual testing will be required to verify UI/UX and end-to-end functionality.

## 3. Unit Test Cases (for isolatable backend logic)

While much of a Streamlit app's testing is manual, any functions that can be decoupled from the Streamlit UI should have unit tests.

### Test Case 1: Data Fetching and Aggregation Integration

-   **Name:** `test_data_pipeline_integration`
-   **Description:** Verifies that `fetch_market_data` and `aggregate_data` can be called sequentially without errors and produce expected output structures.
-   **Setup:** Mock `src.broker.connection.get_historical_data` to return predictable data.
-   **Action:** Call `fetch_market_data` and then `aggregate_data` with mock data.
-   **Assertions:**
    1.  Ensure the output dictionary contains `'daily'`, `'intraday_5s'`, `'intraday_1m'`, and `'intraday_5m'` keys.
    2.  Verify that the DataFrames are not empty.

## 4. Manual Test Cases (UI/UX and End-to-End)

These tests will be performed by running the Streamlit application and interacting with it.

### Test Case 1: Initial Load and UI Elements

-   **Description:** Verify the initial state of the application and the presence of all UI elements.
-   **Steps:**
    1.  Run the Streamlit app (`streamlit run src/replay/app.py`).
    2.  Verify that the symbol input field, date input widget, and "Load Data" button are visible.
    3.  Verify that no charts are displayed initially.
    4.  Verify that no error messages are displayed initially.

### Test Case 2: Successful Data Load and Chart Display

-   **Description:** Verify that valid inputs lead to successful data fetching, aggregation, and chart display.
-   **Steps:**
    1.  Enter a valid stock symbol (e.g., "SPY").
    2.  Select a valid trading date (e.g., a recent date with known market data).
    3.  Click the "Load Data" button.
    4.  Verify that a loading indicator is displayed briefly.
    5.  Verify that four candlestick charts appear in a 2x2 grid.
    6.  Verify that each chart is correctly labeled with its timeframe (5s, 1m, 5m, Daily).
    7.  Visually inspect charts for reasonable data representation (e.g., candles, volume bars).

### Test Case 3: VWAP Display on Charts

-   **Description:** Verify that VWAP is correctly displayed on intraday charts and not on the daily chart.
-   **Steps:**
    1.  Perform a successful data load (as in Test Case 2).
    2.  Visually inspect the 5-second, 1-minute, and 5-minute charts to confirm that a VWAP line is present.
    3.  Visually inspect the Daily chart to confirm that no VWAP line is present.

### Test Case 4: Invalid Symbol Input

-   **Description:** Verify error handling for an invalid or non-existent stock symbol.
-   **Steps:**
    1.  Enter an invalid symbol (e.g., "INVALIDSYM").
    2.  Select a valid date.
    3.  Click "Load Data".
    4.  Verify that an appropriate error message is displayed (e.g., "Could not find contract for INVALIDSYM" or similar).
    5.  Verify that no charts are displayed.

### Test Case 5: No Data for Date

-   **Description:** Verify error handling when no market data is available for the selected date.
-   **Steps:**
    1.  Enter a valid symbol.
    2.  Select a date far in the past or future, or a weekend/holiday where no trading occurred.
    3.  Click "Load Data".
    4.  Verify that an appropriate message is displayed (e.g., "No market data found for SPY on YYYY-MM-DD" or "Intraday data is empty").
    5.  Verify that no charts are displayed.

### Test Case 6: Empty Input Fields

-   **Description:** Verify handling of empty input fields.
-   **Steps:**
    1.  Leave the symbol field empty.
    2.  Click "Load Data".
    3.  Verify that a warning or error message prompts the user to enter a symbol.
    4.  Repeat for an empty date field.

### Test Case 7: Performance and Responsiveness

-   **Description:** Assess the application's performance and responsiveness.
-   **Steps:**
    1.  Perform several successful data loads.
    2.  Observe the time taken for data to load and charts to render.
    3.  Verify that the UI remains responsive during interactions.
    4.  Check if Streamlit's caching mechanisms are effectively reducing load times on subsequent requests for the same data.

## 5. Logging Verification

-   **Description:** Verify that application logs are correctly generated.
-   **Steps:**
    1.  Perform various actions (successful load, errors, invalid inputs).
    2.  Check the `logs/replay_app.log` file (or similar, based on `get_logger` configuration) for relevant log entries at appropriate levels (INFO, WARNING, ERROR).
