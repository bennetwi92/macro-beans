# Logging Module Specification

## Purpose
This document outlines the specification for a generic logging module based on Loguru, intended for use across all modules within this repository. The primary goal is to provide a consistent, easy-to-use, and efficient logging mechanism that centralizes log output.

## Technology
The logging module will utilize `Loguru` due to its simplicity, powerful features, and ease of configuration.

## Requirements

### 1. Per-Application Logging
Each distinct application or major module within the repository (e.g., `broker`, `replay`, `mongodb`) must be able to generate its own set of logs. This ensures clear separation and easier debugging.

### 2. Centralized Log Output Directory
All generated log files, regardless of the originating application, must be stored within the `logs/` directory at the root of the repository.

### 3. Log File Naming Convention
Log files should follow a clear and consistent naming convention, ideally incorporating the application name and a timestamp or date.
Example: `logs/{app_name}_{date}.log` (e.g., `logs/broker_2023-10-27.log`, `logs/replay_2023-10-27.log`).

### 4. Log Levels
The logging module should support standard log levels (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). The default log level should be configurable.

### 5. Log Rotation
To prevent log files from growing indefinitely and consuming excessive disk space, log rotation should be implemented. This includes:
- **Size-based rotation:** Rotate logs when they reach a certain size (e.g., 100 MB).
- **Time-based rotation:** Optionally rotate logs daily.
- **Retention policy:** Keep a configurable number of old log files (e.g., 7 days).

### 6. Log Format
Log messages should be formatted consistently to include:
- Timestamp
- Log level
- Module/Application name
- Message content
- (Optional) File path and line number where the log was generated

Example format: `{time} {level} {name} {message}`

### 7. Easy Integration
The module should provide a simple interface for other modules to integrate logging, ideally requiring only a few lines of code to set up and start logging.

### 8. Console Output
In addition to file output, logs should also be directed to the console (stdout/stderr) during development and optionally in production, with configurable levels.

## Usage (Conceptual)

To ensure true log isolation between modules (especially if they could run in the same process), the logging utility should provide a factory function that returns a logger with a specific context. Relying on the global `loguru.logger` directly can lead to modules overwriting each other's configurations or logging to incorrect files.

A more robust pattern involves using `logger.bind()` to add context and a `filter` on the sink to direct messages accordingly.

**Improved Conceptual Example:**

```python
# In a central logging utility (e.g., src/logging/utils.py)
import sys
from loguru import logger

# It's good practice to remove the default handler to have full control.
logger.remove()
logger.add(sys.stderr, level="INFO") # Add a default console logger.

def get_logger(app_name: str):
    """
    Configures and returns a logger for a specific application.
    Logs from this logger will go to a dedicated file.
    """
    log_file = f"logs/{app_name}.log"
    # Use a filter to direct logs only from the correct app
    logger.add(
        log_file,
        filter=lambda record: record["extra"].get("app") == app_name,
        rotation="100 MB",
        retention="7 days",
        level="DEBUG",
        format="{time} {level} [{extra[app]}] {message}" # Include app name in format
    )
    # Bind the app_name to the logger's context
    return logger.bind(app=app_name)

# --- How modules would use it ---

# In broker application:
# from src.logging.utils import get_logger
# log = get_logger("broker")
# log.info("This message will only appear in broker.log")

# In replay application:
# from src.logging.utils import get_logger
# log = get_logger("replay")
# log.warning("This message will only appear in replay.log")
```

## Future Considerations
- **Structured Logging:** Explore structured logging (e.g., JSON format) for easier machine parsing and analysis.
- **Remote Logging:** Option to send logs to a remote logging service (e.g., ELK stack, Sentry).
- **Performance:** Monitor logging performance and optimize if necessary.