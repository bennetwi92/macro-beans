"""
A script to demonstrate and manually test the logging module.

This script simulates two different applications ('broker' and 'replay')
using the centralized logging module. It verifies that:
1. Logs from each app are isolated to their respective files.
2. Console logs show messages from both apps.
"""
import time
from src.logging import get_logger

def run_broker():
    """Simulates a broker application process."""
    log = get_logger("broker")
    log.info("Broker service starting...")
    log.debug("Initializing message queue connection.")
    time.sleep(0.1)
    log.warning("Queue connection is a bit slow today.")
    time.sleep(0.1)
    log.info("Broker service is now running.")
    log.debug("Waiting for messages.")

def run_replay():
    """Simulates a replay application process."""
    log = get_logger("replay")
    log.info("Replay service starting...")
    log.debug("Connecting to database.")
    time.sleep(0.1)
    log.info("Replay service is now running.")
    log.debug("Starting to process historical data.")
    log.error("Failed to process record #12345.")

if __name__ == "__main__":
    print("--- Running Logging Demonstration ---")
    print("This will generate logs in the 'logs/' directory.")
    print("Console should show INFO, WARNING, and ERROR messages from both apps.")
    print("-" * 35)

    run_broker()
    run_replay()

    print("-" * 35)
    print("Demonstration complete.")
    print("Check 'logs/broker.log' and 'logs/replay.log' for file output.")
    print("The log files will contain DEBUG messages in addition to the console output.")
