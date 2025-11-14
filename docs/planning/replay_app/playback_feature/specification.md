# Playback Feature Specification

## Feature: Intraday Chart Playback

This document details the implementation plan for the intraday chart playback feature, following **Approach 1: Client-side JavaScript/Streamlit Custom Component** as the revised recommendation in `dev_plan.md`. This approach is chosen to meet the requirements for smooth rewind, fast forward, jumping to different times using a slider, and avoiding chart reloads.

## Detailed Implementation Plan

### 1. Streamlit Custom Component Setup

*   **Component Structure:** A new Streamlit custom component will be created. This typically involves:
    *   A Python wrapper (`src/replay/components/playback_chart.py`) that defines the component's interface and renders the frontend.
    *   A frontend directory (e.g., `frontend/`) containing the JavaScript/TypeScript code for the component. This will likely include `index.html` (or similar entry point), `src/PlaybackChart.js` (or `.tsx`), and `package.json` for frontend dependencies.
*   **Data Transfer:** The Python backend will pass the full intraday 5-second data (and potentially other relevant data like daily bars for context) to this custom component. The data should be serialized into a JSON-compatible format (e.g., `df.to_json(orient='records')` or `df.to_dict('records')`).
*   **Initial State:** The component will also receive initial playback settings (e.g., default speed, initial display range) from the Python backend.

### 2. Frontend (JavaScript/TypeScript) Implementation

The core logic for playback, interaction, and chart rendering will reside within the custom component's frontend code.

*   **Data Storage:**
    *   The component's JavaScript will receive and store the complete intraday 5-second data locally. This data will be the single source of truth for all playback operations.
*   **Plotly.js Integration:**
    *   Plotly.js will be used directly in the frontend to render and update the candlestick chart. This allows for highly efficient client-side chart manipulation.
*   **UI Elements:**
    *   **Playback Controls:** Implement "Play", "Pause", "Rewind", "Fast Forward", and "Reset" buttons. These will trigger JavaScript functions to control the playback state.
    *   **Speed Selector:** A set of radio buttons or a dropdown to select playback speeds (1x, 5x, 15x). This will adjust the interval at which new bars are added during playback.
    *   **Time Slider:** A slider component (e.g., HTML range input or a more sophisticated UI library component) that allows users to jump to any specific timestamp within the loaded intraday data.
    *   **Current Playback Timestamp Display:** A text element to show the timestamp of the last 5-second bar currently displayed on the chart.
*   **Playback Logic:**
    *   **Animation Loop:** Implement a JavaScript `setInterval` or `requestAnimationFrame` loop to drive the animation. `requestAnimationFrame` is generally preferred for smoother animations.
    *   **Progressive Chart Update:** Based on the selected playback speed, the loop will progressively update the Plotly chart by adding new 5-second bars to the displayed data.
    *   **Play/Pause/Stop:** Manage the state of the animation loop (start, stop, clear interval).
    *   **Rewind/Fast Forward:** Adjust the current data index and the direction/speed of the playback. Rewind would decrement the index, fast forward would increment it at a higher rate.
    *   **Slider Interaction:** When the slider's value changes, directly update the displayed chart to show data up to the corresponding timestamp without involving the Python backend.
*   **Communication with Streamlit (if necessary):**
    *   If any state needs to be sent back to the Python backend (e.g., for logging the user's interaction, saving a specific playback point, or triggering other server-side processes), the `Streamlit.setComponentValue` function will be used. This should be minimized to keep the interaction client-side.

### 3. Python Backend (`src/replay/app.py`) Integration

The Python application will primarily act as a data provider and a renderer for the custom component.

*   **Data Preparation:**
    *   The existing `fetch_market_data` and `aggregate_data` functions will be used to retrieve and process the intraday 5-second data.
*   **Data Serialization:**
    *   The `intraday_5s` DataFrame will be converted into a JSON-serializable format (e.g., `df.to_json(orient='records', date_format='iso')`) before being passed to the custom component. This ensures that datetime objects are correctly handled.
*   **Component Rendering:**
    *   The `playback_chart` component (from `src/replay/components/playback_chart.py`) will be instantiated in `app.py`, passing the serialized data and any initial configuration as arguments.
*   **Handle Component Output (Optional):**
    *   If the custom component sends data back to Streamlit, `app.py` will receive and process this data.

### 4. Error Handling and Edge Cases

*   **Empty Data:** If `intraday_5s` data is empty after fetching, the custom component should be rendered with an appropriate message, and playback controls should be disabled.
*   **Data Serialization/Deserialization:** Ensure robust handling of data conversion between pandas DataFrames and JSON in both Python and JavaScript.
*   **Performance:** Monitor client-side performance, especially with very large datasets, and optimize JavaScript rendering if necessary.

### 5. Logging

*   Utilize `src.logging.get_logger("replay")` for all Python-side logging.
*   Frontend JavaScript can use `console.log` for debugging, but critical events might be sent back to Python for persistent logging if needed.

## Next Steps

1.  Create the directory structure for the custom component (`src/replay/components/` and `frontend/`).
2.  Develop the basic Streamlit custom component boilerplate.
3.  Implement the data serialization in `src/replay/app.py` and pass it to the component.
4.  Develop the frontend JavaScript/TypeScript for chart rendering, UI controls, and playback logic using Plotly.js.
5.  Integrate the custom component into `src/replay/app.py`.
6.  Add necessary error handling and logging.
