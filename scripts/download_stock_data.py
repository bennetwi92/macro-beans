"""
Stock Data Download and Caching Script
Downloads entire history for all stocks in the universe and caches to CSV files
Run this script periodically to refresh the data
"""

import yfinance as yf
import pandas as pd
import os
from datetime import datetime
import time

# Stock universe (same as scanner)
UNIVERSE = [
    'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'NVDA',
    'JPM', 'V', 'MA', 'BAC', 'WMT', 'PG', 'HD', 'DIS',
    'ADBE', 'CRM', 'NFLX', 'PYPL', 'INTC', 'CSCO', 'PFE',
    'AMD', 'ORCL', 'QCOM', 'TXN', 'AVGO', 'COST', 'NKE',
    # User requested additions
    'PLTR', 'HOOD',
    # Additional liquid stocks
    'COIN', 'SHOP', 'UBER', 'ABNB', 'SNOW',
    'SOFI', 'RBLX', 'NET', 'DDOG', 'CRWD', 'ZS',
    'MU', 'MRVL', 'KLAC', 'AMAT', 'LRCX',
    'CVX', 'XOM', 'COP', 'SLB', 'MPC'
]

DATA_DIR = 'data/stock_history'

def download_stock_history(symbol, data_dir=DATA_DIR):
    """Download entire history for a stock and save to CSV"""
    try:
        print(f"Downloading {symbol}...", end=" ")

        # Download all available data
        stock = yf.Ticker(symbol)
        data = stock.history(period="max")

        if len(data) == 0:
            print(f"❌ No data available")
            return False

        # Save to CSV
        filepath = os.path.join(data_dir, f"{symbol}.csv")
        data.to_csv(filepath)

        # Get date range
        start_date = data.index[0].strftime('%Y-%m-%d')
        end_date = data.index[-1].strftime('%Y-%m-%d')

        print(f"✓ {len(data)} days ({start_date} to {end_date})")
        return True

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def download_all_stocks(symbols=None, force_refresh=False):
    """Download all stocks in the universe"""
    if symbols is None:
        symbols = UNIVERSE

    # Create data directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)

    print("="*80)
    print("STOCK DATA DOWNLOAD")
    print("="*80)
    print(f"Universe size: {len(symbols)} stocks")
    print(f"Data directory: {DATA_DIR}")
    print(f"Force refresh: {force_refresh}")
    print()

    success_count = 0
    skip_count = 0
    fail_count = 0

    for idx, symbol in enumerate(symbols, 1):
        # Skip if already exists and not forcing refresh
        filepath = os.path.join(DATA_DIR, f"{symbol}.csv")
        if os.path.exists(filepath) and not force_refresh:
            print(f"[{idx}/{len(symbols)}] {symbol} - Skipped (already cached)")
            skip_count += 1
            continue

        print(f"[{idx}/{len(symbols)}] ", end="")
        if download_stock_history(symbol):
            success_count += 1
        else:
            fail_count += 1

        # Rate limiting - be nice to Yahoo Finance
        time.sleep(0.5)

    print()
    print("="*80)
    print("DOWNLOAD COMPLETE")
    print("="*80)
    print(f"✓ Success: {success_count}")
    print(f"⊘ Skipped: {skip_count}")
    print(f"✗ Failed:  {fail_count}")
    print(f"Total: {len(symbols)}")
    print()
    print(f"Data saved to: {DATA_DIR}")
    print("="*80)

def get_cached_stock(symbol, data_dir=DATA_DIR):
    """Load cached stock data from CSV"""
    filepath = os.path.join(data_dir, f"{symbol}.csv")

    if not os.path.exists(filepath):
        return None

    data = pd.read_csv(filepath, index_col=0, parse_dates=True)
    return data

def refresh_recent_data(symbols=None, days=5):
    """Refresh only the most recent data for all stocks (faster than full refresh)"""
    if symbols is None:
        symbols = UNIVERSE

    print("="*80)
    print(f"REFRESHING RECENT DATA (Last {days} days)")
    print("="*80)

    for idx, symbol in enumerate(symbols, 1):
        filepath = os.path.join(DATA_DIR, f"{symbol}.csv")

        if not os.path.exists(filepath):
            # File doesn't exist, do full download
            print(f"[{idx}/{len(symbols)}] {symbol} - No cache, downloading full history...", end=" ")
            download_stock_history(symbol)
            continue

        try:
            # Load existing data
            existing_data = pd.read_csv(filepath, index_col=0, parse_dates=True)
            last_date = existing_data.index[-1]

            # Download recent data
            stock = yf.Ticker(symbol)
            recent_data = stock.history(period=f"{days}d")

            if len(recent_data) == 0:
                print(f"[{idx}/{len(symbols)}] {symbol} - ❌ No recent data")
                continue

            # Merge with existing data (drop duplicates)
            combined = pd.concat([existing_data, recent_data])
            combined = combined[~combined.index.duplicated(keep='last')]
            combined = combined.sort_index()

            # Save back to CSV
            combined.to_csv(filepath)

            new_days = len(recent_data)
            print(f"[{idx}/{len(symbols)}] {symbol} - ✓ Updated ({new_days} new days)")

        except Exception as e:
            print(f"[{idx}/{len(symbols)}] {symbol} - ❌ Error: {str(e)}")

        time.sleep(0.5)

    print()
    print("="*80)
    print("REFRESH COMPLETE")
    print("="*80)

def cache_info():
    """Show information about the cache"""
    print("="*80)
    print("CACHE INFORMATION")
    print("="*80)
    print(f"Data directory: {DATA_DIR}")
    print()

    if not os.path.exists(DATA_DIR):
        print("Cache directory does not exist")
        return

    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]

    if len(files) == 0:
        print("No cached data found")
        return

    print(f"Cached stocks: {len(files)}")
    print()

    # Show sample of cached stocks with details
    print("Sample of cached data:")
    print("-"*80)

    for filename in sorted(files)[:10]:  # Show first 10
        symbol = filename.replace('.csv', '')
        filepath = os.path.join(DATA_DIR, filename)

        try:
            data = pd.read_csv(filepath, index_col=0, parse_dates=True)
            start_date = data.index[0].strftime('%Y-%m-%d')
            end_date = data.index[-1].strftime('%Y-%m-%d')
            file_size = os.path.getsize(filepath) / 1024  # KB

            print(f"{symbol:6} | {len(data):5} days | {start_date} to {end_date} | {file_size:.1f} KB")
        except:
            print(f"{symbol:6} | Error reading file")

    if len(files) > 10:
        print(f"... and {len(files) - 10} more")

    print("="*80)

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "refresh":
            # Force refresh all data
            download_all_stocks(force_refresh=True)
        elif command == "recent":
            # Update only recent days
            refresh_recent_data()
        elif command == "info":
            # Show cache info
            cache_info()
        elif command == "help":
            print("Usage:")
            print("  python download_stock_data.py          - Download missing stocks")
            print("  python download_stock_data.py refresh  - Force refresh all data")
            print("  python download_stock_data.py recent   - Update recent data only")
            print("  python download_stock_data.py info     - Show cache information")
        else:
            print(f"Unknown command: {command}")
            print("Run 'python download_stock_data.py help' for usage")
    else:
        # Default: download only missing stocks
        download_all_stocks(force_refresh=False)
