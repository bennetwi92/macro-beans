# scripts/test_broker_phase3.py

import sys
import os
from datetime import datetime
import pytz

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker.connection import get_historical_data, ContractNotFoundError, BrokerError

def demonstrate_phase3():
    """
    Demonstrates the Phase 3 implementation of the broker module,
    focusing on robust error handling.
    """
    print("--- Broker Module Phase 3 Demonstration (Error Handling) ---")
    print("Please ensure your TWS or IB Gateway is running and configured for API connections on port 7496.")
    print("-" * 60)

    # --- Test Case 1: Successful Request ---
    print("\n[1] Testing a successful request for 'CLIK'...")
    try:
        utc = pytz.utc
        start_date = datetime(2025, 10, 24, 0, 0, 0, tzinfo=utc)
        end_date = datetime(2025, 10, 24, 23, 59, 59, tzinfo=utc)

        data_df = get_historical_data(
            symbol="CLIK",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            start_date=start_date,
            end_date=end_date,
            bar_size="DAILY",
            client_id=103
        )
        if not data_df.empty:
            print("✅ Success! Retrieved data for CLIK:")
            print(data_df.head())
        else:
            print("⚠️ Warning: Request was successful but returned no data.")

    except BrokerError as e:
        print(f"❌ Failure! An unexpected broker error occurred: {e}")


    # --- Test Case 2: Unsuccessful Request (Invalid Symbol) ---
    print("\n[2] Testing an unsuccessful request for an invalid symbol 'XYZ_INVALID_XYZ'...")
    try:
        utc = pytz.utc
        start_date = datetime(2025, 10, 24, 0, 0, 0, tzinfo=utc)
        end_date = datetime(2025, 10, 24, 23, 59, 59, tzinfo=utc)

        get_historical_data(
            symbol="XYZ_INVALID_XYZ",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
            start_date=start_date,
            end_date=end_date,
            bar_size="DAILY",
            client_id=104
        )
    except ContractNotFoundError as e:
        print(f"✅ Success! Correctly caught the expected error: ContractNotFoundError.")
        print(f"   Error details: {e}")
    except BrokerError as e:
        print(f"❌ Failure! Caught a broker error, but not the expected ContractNotFoundError: {e}")
    except Exception as e:
        print(f"❌ Failure! Caught an unexpected generic error: {e}")


if __name__ == "__main__":
    demonstrate_phase3()
