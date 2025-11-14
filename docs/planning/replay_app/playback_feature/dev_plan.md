# Playback Feature Development Plan

## Objective

Implement a playback feature for intraday charts in the Streamlit application. The feature should allow users to visualize price development over time by incrementing the chart in 5-second intervals. Playback speeds of 1x, 5x, and 15x should be supported, with increments occurring every second.

## Approaches

### Approach 1: Client-side JavaScript/Streamlit Custom Component

*   **Description:** This approach involves sending the entire intraday 5s dataset to the Streamlit frontend. A custom Streamlit component or direct JavaScript within `st.components.v1.html` would then handle the playback logic. It would update the Plotly chart by progressively adding 5-second bars based on the selected speed. The Python backend would primarily serve the initial data, and the animation would run entirely in the user's browser.

*   **Pros:**
    *   Potentially smoother animation as data is already client-side, reducing network latency during playback.
    *   Reduces server load significantly after the initial data fetch, as the server is not constantly re-rendering.
    *   Offers more granular control over animation details and interactivity using JavaScript.
    *   Can provide a more responsive user experience during playback.

*   **Cons:**
    *   Requires knowledge of JavaScript, Plotly.js, and potentially Streamlit custom component development, increasing complexity.
    *   Large datasets might lead to initial loading delays or performance issues in the browser, especially on less powerful client machines.
    *   State management and communication between the Python backend and JavaScript frontend can be challenging to implement and debug.
    *   Debugging client-side animation logic can be more involved than pure Python.

### Approach 2: Server-side Streamlit State Management with `st.empty()` and `time.sleep()`

*   **Description:** The Streamlit application would maintain the current playback state (e.g., current timestamp, playback speed, current index of data to display) in `st.session_state`. A loop on the server-side would progressively update the displayed chart. In each iteration, it would render a new Plotly figure with additional 5-second bars, using `st.empty()` to replace the previous chart and `time.sleep()` to control the playback speed. User controls (play, pause, speed) would trigger updates to the session state, which the loop would react to.

*   **Pros:**
    *   Pure Python implementation, leveraging existing Streamlit knowledge and ecosystem.
    *   Simpler to implement for basic playback functionality without needing to delve into frontend technologies.
    *   No need for custom components or external JavaScript, keeping the codebase unified.
    *   Easier to debug as all logic resides on the server.

*   **Cons:**
    *   Can be less performant for very fast playback speeds or large datasets due to repeated re-rendering of the entire chart and network round-trips for each frame.
    *   `time.sleep()` blocks the Streamlit thread, making the application unresponsive to other user interactions (e.g., changing speed, pausing) during playback. This can lead to a poor user experience.
    *   Frequent re-renders can consume more server resources.
    *   The UI might appear "choppy" or laggy, especially over slower network connections.

### Approach 3: Server-side Data Generation with Streamlit's `st.rerun()` and Query Parameters (or Callback-driven)

*   **Description:** This approach aims to mitigate the blocking issue of `time.sleep()` while remaining server-side. Instead of a continuous loop, the server would generate a single "frame" of the playback (i.e., the chart up to a certain timestamp). Playback speed would be controlled by the client sending requests (e.g., via a button click, a JavaScript timer that triggers `st.rerun()` with updated query parameters, or Streamlit's own callback mechanisms). The server would then render the next frame based on the updated state or query parameters. This could involve a "next frame" button or a more sophisticated client-side timer that periodically updates a session state variable or query parameter.

*   **Pros:**
    *   Avoids blocking the Streamlit thread with `time.sleep()`, leading to a more responsive UI during playback.
    *   Leverages Streamlit's native rerun mechanism, which is designed for reactive updates.
    *   Still primarily Python-based, though some client-side scripting might be needed to trigger reruns at intervals.
    *   Better resource management on the server compared to a constantly sleeping thread.

*   **Cons:**
    *   Requires more complex client-side logic to trigger reruns at specific intervals if a smooth, automatic playback is desired (e.g., using `st.script_runner.RerunData.from_query_params` or similar advanced techniques).
    *   Might still involve frequent server-side re-rendering, impacting performance for very fast speeds, though potentially less so than Approach 2.
    *   Managing the playback state and ensuring smooth transitions across reruns can be tricky.
    *   The "every second" increment might be harder to precisely control without a dedicated client-side timer.

---
**Revised Recommendation:**

Based on the updated user requirements for smooth rewind, fast forward, the ability to jump to different times using a slider, and the critical need to avoid waiting for the chart to reload every time, **Approach 1: Client-side JavaScript/Streamlit Custom Component** is the most appropriate choice.

While this approach introduces more complexity due to the need for JavaScript and potentially Streamlit custom component development, it is the only one that can effectively meet the demands for:
*   **Instantaneous updates:** Once the data is loaded to the client, all playback, rewind, fast-forward, and jump operations can be handled client-side without server interaction, ensuring a highly responsive user experience.
*   **Smooth animation:** Client-side control allows for fine-grained manipulation of chart updates, leading to smoother visual playback.
*   **Efficient slider interaction:** A slider can directly control the visible data range on the client, providing immediate feedback without server round-trips.

The previous recommendation (Approach 2) would lead to a blocked UI and significant delays for each update, directly contradicting the new requirements. Approach 3, while better, would still involve server-side re-renders for each frame, which would not be fast enough for truly smooth and interactive control.

Therefore, for the initial implementation, we will proceed with **Approach 1**.
