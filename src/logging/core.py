"""
Core implementation of the Loguru-based logging module.
"""
import sys
from pathlib import Path
from loguru import logger
import logging # Import the standard logging module

# A set to keep track of initialized sinks to avoid duplication.
# This state is managed globally for the lifetime of the application.
_initialized_sinks = set()


class PropagateHandler(logging.Handler):
    """
    A handler that propagates Loguru messages to the standard logging module.
    This is necessary for pytest's caplog fixture to capture Loguru output.
    """
    def emit(self, record):
        logging.getLogger(record.name).handle(record)


def get_logger(app_name: str):
    """
    Creates and returns a Loguru logger instance configured for a specific application.

    This function ensures that logs from different applications are isolated
    into their own respective log files. It uses a filter based on the 'app'
    context to direct log records to the correct file sink.

    Handlers for the console and for each application's file are added only
    once to avoid duplicating log entries.

    Args:
        app_name (str): The name of the application, used to name the log file
                        and to filter log records.

    Returns:
        loguru.Logger: A logger instance with the 'app' name bound to its context.
                       All logs created from this instance will be tagged with
                       the application name.
    """
    # Add a console sink only if it hasn't been initialized yet.
    if "_console" not in _initialized_sinks:
        logger.remove() # Remove any default or pre-existing handlers
        logger.add(
            sys.stderr,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
        )
        _initialized_sinks.add("_console")

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)  # Ensure the log directory exists.
    log_file = log_dir / f"{app_name}.log"

    # Add a file sink only if it hasn't been initialized for this app_name yet.
    if app_name not in _initialized_sinks:
        logger.add(
            log_file,
            filter=lambda record: record["extra"].get("app") == app_name,
            level="DEBUG",
            rotation="100 MB",
            retention="7 days",
            enqueue=True,  # Make it process-safe.
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | [{extra[app]}] | {name}:{function}:{line} - {message}",
            encoding="utf-8"
        )
        # Add a handler to propagate Loguru messages to the standard logging module
        logger.add(PropagateHandler(), level="DEBUG", filter=lambda record: record["extra"].get("app") == app_name)
        _initialized_sinks.add(app_name)

    # Return a logger with the application name bound to the context.
    return logger.bind(app=app_name)