# Aggregation Module

## Overview

This module is responsible for aggregating 5-second intraday market data into higher timeframes (1-minute and 5-minute bars).

## Primary Interface

The main function is `aggregate_data()`.

```python
def aggregate_data(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
```

## Inputs

The primary input is a dictionary of `pandas.DataFrame` objects, as produced by the `market_data.collector` module.

- **Expected Key:** `'intraday_5s'`
- **DataFrame Requirements:**
    - The DataFrame must have a `DatetimeIndex`.
    - It must contain the following columns: `open`, `high`, `low`, `close`, `volume`, `vwap`.

The module will also pass through any other keys in the input dictionary (e.g., `'daily'`) without modification.

## Outputs

The module will return a dictionary of `pandas.DataFrame` objects containing the original datasets plus the newly aggregated ones.

- **Output Keys:** `'daily'`, `'intraday_5s'`, `'intraday_1m'`, `'intraday_5m'`.

## Aggregation Rules

The aggregation rules for resampling are as follows:
- `open`: The first price of the period (`'first'`).
- `high`: The maximum price of the period (`'max'`).
- `low`: The minimum price of the period (`'min'`).
- `close`: The last price of the period (`'last'`).
- `volume`: The sum of all volume in the period (`'sum'`).
- `vwap`: The last price of the period (`'last'`).

## Error Handling

- If the input dictionary is missing the `'intraday_5s'` key, the function will log a warning and return the original dictionary.
- If the `'intraday_5s'` DataFrame is empty, the function will log a warning and return the original dictionary.
- The function will handle `NaN` values that may result from resampling periods with no data by dropping them (`.dropna()`).
