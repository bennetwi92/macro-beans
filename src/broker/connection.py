import logging
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time
import threading

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.common import BarData

# --- Custom Exceptions ---
class BrokerError(Exception):
    """Base class for exceptions in this module."""
    pass

class ContractNotFoundError(BrokerError):
    """Raised when the requested contract cannot be found."""
    pass

class DataRequestError(BrokerError):
    """Raised for general data request failures."""
    pass

class ConnectionTimeoutError(BrokerError):
    """Raised for connection timeouts."""
    pass

# --- Logging Configuration ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a file handler if not already present
if not logger.handlers:
    log_file = "logs/broker.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


class IBClient(EWrapper, EClient):
    """
    A custom client for the TWS API that handles callbacks for historical data.
    Inherits from both EWrapper (to handle incoming messages) and EClient (to send requests).
    """
    def __init__(self):
        EClient.__init__(self, self)
        self.data = []
        self.nextValidOrderId = -1
        self.error_code = None
        self.error_messages = []
        self.req_id_map = {}
        self.request_event = threading.Event()

    def nextValidId(self, orderId: int):
        """Receives the next valid order ID from TWS upon connection."""
        super().nextValidId(orderId)
        self.nextValidOrderId = orderId
        logger.info(f"Next valid order ID: {orderId}")

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson=""):
        """Handles errors received from TWS."""
        super().error(reqId, errorCode, errorString)
        # Ignore informational messages (codes 2100-2199)
        if 2100 <= errorCode < 2200:
            logger.info(f"TWS Info: {errorString}")
            return

        self.error_code = errorCode
        error_msg = f"TWS Error. Request ID: {reqId}, Code: {errorCode}, Message: {errorString}"
        self.error_messages.append(error_msg)
        logger.error(error_msg)
        # Signal that the request is complete (with an error) to unblock the main thread
        self.request_event.set()

    def historicalData(self, reqId: int, bar: BarData):
        """Callback that receives each historical bar."""
        self.data.append({
            "date": datetime.strptime(bar.date, "%Y%m%d" if len(bar.date) == 8 else "%Y%m%d  %H:%M:%S"),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "vwap": bar.average,
        })

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """Callback that signifies the end of a historical data request."""
        super().historicalDataEnd(reqId, start, end)
        logger.info(f"HistoricalDataEnd. Request ID: {reqId} from {start} to {end}")
        # Signal that data reception is complete for this request
        self.request_event.set()

def get_historical_data(
    symbol: str,
    sec_type: str,
    exchange: str,
    currency: str,
    start_date: datetime,
    end_date: datetime,
    bar_size: str,
    use_rth: bool = False,
    host: str = "127.0.0.1",
    port: int = 7496,
    client_id: int = 1,
    timezone: str = "UTC"
) -> pd.DataFrame:
    if not start_date.tzinfo:
        raise ValueError("start_date must be timezone-aware.")
    if not end_date.tzinfo:
        raise ValueError("end_date must be timezone-aware.")

    client = IBClient()
    try:
        logger.info(f"Connecting to TWS on {host}:{port} with client ID {client_id}...")
        client.connect(host, port, client_id)

        api_thread = threading.Thread(target=client.run, daemon=True)
        api_thread.start()

        connection_timeout = 10
        start_time = time.time()
        while client.nextValidOrderId == -1:
            time.sleep(0.1)
            if time.time() - start_time > connection_timeout:
                raise ConnectionTimeoutError("TWS connection timeout. Check if TWS/Gateway is running and API is enabled.")

        contract = Contract()
        contract.symbol = symbol
        contract.secType = sec_type
        contract.exchange = exchange
        contract.currency = currency
        logger.info(f"Constructed contract: {symbol} {sec_type} on {exchange} in {currency}")

        if bar_size == "DAILY":
            bar_size_setting = "1 day"
            duration_str = "1 M"
        elif bar_size == "5 secs":
            bar_size_setting = "5 secs"
            duration_str = "1800 S"
        else:
            raise ValueError("bar_size must be 'DAILY' or '5 secs'")

        all_data = []
        current_end_date = end_date

        # --- Pagination Loop ---
        # Start from the user's end_date and work backwards in time until we reach the start_date.
        while current_end_date > start_date:
            # Reset state for the new request
            client.request_event.clear()
            client.data = []
            client.error_code = None
            client.error_messages = []

            tws_end_date_str = current_end_date.astimezone(pytz.utc).strftime("%Y%m%d %H:%M:%S UTC")
            req_id = client.nextValidOrderId
            client.req_id_map[req_id] = f"{symbol}-{sec_type}-{exchange}"
            
            logger.info(f"Requesting data page ending on {tws_end_date_str} for duration {duration_str}")
            client.reqHistoricalData(
                reqId=req_id, contract=contract, endDateTime=tws_end_date_str,
                durationStr=duration_str, barSizeSetting=bar_size_setting,
                whatToShow="TRADES", useRTH=1 if use_rth else 0, formatDate=1,
                keepUpToDate=False, chartOptions=[]
            )

            # Wait for the request to complete (or time out)
            request_timeout = 30
            if not client.request_event.wait(timeout=request_timeout):
                raise DataRequestError("TWS data request timeout.")

            # Check if the request resulted in an error
            if client.error_code:
                if client.error_code == 200:
                    raise ContractNotFoundError(f"No security definition found for the request: {client.error_messages}")
                else:
                    raise DataRequestError(f"An API error occurred: {client.error_messages}")

            # If TWS returns no data for a period, stop paginating.
            if not client.data:
                logger.info("No more data available for this period, ending pagination.")
                break

            all_data.extend(client.data)
            
            # Set the end date for the next request to be just before the first bar we received.
            first_bar_date = client.data[0]['date']
            current_end_date = pytz.utc.localize(first_bar_date) - timedelta(seconds=1)
            
            client.nextValidOrderId += 1
            time.sleep(0.1) # Small delay to avoid pacing violations

        if not all_data:
            logger.warning(f"No historical data was found for {symbol} in the entire date range.")
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.drop_duplicates(subset="date").set_index("date").sort_index()
        logger.info(f"Total {len(df)} unique bars collected.")

        df.index = df.index.tz_localize(pytz.utc)
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        target_timezone = pytz.timezone(timezone)
        df.index = df.index.tz_convert(target_timezone)

        logger.info(f"Successfully retrieved and processed {len(df)} bars for {symbol}.")
        return df
    finally:
        if client.isConnected():
            logger.info("Disconnecting from TWS.")
            client.disconnect()
