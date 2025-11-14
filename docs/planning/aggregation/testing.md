# Aggregation Module Test Plan

## 1. Objective

To verify that the `aggregation` module correctly, efficiently, and reliably transforms 5-second intraday data into 1-minute and 5-minute aggregated bars, while handling edge cases gracefully.

## 2. Test Framework & Location

-   **Framework:** `pytest`
-   **Location:** `tests/aggregation/test_aggregator.py`

## 3. Test Fixtures

A `pytest` fixture will be created to provide a standardized, reusable `pandas.DataFrame` representing `intraday_5s` data.

-   **`sample_market_data` fixture:**
    -   **Input:** None.
    -   **Output:** A dictionary `{'intraday_5s': df, 'daily': empty_df}`.
    -   **Details:** The `intraday_5s` DataFrame will be programmatically generated to span exactly 10 minutes (e.g., from 09:30:00 to 09:39:55), containing 120 rows. The OHLCV and VWAP values will be simple, predictable series (e.g., arange) to make assertions straightforward.

## 4. Unit Test Cases

### Test Case 1: Successful Aggregation

-   **Name:** `test_successful_aggregation`
-   **Description:** Verifies the standard, successful execution path.
-   **Setup:** Use the `sample_market_data` fixture.
-   **Action:** Call `aggregation.aggregator.aggregate_data()` with the fixture data.
-   **Assertions:**
    1.  The returned dictionary must contain four keys: `'daily'`, `'intraday_5s'`, `'intraday_1m'`, `'intraday_5m'`.
    2.  The `'intraday_1m'` DataFrame should have exactly 10 rows.
    3.  The `'intraday_5m'` DataFrame should have exactly 2 rows.
    4.  For the first 1-minute bar:
        -   Assert `open` equals the first `open` of the source data.
        -   Assert `high` equals the max of the first 12 `high` values.
        -   Assert `low` equals the min of the first 12 `low` values.
        -   Assert `close` equals the `close` of the 12th row.
        -   Assert `volume` equals the sum of the first 12 `volume` values.
        -   Assert `vwap` equals the `vwap` of the 12th row.
    5.  Repeat assertions for the first 5-minute bar (covering the first 60 rows of source data).

### Test Case 2: Input Validation

-   **Name:** `test_missing_intraday_key`
-   **Description:** Ensures the function handles inputs where the `'intraday_5s'` key is missing.
-   **Setup:** Create a dictionary `{'daily': df}`.
-   **Action:** Call `aggregate_data()` with this dictionary.
-   **Assertions:**
    1.  The function should return the original dictionary, unchanged.
    2.  The number of keys in the output should be 1.
    3.  Check that a `WARNING` level message was logged (requires `caplog` fixture).

### Test Case 3: Empty DataFrame

-   **Name:** `test_empty_intraday_dataframe`
-   **Description:** Ensures the function handles an empty `'intraday_5s'` DataFrame.
-   **Setup:** Create a dictionary `{'intraday_5s': pd.DataFrame(), 'daily': df}`.
-   **Action:** Call `aggregate_data()` with this dictionary.
-   **Assertions:**
    1.  The function should return the original dictionary, unchanged.
    2.  The number of keys in the output should be 2.
    3.  Check that a `WARNING` level message was logged.

### Test Case 4: Partial Final Bar

-   **Name:** `test_partial_final_bar_aggregation`
-   **Description:** Verifies that data that doesn't fill a complete final bar is still aggregated correctly.
-   **Setup:** Use the `sample_market_data` fixture but truncate the source DataFrame to 7.5 minutes of data (90 rows, ending at 09:37:25).
-   **Action:** Call `aggregate_data()`.
-   **Assertions:**
    1.  The `'intraday_5m'` DataFrame should have 2 rows.
    2.  The second (and last) row of the `'intraday_5m'` DataFrame should correctly aggregate the data from 09:35:00 to 09:37:25 (30 rows).
    3.  Verify the OHLCV and VWAP values for this partial bar.
