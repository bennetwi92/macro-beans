# Aggregation Module Development Plan

This document outlines the development steps for creating the `aggregation` module.

## Phase 1: Scaffolding & Setup

1.  **Create Directory Structure:**
    -   `src/aggregation/`
    -   `tests/aggregation/`

2.  **Create Initial Files:**
    -   `src/aggregation/__init__.py`
    -   `src/aggregation/aggregator.py` (main logic)
    -   `src/aggregation/GEMINI.md` (documentation for agents)
    -   `tests/aggregation/__init__.py`
    -   `tests/aggregation/test_aggregator.py` (unit tests)

3.  **Update Environment:**
    -   Ensure `pandas` is listed in `environment.yml` (it should already be present).

## Phase 2: Core Logic Implementation

1.  **Get Logger:**
    -   In `src/aggregation/aggregator.py`, import `get_logger` from `src.logging` and initialize a logger for the module: `log = get_logger("aggregation")`.

2.  **Define `aggregate_data` function:**
    -   Create the main function: `def aggregate_data(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:`.
    -   Add comprehensive docstrings explaining its purpose, parameters, and return value.

3.  **Implement Input Validation:**
    -   Add checks to ensure the `'intraday_5s'` key exists and the corresponding DataFrame is not empty. Log a warning and return the input `data` if checks fail.

4.  **Implement Resampling Logic:**
    -   Use `df.resample()` on the `intraday_5s` DataFrame.
    -   Apply the aggregation rules:
        -   `open`: `'first'`
        -   `high`: `'max'`
        -   `low`: `'min'`
        -   `close`: `'last'`
        -   `volume`: `'sum'`
        -   `vwap`: `'last'`
    -   Perform the resampling for `'1T'` and `'5T'` frequencies.
    -   Handle potential `NaN` values by dropping rows where all values are null.

5.  **Construct Output:**
    -   Create a new dictionary to hold the results.
    -   Add the original and new DataFrames to the dictionary with the correct keys.
    -   Return the result dictionary.

## Phase 3: Testing

1.  **Setup Test Fixture:**
    -   In `tests/aggregation/test_aggregator.py`, create a `pytest` fixture that generates a sample `intraday_5s` DataFrame. This DataFrame should span at least 10 minutes and have predictable values.

2.  **Write Unit Tests:**
    -   **`test_successful_aggregation`**: Verify that the output contains all four data keys and that the aggregated data (OHLCV, VWAP) is correct for the first 1-min and 5-min bars.
    -   **`test_input_validation`**: Test the cases where the `'intraday_5s'` key is missing or the DataFrame is empty. Ensure the function returns the original data and logs a warning.
    -   **`test_edge_cases`**: Test with data that doesn't align perfectly to minute boundaries to ensure the last bar is handled correctly.

## Phase 4: Documentation & Integration

1.  **Write `GEMINI.md`:**
    -   Create the `src/aggregation/GEMINI.md` file, explaining the module's purpose, how to use the `aggregate_data` function, and its inputs/outputs.

2.  **Create Validation Script (Optional but Recommended):**
    -   Create a new script in `scripts/` that:
        1.  Calls `fetch_market_data` to get real data.
        2.  Passes the result to `aggregate_data`.
        3.  Prints the head of each of the four DataFrames to allow for visual inspection.
