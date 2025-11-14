# Streamlit Replay App Specification

## 1. Purpose

The Streamlit Replay App will provide a user interface for practicing day trading by replaying historical market data. Users will be able to select a stock symbol and a trading date, load the corresponding data, and visualize it through candlestick charts at different aggregation levels.

## 2. User Interface (UI)

The application will consist of a single Streamlit page with the following components:

### 2.1 Input Section

-   **Symbol Entry Field:** A text input field for the user to enter a stock ticker symbol (e.g., "SPY", "AAPL").
-   **Date Entry Field:** A date input widget for the user to select a specific trading date.
-   **Load Button:** A button labeled "Load Data" that, when clicked, triggers the data fetching and aggregation process.

### 2.2 Data Display Section

-   **Loading Indicator:** A visual indicator (e.g., a spinner or message) displayed while data is being fetched and processed.
-   **Candlestick Chart Grid:** A 2x2 grid displaying four candlestick charts. Each chart will represent the same symbol and date but at different aggregation levels:
    -   Top-Left: 5-second intraday data
    -   Top-Right: 1-minute intraday data
    -   Bottom-Left: 5-minute intraday data
    -   Bottom-Right: Daily historical data (for context, showing the selected date within a broader daily trend)

## 3. Core Functionality

1.  **Input Handling:**
    -   Capture user input for `symbol` and `trade_date`.
    -   Validate inputs (e.g., ensure symbol is not empty, date is valid).
2.  **Data Fetching:**
    -   Upon "Load Data" button click, call `src.market_data.collector.fetch_market_data` using the provided `symbol` and `trade_date`.
    -   Handle potential errors during data fetching (e.g., `ContractNotFoundError`, `ConnectionTimeoutError`). Display appropriate error messages to the user.
3.  **Data Aggregation:**
    -   Pass the fetched market data (which includes 5-second and daily data) to `src.aggregation.aggregator.aggregate_data`. This will produce 1-minute and 5-minute aggregated data.
4.  **Chart Generation:**
    -   For each of the four dataframes (`intraday_5s`, `intraday_1m`, `intraday_5m`, `daily`), generate a candlestick chart.
    -   Use a suitable charting library (e.g., `plotly.graph_objects` or `mplfinance` if available and appropriate for Streamlit).
    -   Each chart should display `open`, `high`, `low`, `close` prices, and `volume`.
    -   **VWAP Display:** VWAP should be displayed on the `intraday_5s`, `intraday_1m`, and `intraday_5m` charts. VWAP should *not* be displayed on the `daily` chart.
    -   Ensure charts are properly labeled with their respective timeframes.
5.  **Error and Information Display:**
    -   Display user-friendly messages for successful data loading, errors, or when no data is found for the selected criteria.

## 4. Technical Considerations

-   **Dependencies:** `streamlit`, `pandas`, `plotly` (or similar charting library), `src.market_data`, `src.aggregation`, `src.logging`.
-   **Logging:** Use `src.logging.get_logger` for all application logging.
-   **Performance:** Data fetching and aggregation should be performed efficiently. Use Streamlit's caching mechanisms (`@st.cache_data`, `@st.cache_resource`) where appropriate to avoid re-running expensive computations.
-   **TWS/IB Gateway:** The application will rely on a running TWS or IB Gateway instance for data fetching.
-   **UI Layout:** Use Streamlit's layout features (e.g., `st.columns`, `st.container`) to arrange input fields and charts effectively.
