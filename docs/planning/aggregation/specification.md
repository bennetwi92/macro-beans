# Aggregation Module Specification

## 1. Purpose

The `aggregation` module is responsible for taking raw, 5-second intraday market data and creating additional, higher-timeframe datasets through resampling. It will produce 1-minute and 5-minute bars, which are common timeframes for trading analysis.

## 2. Inputs

The primary input is a dictionary of `pandas.DataFrame` objects, as produced by the `market_data.collector` module.

- **Expected Key:** `'intraday_5s'`
- **DataFrame Requirements:**
    - The DataFrame must have a `DatetimeIndex`.
    - It must contain the following columns: `open`, `high`, `low`, `close`, `volume`, `vwap`.

The module will also pass through any other keys in the input dictionary (e.g., `'daily'`) without modification.

## 3. Outputs

The module will return a dictionary of `pandas.DataFrame` objects containing the original datasets plus the newly aggregated ones.

- **Output Keys:** `'daily'`, `'intraday_5s'`, `'intraday_1m'`, `'intraday_5m'`.

## 4. Core Logic

The module's core function, `aggregate_data`, will perform the following steps:

1.  Check if the `'intraday_5s'` key exists and its DataFrame is not empty. If not, it will log a warning and return the input dictionary unmodified.
2.  Create copies of the original DataFrames to avoid side effects.
3.  Resample the `intraday_5s` DataFrame into two new DataFrames:
    -   One for 1-minute bars (resampling rule: `'1T'`).
    -   One for 5-minute bars (resampling rule: `'5T'`).
4.  The aggregation rules for resampling will be as follows:
    -   `open`: The first price of the period (`'first'`).
    -   `high`: The maximum price of the period (`'max'`).
    -   `low`: The minimum price of the period (`'min'`).
    -   `close`: The last price of the period (`'last'`).
    -   `volume`: The sum of all volume in the period (`'sum'`).
    -   `vwap`: The last price of the period (`'last'`).
5.  Add the two new DataFrames to the output dictionary under the keys `'intraday_1m'` and `'intraday_5m'`.
6.  Return the final dictionary.

## 5. Error Handling

- If the input dictionary is missing the `'intraday_5s'` key, the function will log a warning and return the original dictionary.
- If the `'intraday_5s'` DataFrame is empty, the function will log a warning and return the original dictionary.
- The function will handle `NaN` values that may result from resampling periods with no data by dropping them (`.dropna()`).
