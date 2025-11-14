# Logging Module

This module provides a standardized, easy-to-use logging utility for all applications in this repository.

## Purpose

The primary goal is to offer a simple way to get a pre-configured logger that automatically handles:
- **Log Isolation**: Logs from different applications (e.g., `broker`, `replay`) are automatically saved to separate files (`logs/broker.log`, `logs/replay.log`).
- **Console Output**: `INFO` level logs and higher are also printed to the console.
- **File Output**: `DEBUG` level logs and higher are saved to a file.
- **Log Rotation**: Log files are automatically rotated when they reach 100 MB.
- **Retention**: Old log files are kept for 7 days.
- **Process Safety**: Logging is safe to use across multiple processes.

## Usage

To use the logger, import the `get_logger` function and call it with the name of your application.

```python
from src.logging import get_logger

# Get a logger instance for your specific application
log = get_logger("my_awesome_app")

def main():
    log.debug("This is a detailed debug message. It will only go to the log file.")
    log.info("Application is starting up.")
    log.warning("Something looks a bit strange.")
    
    try:
        result = 1 / 0
    except ZeroDivisionError:
        log.exception("An error occurred!")

    log.info("Application shutting down.")

if __name__ == "__main__":
    main()
```

### Output

**Console Output:**
```
2023-10-27 10:30:00 | INFO     | Application is starting up.
2023-10-27 10:30:00 | WARNING  | Something looks a bit strange.
2023-10-27 10:30:00 | ERROR    | An error occurred!
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
2023-10-27 10:30:00 | INFO     | Application shutting down.
```

**File Output (`logs/my_awesome_app.log`):**
```
2023-10-27 10:30:00 | DEBUG    | [my_awesome_app] | ... - This is a detailed debug message...
2023-10-27 10:30:00 | INFO     | [my_awesome_app] | ... - Application is starting up.
2023-10-27 10:30:00 | WARNING  | [my_awesome_app] | ... - Something looks a bit strange.
2023-10-27 10:30:00 | ERROR    | [my_awesome_app] | ... - An error occurred!
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
2023-10-27 10:30:00 | INFO     | [my_awesome_app] | ... - Application shutting down.
```
