# scripts/validate_market_data.py

import os
import sys
from datetime import date, timedelta

# Add the project root to the Python path to allow imports from `src`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.market_data.collector import fetch_market_data

def validate_data():
    """
    Runs a validation test on the fetch_market_data function.
    """
    # --- Configuration ---
    # Using a highly liquid symbol like SPY is a good test case.
    SYMBOL_TO_TEST = "SPY"
    
    # Use a recent weekday for the trade date.
    # This logic finds the most recent weekday (not Saturday or Sunday).
    trade_date = date.today()
    while trade_date.weekday() >= 5: # 5 for Saturday, 6 for Sunday
        trade_date -= timedelta(days=1)
    
    print("--- Market Data Validation Script ---")
    print(f"Requesting data for symbol: {SYMBOL_TO_TEST}")
    print(f"Using trade date: {trade_date.strftime('%Y-%m-%d')}")
    print("\nNOTE: This script requires a running TWS/Gateway instance and a network connection.")
    print("An error or empty dataframes may indicate a connection issue.\n")

    # --- Fetch Data ---
    market_data = fetch_market_data(
        symbol=SYMBOL_TO_TEST,
        trade_date=trade_date
        # Using default connection params: localhost:7496, client_id=1
    )

    # --- Validation ---
    print("\n--- Validation Results ---")

    # Check for presence of keys
    if "daily" not in market_data or "intraday_5s" not in market_data:
        print("FAIL: The returned dictionary is missing 'daily' or 'intraday_5s' keys.")
        return

    df_daily = market_data["daily"]
    df_intraday = market_data["intraday_5s"]

    # Validate Daily DataFrame
    print("\n[Daily Data Validation]")
    if not df_daily.empty:
        print(f"PASS: Daily DataFrame is not empty. Shape: {df_daily.shape}")
        print(f"Date Range: {df_daily.index.min()} to {df_daily.index.max()}")
        print("Head:")
        print(df_daily.head(3))
        print("Tail:")
        print(df_daily.tail(3))
    else:
        print("WARN: Daily DataFrame is empty. Could be a connection issue or no data available.")

    # Validate Intraday DataFrame
    print("\n[Intraday 5s Data Validation]")
    if not df_intraday.empty:
        print(f"PASS: Intraday DataFrame is not empty. Shape: {df_intraday.shape}")
        print(f"Time Range: {df_intraday.index.min()} to {df_intraday.index.max()}")
        print("Head:")
        print(df_intraday.head(3))
        print("Tail:")
        print(df_intraday.tail(3))
    else:
        print("WARN: Intraday DataFrame is empty. Could be a connection issue or no data available.")
    
    print("\n--- Validation Complete ---")


if __name__ == "__main__":
    validate_data()
