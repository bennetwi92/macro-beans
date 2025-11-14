# Streamlit Replay App Development Plan

## Phase 1: Scaffolding & Setup

1.  **Create Directory Structure:**
    -   `src/replay/`
    -   `tests/replay/`

2.  **Create Initial Files:**
    -   `src/replay/__init__.py`
    -   `src/replay/app.py` (main Streamlit application)
    -   `src/replay/GEMINI.md` (documentation for agents)
    -   `tests/replay/__init__.py`
    -   `tests/replay/test_app.py` (unit tests for any isolatable logic)

3.  **Update Environment:**
    -   Ensure `streamlit` and `plotly` (or chosen charting library) are listed in `environment.yml`.

## Phase 2: Basic Streamlit UI and Data Input

1.  **Initialize Streamlit App:**
    -   In `src/replay/app.py`, set up basic Streamlit page configuration (`st.set_page_config`).
    -   Add a title to the app (`st.title`).
    -   Get logger: `log = get_logger("replay_app")`.

2.  **Implement Input Fields:**
    -   Add `st.text_input` for `symbol`.
    -   Add `st.date_input` for `trade_date`.
    -   Add `st.button` for "Load Data".

3.  **Basic Data Loading Logic (Placeholder):**
    -   When the "Load Data" button is clicked:
        -   Display a loading spinner (`st.spinner`).
        -   Log the inputs.
        -   For now, just print the inputs to the console or display them on the app to confirm input capture.

## Phase 3: Integrate Data Fetching and Aggregation

1.  **Import Services:**
    -   Import `fetch_market_data` from `src.market_data.collector`.
    -   Import `aggregate_data` from `src.aggregation.aggregator`.

2.  **Implement Data Pipeline:**
    -   Inside the "Load Data" button logic:
        -   Validate `symbol` and `trade_date` inputs (e.g., not empty). Display `st.error` if invalid.
        -   Call `fetch_market_data` with user inputs.
        -   Handle `BrokerError` (e.g., `ContractNotFoundError`, `ConnectionTimeoutError`) and display `st.error`.
        -   Check if `intraday_5s` DataFrame is empty. If so, display `st.warning` and return.
        -   Call `aggregate_data` with the fetched data.
        -   Store the aggregated data in Streamlit's session state (`st.session_state`) to persist across reruns.

## Phase 4: Charting and Display

1.  **Chart Generation Function:**
    -   Create a helper function (e.g., `create_candlestick_chart(df, title, show_vwap=False)`) that takes a DataFrame, a title, and a boolean `show_vwap` flag, and returns a Plotly candlestick figure.
    -   This function should use `plotly.graph_objects` to create the chart.
    -   Include `open`, `high`, `low`, `close` and `volume` in the chart.
    -   If `show_vwap` is True, add a line trace for VWAP.

2.  **Display Charts:**
    -   Retrieve the aggregated data from `st.session_state`.
    -   Use `st.columns` or `st.container` to create a 2x2 grid layout.
    -   In each grid cell, call the `create_candlestick_chart` function with the appropriate DataFrame and display it using `st.plotly_chart`.
    -   **VWAP Display:** Call `create_candlestick_chart` with `show_vwap=True` for `intraday_5s`, `intraday_1m`, and `intraday_5m` charts. Call it with `show_vwap=False` for the `daily` chart.
    -   Add titles to each chart indicating the timeframe.

## Phase 5: Error Handling and User Feedback

1.  **Refine Error Messages:**
    -   Ensure all error and warning messages are user-friendly and informative.
    -   Use `st.info`, `st.warning`, `st.error` appropriately.

2.  **Loading State:**
    -   Ensure the `st.spinner` is correctly used during data fetching and aggregation.

3.  **Initial State:**
    -   Ensure the app starts in a clean state with input fields and no charts displayed until data is loaded.

## Phase 6: Testing and Refinement

1.  **Manual Testing:**
    -   Follow the `test_plan.md` for comprehensive manual testing of the UI and end-to-end functionality.

2.  **Unit Tests:**
    -   If any new isolatable functions are created, write corresponding unit tests in `tests/replay/test_app.py`.

3.  **Code Review:**
    -   Review code for PEP 8 compliance, readability, and adherence to project conventions.

4.  **Performance Optimization:**
    -   Apply Streamlit caching (`@st.cache_data`, `@st.cache_resource`) to `fetch_market_data` and `aggregate_data` calls to optimize performance for repeated requests with the same parameters.
