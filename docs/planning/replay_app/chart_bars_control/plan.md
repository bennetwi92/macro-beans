# Chart Bars Control Feature Plan

## 1. Specification

### 1.1 Feature Description
This feature introduces an integer entry field in the Streamlit replay application, allowing users to control the number of historical bars displayed on each chart. This ensures that users can focus on a relevant window of data rather than viewing the entire dataset, which can be overwhelming.

### 1.2 User Interface
-   **Location**: The integer entry field will be placed prominently in the Streamlit application's sidebar (`st.sidebar`).
-   **Label**: The field will be labeled "Number of Bars to Display" or similar.
-   **Default Value**: The default value for this field will be `45`.
-   **Input Type**: It will be an integer input field, preventing non-numeric entries.
-   **Range**: A reasonable minimum (e.g., 10) and maximum (e.g., 500) value should be enforced to prevent usability issues or excessive resource consumption.
-   **Update Mechanism**:
    -   **Option A (Automatic)**: The charts update dynamically as the user changes the value in the input field. This provides immediate feedback but might be resource-intensive for frequent changes.
    -   **Option B (Manual with Button)**: An "Update Charts" button will be placed next to the input field. Charts will only refresh when this button is clicked. This is less resource-intensive but requires an extra user action.
    -   **Decision**: For simplicity and to avoid potential performance issues with large datasets, **Option B (Manual with Button)** is preferred initially. The button will be labeled "Apply".

### 1.3 Functional Requirements
-   The input field must accept only integer values.
-   The value entered will determine the number of the most recent bars to display on all relevant charts within the application.
-   If the number of available bars is less than the specified `n`, all available bars should be displayed. This will be handled by slicing the data using `df.tail(min(n_bars, len(df)))`.
-   The application should handle invalid inputs gracefully (e.g., non-numeric, out-of-range values) by displaying an error message and reverting to the last valid value or the default.

## 2. Testing Plan

### 2.1 Unit Tests
-   **Input Validation**:
    -   Test that the input field correctly handles non-integer inputs (e.g., strings, floats).
    -   Test that the input field enforces minimum and maximum values.
-   **Default Value**:
    -   Verify that the field initializes with the default value of `45`.
-   **Chart Update Logic**:
    -   Mock the chart rendering function to ensure it receives the correct number of bars based on the input value after the "Apply" button is clicked.
    -   Test edge cases where the total number of available bars is less than the requested `n`, ensuring `min(n_bars, len(df))` logic is applied.

### 2.2 Integration Tests
-   **Streamlit UI Interaction**:
    -   Simulate user input into the number field and clicking the "Apply" button.
    -   Verify that the displayed charts visually update to show the correct number of bars.
-   **Persistence (within session)**:
    -   Verify that the value stored in `st.session_state` is correctly maintained across Streamlit reruns within the same user session.

### 2.3 Acceptance Criteria
-   The integer entry field is visible and functional in the Streamlit app.
-   The default value is `45`.
-   Entering a valid integer and clicking "Apply" correctly updates the number of bars on all charts.
-   Invalid inputs are handled gracefully without crashing the application.
-   The "Apply" button is present and triggers the chart update.

## 3. Development Plan

### 3.1 Task Breakdown

1.  **Modify `src/replay/app.py`**:
    *   Initialize `st.session_state['n_bars']` with `45` if it doesn't already exist.
    *   Add a `st.number_input` widget to the Streamlit sidebar (`st.sidebar`) for the "Number of Bars to Display".
    *   Set the default value to `st.session_state['n_bars']`, and define `min_value` (10) and `max_value` (500).
    *   Add a `st.button` widget labeled "Apply" next to the number input.
    *   Implement logic to update `st.session_state['n_bars']` with the new input value and trigger chart updates only when the "Apply" button is clicked.

2.  **Update Chart Rendering Logic**:
    *   Identify the existing chart rendering functions within `src/replay/app.py` (or related modules if charts are abstracted).
    *   Modify these functions to accept an `n_bars` parameter.
    *   Within the chart rendering, slice the data to display only the last `n_bars` (e.g., `df.tail(min(n_bars, len(df)))`).

3.  **Error Handling and Validation**:
    *   Add checks for `n_bars` to ensure it's a positive integer within the defined range.
    *   Display Streamlit warning/error messages for invalid inputs.

4.  **Testing**:
    *   Create or update `tests/replay/test_app.py` to include unit tests for the new input field and its interaction with the chart rendering logic.
    *   Focus on testing the default value, input validation, and the data slicing mechanism.

### 3.2 Estimated Time
-   **UI Implementation (Streamlit widgets)**: 1-2 hours
-   **Chart Logic Modification**: 2-3 hours (depending on existing chart complexity)
-   **Error Handling/Validation**: 1 hour
-   **Testing**: 2-3 hours
-   **Total**: 6-9 hours

### 3.3 Dependencies
-   `streamlit` library for UI components.
-   Existing chart rendering functions and data loading mechanisms in `src/replay/app.py`.

### 3.4 Open Questions / Considerations
-   Are there multiple charts that need to be updated, or just one? **All charts will be updated.**
-   What is the appropriate `min_value` and `max_value` for the number input? **The values 10 and 500 are appropriate.**
-   How will the `n_bars` parameter be passed down to the chart rendering functions? **The `n_bars` value will be stored in `st.session_state` and then passed as an argument to the chart rendering functions.**
