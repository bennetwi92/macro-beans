import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys

# Mock the entire streamlit module to prevent it from running during tests
@pytest.fixture(autouse=True)
def mock_streamlit_session_state():
    with patch('streamlit.session_state', new_callable=MagicMock) as mock_session_state:
        # Initialize only the session state variables directly used by on_slider_change
        mock_session_state.current_playback_index = 0
        mock_session_state.playback_active = True # Assume active before slider interaction
        mock_session_state.playback_slider = 0 # Initial slider value

        # Mock st.info and log.info as they are called by on_slider_change
        with patch('streamlit.info'), \
             patch('src.replay.app.log') as mock_log:
            yield mock_session_state, mock_log

def test_on_slider_change_updates_index_and_pauses_playback(mock_streamlit_session_state):
    mock_session_state, _ = mock_streamlit_session_state # Don't unpack mock_log here

    # Set initial state for the test
    mock_session_state.current_playback_index = 10
    mock_session_state.playback_active = True
    mock_session_state.playback_slider = 50 # Simulate user moving slider to index 50

    # Re-import the app module to ensure the latest on_slider_change is used
    if 'src.replay.app' in sys.modules:
        del sys.modules['src.replay.app']
    import src.replay.app
    
    # Patch the log object *after* the module has been imported
    with patch('src.replay.app.log') as mock_app_log:
        # Call the function directly
        src.replay.app.on_slider_change()

        assert mock_session_state.current_playback_index == 50
        assert mock_session_state.playback_active == False
        mock_app_log.info.assert_called_with("Jumped to index 50.")
