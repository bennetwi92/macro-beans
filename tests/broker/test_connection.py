import pytest
import pandas as pd
from datetime import datetime
import pytz
import threading
import time

from src.broker.connection import (
    get_historical_data,
    ContractNotFoundError,
    ConnectionTimeoutError
)

# A simplified mock client. The run() method does nothing, and the background
# thread will start and exit immediately. This is stable for testing the main thread's logic.
class SimpleMockIBClient:
    def __init__(self):
        self.nextValidOrderId = 1
        self.error_code = None
        self.error_messages = []
        self.data = []
        self.request_event = threading.Event()
        self.req_id_map = {}
        self.call_count = 0
        self._is_connected = False

    def connect(self, *args, **kwargs): self._is_connected = True
    def run(self): pass
    def disconnect(self): self._is_connected = False
    def isConnected(self): return self._is_connected
    def reqHistoricalData(self, *args, **kwargs): self.request_event.set()

@pytest.fixture
def test_params():
    """Provides a standard set of parameters for test functions."""
    utc = pytz.utc
    start_date = datetime(2025, 10, 25, 0, 0, 0, tzinfo=utc)
    end_date = datetime(2025, 10, 26, 23, 59, 59, tzinfo=utc)
    return {
        "symbol": "TEST", "sec_type": "STK", "exchange": "SMART", "currency": "USD",
        "start_date": start_date, "end_date": end_date, "bar_size": "DAILY",
    }

@pytest.mark.timeout(15) # Add a pytest timeout to prevent indefinite hangs
def test_connection_timeout(monkeypatch, test_params):
    """Test that a ConnectionTimeoutError is raised. This test will take ~10s."""
    class MockTimeoutClient(SimpleMockIBClient):
        def __init__(self):
            super().__init__()
            self.nextValidOrderId = -1

    monkeypatch.setattr('src.broker.connection.IBClient', MockTimeoutClient)
    
    with pytest.raises(ConnectionTimeoutError):
        get_historical_data(**test_params)

def test_contract_not_found_error(monkeypatch, test_params):
    """Test that ContractNotFoundError is raised for error code 200."""
    class MockErrorClient(SimpleMockIBClient):
        def reqHistoricalData(self, *args, **kwargs):
            self.error_code = 200
            self.error_messages.append("No security definition has been found")
            self.request_event.set()

    monkeypatch.setattr('src.broker.connection.IBClient', MockErrorClient)
    with pytest.raises(ContractNotFoundError):
        get_historical_data(**test_params)

def test_successful_request_terminates(monkeypatch, test_params):
    """Test a successful data retrieval and that the pagination loop terminates correctly."""
    mock_bar = {"date": datetime(2025, 10, 26), "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000, "average": 102.5}

    class MockSuccessClient(SimpleMockIBClient):
        def reqHistoricalData(self, *args, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                self.data = [mock_bar]
            else:
                self.data = []
            self.request_event.set()

    monkeypatch.setattr('src.broker.connection.IBClient', MockSuccessClient)
    df = get_historical_data(**test_params)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.index[0].date() == datetime(2025, 10, 26).date()

def test_timezone_handling(monkeypatch, test_params):
    """Test that the output DataFrame has the correct timezone."""
    mock_bar = {"date": datetime(2025, 10, 26, 10, 0, 0), "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000, "average": 102.5}
    
    class MockTimezoneClient(SimpleMockIBClient):
        def reqHistoricalData(self, *args, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                self.data = [mock_bar]
            else:
                self.data = []
            self.request_event.set()

    monkeypatch.setattr('src.broker.connection.IBClient', MockTimezoneClient)
    test_params['timezone'] = 'America/New_York'
    df = get_historical_data(**test_params)

    assert str(df.index.tz) == 'America/New_York'
    assert df.index[0].hour == 6
