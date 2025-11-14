# Logging Module Test Plan

## 1. Objective
To verify that the logging module implementation meets all functional and non-functional requirements outlined in the `specification.md`. The tests will ensure that the logger is robust, provides correct output, and properly isolates log streams between different applications.

## 2. Testing Framework
- **Framework**: `pytest` will be used as the primary testing framework.
- **Fixtures**: `pytest`'s `tmp_path` fixture will be used to create temporary directories for log files, ensuring that tests do not pollute the repository and are cleaned up automatically.

## 3. Test Environment
- Tests will be located in `tests/logging/`.
- A test file `tests/logging/test_logging_core.py` will be created.
- The test environment must have `loguru` and `pytest` installed.

## 4. Test Cases

### 4.1. Test Logger Isolation
- **Description**: Verify that loggers created for different applications write only to their own log files.
- **Steps**:
    1.  Use `tmp_path` to create a temporary `logs` directory.
    2.  Instantiate two loggers: `log_a = get_logger("app_a")` and `log_b = get_logger("app_b")`.
    3.  Write a unique message to each logger (e.g., `log_a.info("Message A")`, `log_b.warning("Message B")`).
    4.  Read the content of `app_a.log` and `app_b.log`.
- **Assertions**:
    - Assert that `app_a.log` contains "Message A".
    - Assert that `app_a.log` does **not** contain "Message B".
    - Assert that `app_b.log` contains "Message B".
    - Assert that `app_b.log` does **not** contain "Message A".

### 4.2. Test Console Output
- **Description**: Verify that logs are correctly written to the standard error stream (console).
- **Steps**:
    1.  Instantiate a logger: `log_a = get_logger("app_a")`.
    2.  Use a fixture or context manager to capture `sys.stderr`.
    3.  Write a message: `log_a.info("Console test message")`.
- **Assertions**:
    - Assert that the captured `stderr` output contains "Console test message".

### 4.3. Test Log Format
- **Description**: Verify that log messages in the file are formatted according to the specification.
- **Steps**:
    1.  Instantiate a logger and write a message.
    2.  Read the first line from the generated log file.
- **Assertions**:
    - Assert that the line contains the current date.
    - Assert that the line contains the log level (e.g., `INFO`).
    - Assert that the line contains the application name (e.g., `[app_a]`).
    - Assert that the line contains the log message itself.

### 4.4. Test Log Rotation (Conceptual)
- **Description**: Verify that log files are rotated when they exceed the specified size. This is a more complex integration test.
- **Steps**:
    1.  Configure a logger with a very small rotation size (e.g., `rotation="1 KB"`). This may require a special test-only configuration.
    2.  Write more than 1 KB of data in a loop.
    3.  Check the log directory for rotated files (e.g., `app.log.1`).
- **Assertions**:
    - Assert that more than one log file exists for the application.
- **Note**: Due to the timing and I/O dependency, this test might be marked as a lower-priority or integration test rather than a standard unit test.

### 4.5. Test `get_logger` Return Value
- **Description**: Verify that the factory function returns a valid and correctly configured logger instance.
- **Steps**:
    1.  Call `log = get_logger("test_app")`.
- **Assertions**:
    - Assert that the returned `log` object is a `loguru.Logger` instance.
    - Assert that the logger's bound context is correct: `log.extra["app"] == "test_app"`.

## 5. Cleanup
- All tests creating files must use the `tmp_path` fixture to ensure no artifacts are left after the test suite runs.
- Care should be taken to properly close/remove handlers if they are manipulated dynamically during tests, although the proposed design should not require this.