import pandas as pd
from src.market_data.collector import fetch_market_data
from src.aggregation.aggregator import aggregate_data
from datetime import date
from loguru import logger

# Configure logger for the script
logger.add("logs/validate_aggregation.log", rotation="10 MB", level="INFO")

def validate_aggregation_script():
    """
    Fetches market data and then aggregates it, printing the head of each DataFrame
    for visual inspection.
    """
    symbol = "SPY"
    trade_date = date(2025, 11, 12) # Use a future date for consistency with example

    logger.info(f"Fetching market data for {symbol} on {trade_date}...")
    try:
        market_data = fetch_market_data(symbol=symbol, trade_date=trade_date)
        if market_data["intraday_5s"].empty:
            logger.warning("No intraday 5s data fetched. Cannot proceed with aggregation validation.")
            return
        if market_data["daily"].empty:
            logger.warning("No daily data fetched.")

        logger.info("Market data fetched successfully. Aggregating data...")
        aggregated_data = aggregate_data(market_data)

        logger.info("\n--- Original Intraday 5s Data (Head) ---")
        logger.info(aggregated_data['intraday_5s'].head())

        logger.info("\n--- Aggregated Intraday 1m Data (Head) ---")
        logger.info(aggregated_data['intraday_1m'].head())

        logger.info("\n--- Aggregated Intraday 5m Data (Head) ---")
        logger.info(aggregated_data['intraday_5m'].head())

        if 'daily' in aggregated_data and not aggregated_data['daily'].empty:
            logger.info("\n--- Daily Data (Head) ---")
            logger.info(aggregated_data['daily'].head())
        else:
            logger.info("\n--- No Daily Data to Display ---")

        logger.info("Aggregation validation script finished.")

    except Exception as e:
        logger.error(f"An error occurred during aggregation validation: {e}")

if __name__ == "__main__":
    validate_aggregation_script()
