# Replay Module

## Overview

This module contains the Streamlit application for replaying historical market data. It provides a user interface to select a symbol and date, fetch and aggregate market data, and display it as candlestick charts.

## Primary Interface

The main Streamlit application is defined in `app.py`. It is run using the `streamlit run` command.

## Core Functionality

-   **User Input:** Collects stock symbol and trading date from the user.
-   **Data Fetching:** Utilizes `src.market_data.collector.fetch_market_data` to retrieve 5-second intraday and daily historical data from the IB TWS API.
-   **Data Aggregation:** Uses `src.aggregation.aggregator.aggregate_data` to transform 5-second data into 1-minute and 5-minute aggregated bars.
-   **Charting:** Displays the aggregated data as candlestick charts using `plotly.graph_objects`. VWAP is shown on intraday charts but not on the daily chart.
-   **Error Handling:** Provides user-friendly feedback for invalid inputs, data fetching errors, or when no data is available.
-   **Performance:** Employs Streamlit's caching mechanisms (`@st.cache_data`, `@st.cache_resource`) to optimize data loading and aggregation.

## Usage

To run the Streamlit application, navigate to the project's root directory in your terminal and execute:

```bash
streamlit run src/replay/app.py
```

Ensure that a TWS or IB Gateway instance is running and accessible for data fetching.

## Technical Considerations

-   **Dependencies:** `streamlit`, `pandas`, `plotly`, `src.market_data`, `src.aggregation`, `src.logging`.
-   **Logging:** All application logging is handled through `src.logging.get_logger`.
-   **Session State:** Streamlit's `st.session_state` is used to persist aggregated data across reruns.
