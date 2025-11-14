# Development Plan: Market Data Collector Module

This document outlines the development phases and tasks required to implement the Market Data Collector module.

## Phase 1: Foundation & Setup

**Objective:** Prepare the project structure, understand the broker service interface, and set up configuration.

-   **Task 1.1: Understand Broker Service Data Interface**
    -   **Description**: Review the `src.broker.connection.get_historical_data` function to understand its parameters, expected inputs (e.g., timezone-aware datetimes), and output format. Identify any specific requirements for `symbol`, `sec_type`, `exchange`, `currency`.
    -   **Outcome**: Clear understanding of how to call `get_historical_data` for both 5-second and daily data.

-   **Task 1.2: Create Module Structure**
    -   **Description**: Create the necessary directory and files for the new module.
    -   **Actions**:
        -   Create `src/market_data/`.
        -   Create `src/market_data/__init__.py`.
        -   Create `src/market_data/collector.py` which will contain the module's logic.

-   **Task 1.3: Set Up Configuration**
    -   **Description**: Add mechanisms to securely store and access TWS connection parameters (host, port, client ID) if not already handled by the `broker` service.
    -   **Actions**: Update existing configuration files or create a new method to load credentials without hardcoding them.

## Phase 2: Core Feature Implementation

**Objective:** Implement the functions to fetch the required datasets by wrapping the `broker` service.

-   **Task 2.1: Implement Daily Data Wrapper**
    -   **Description**: Create a function in `collector.py` that calculates the required daily date range (last 45 days to yesterday) and calls `src.broker.connection.get_historical_data` with the appropriate parameters (`bar_size="DAILY"`).
    -   **Actions**:
        -   Implement date calculation logic.
        -   Map `market_data` inputs to `broker` service parameters (e.g., `symbol`, `sec_type`, `exchange`, `currency`).
        -   Process the `pandas.DataFrame` returned by `get_historical_data` to ensure it matches the `market_data` module's output requirements (e.g., column selection).

-   **Task 2.2: Implement Intraday Data Wrapper**
    -   **Description**: Create a function in `collector.py` that prepares the `trade_date` and time range (09:00-13:00 UK) for the `broker` service and calls `src.broker.connection.get_historical_data` with `bar_size="5 secs"`.
    -   **Actions**:
        -   Handle timezone conversions correctly for the start and end times.
        -   Map `market_data` inputs to `broker` service parameters.
        -   Process the `pandas.DataFrame` returned by `get_historical_data` to ensure it matches the `market_data` module's output requirements.

-   **Task 2.3: Implement Main Orchestrator Function**
    -   **Description**: Create the main public function `fetch_market_data(symbol, trade_date)` that calls the daily and intraday wrapper functions and returns the data in the specified dictionary format.

## Phase 3: Testing & Validation

**Objective:** Ensure the module is reliable, robust, and correct.

-   **Task 3.1: Set Up Test Environment**
    -   **Description**: Create test files and set up mocking for the `src.broker.connection.get_historical_data` function. Real TWS API calls should not be made during tests.
    -   **Actions**:
        -   Create `tests/market_data/test_collector.py`.
        -   Use `pytest-mock` or Python's `unittest.mock` to create fixtures that simulate responses from `get_historical_data`.

-   **Task 3.2: Write Unit Tests**
    -   **Description**: Implement the tests defined in `testing.md`.
    -   **Actions**:
        -   Test date and time range calculations.
        -   Test that the wrapper functions correctly call `get_historical_data` with the expected parameters.
        -   Test data processing and column selection from the `broker` service's output.
        -   Test the main orchestrator function's output structure.
        -   Test all error handling scenarios, including errors propagated from the `broker` service.

## Phase 4: Integration & Finalization

**Objective:** Integrate the module into the broader application and add final touches.

-   **Task 4.1: Integrate with Application**
    -   **Description**: Update any upstream services or scripts that will consume this module to call `fetch_market_data`.

-   **Task 4.2: Add Logging**
    -   **Description**: Integrate with the project's existing logging system to record important information, such as calls made to the `broker` service, data fetched, and any errors encountered.

-   **Task 4.3: Documentation**
    -   **Description**: Add comprehensive docstrings to all new functions and classes, explaining their purpose, parameters, and return values.
    -   **Actions**: Update the main `README.md` if the module's usage needs to be documented for users.
