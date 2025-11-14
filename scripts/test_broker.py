# scripts/test_broker.py

import sys
import os
from datetime import datetime
import pytz

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker.connection import get_historical_data

def demonstrate_broker():
    """
    Demonstrates the broker module, now with pagination.

    This script will attempt to connect to a running TWS or IB Gateway instance
    and download historical data over a multi-month period.
    """
    print("--- Broker Module Demonstration (with Pagination) ---")
    print("This script will attempt to download 3 months of daily data for the symbol 'CLIK'.")
    print("Please ensure your TWS or IB Gateway is running and configured for API connections on port 7496.")
    print("-" * 55)

    try:
        # Define the parameters for the data request using the test case
        symbol = "CLIK"
        sec_type = "STK"
        exchange = "SMART"
        currency = "USD"
        
        # Define a timezone-aware date range for the multi-month request
        utc = pytz.utc
        start_date = datetime(2025, 7, 27, 0, 0, 0, tzinfo=utc)
        end_date = datetime(2025, 10, 26, 23, 59, 59, tzinfo=utc)

        bar_size = "DAILY"

        # Call the function from the broker module
        historical_data_df = get_historical_data(
            symbol=symbol,
            sec_type=sec_type,
            exchange=exchange,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            bar_size=bar_size,
            use_rth=False,
            port=7496,
            client_id=102 # Use a unique client ID
        )

        if not historical_data_df.empty:
            print(f"\nSuccessfully retrieved {len(historical_data_df)} bars of historical data.")
            print("Data from the beginning of the date range:")
            print(historical_data_df.head())
            print("\nData from the end of the date range:")
            print(historical_data_df.tail())
        else:
            print("\nNo historical data was returned. This could be due to several reasons:")
            print("- The symbol 'CLIK' may not be available on your account.")
            print("- No data exists for the requested date range.")
            print("- Check the 'logs/broker.log' file for specific API error messages.")

    except Exception as e:
        print(f"\nAn error occurred during the demonstration: {e}")
        print("Please check the logs in 'logs/broker.log' for more details.")

if __name__ == "__main__":
    demonstrate_broker()
