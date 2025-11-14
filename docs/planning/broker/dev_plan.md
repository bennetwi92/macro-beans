# Broker Module Development Plan

This plan outlines the development steps for creating the TWS API broker connection module, based on the provided specification.

## Phase 1: Core Connection and Data Request

1.  **Create Module Structure:**
    - Create a new directory `src/broker`.
    - Add an `__init__.py` file.
    - Create the main module file, e.g., `src/broker/connection.py`.

2.  **Implement the TWS Connection Wrapper:**
    - In `connection.py`, create a class that inherits from `ibapi.EClient` and `ibapi.EWrapper`.
    - Implement the basic connection logic (`connect`, `disconnect`).
    - Implement the `error` callback to log errors from TWS.

3.  **Implement Initial `get_historical_data` function:**
    - Create the function signature as defined in the specification.
    - Add the logic to construct the `Contract` object from the simplified parameters.
    - Implement a single, non-paginated call to `reqHistoricalData`.
    - Implement the `historicalData` callback in the wrapper to receive and store the data.
    - Return the data as a pandas DataFrame.

## Phase 2: Pagination and Data Handling

1.  **Implement Pagination Logic:**
    - Enhance `get_historical_data` to handle date ranges that exceed the TWS API's single-request limit.
    - Add a loop that makes sequential calls to `reqHistoricalData`, adjusting the `endDateTime` for each iteration until the `start_date` is reached.
    - Stitch the results from all requests together into a single DataFrame.

2.  **Implement Time Zone Handling:**
    - Ensure all `datetime` operations are timezone-aware.
    - Convert user-provided `start_date` and `end_date` to the appropriate format for the TWS API.
    - Localize the final DataFrame's index to the user-specified `timezone`.

## Phase 3: Error Handling and Logging

1.  **Integrate Logging Module:**
    - Add logging statements throughout the code, as specified in the `logging` section of the specification.
    - Ensure logs are written to `broker.log`.

2.  **Robust Error Handling:**
    - Enhance the `error` callback to handle specific, common TWS error codes (e.g., "No security definition has been found for the request").
    - Add `try...except` blocks to handle connection errors, timeouts, and other potential exceptions.
    - Raise clear, informative exceptions to the user when a request cannot be fulfilled.

## Phase 4: Finalization and Testing

1.  **Unit Testing:**
    - Develop unit tests for individual components (e.g., contract creation, time zone conversion).
    - Mock the TWS API connection to test the pagination logic and data handling in isolation.

2.  **Integration Testing:**
    - Write integration tests that connect to a paper trading TWS or Gateway instance.
    - Use the test cases defined in `testing.md` to validate the end-to-end functionality.

3.  **Code Review and Refinement:**
    - Review the code for clarity, efficiency, and adherence to the specification.
    - Add docstrings and comments where necessary.
