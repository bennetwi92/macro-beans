"""
Unit tests for the core logging module.
"""
import sys
import pytest
from loguru import logger as global_logger
from src.logging.core import get_logger, _initialized_sinks

# Pytest fixture to clean up handlers and sinks after each test.
# This ensures that tests are independent and don't interfere with each other.
@pytest.fixture(autouse=True)
def reset_loguru():
    """
    A fixture to reset the Loguru configuration before and after each test.
    This is crucial to ensure test isolation.
    """
    # Before the test, clear everything.
    global_logger.remove()
    _initialized_sinks.clear()

    yield  # This is where the test runs

    # After the test, clear everything again.
    global_logger.remove()
    _initialized_sinks.clear()


def test_logger_isolation(tmp_path, monkeypatch):
    """
    Tests that logs from two different apps are written only to their
    respective log files.
    """
    # Point the logging directory to pytest's tmp_path
    # We need to modify the get_logger function to allow this, or monkeypatch it.
    # For now, let's assume we can direct output. A better way would be to
    # make the log directory configurable. Let's patch the Path object.
    from src.logging import core
    monkeypatch.setattr(core, "Path", lambda _: tmp_path)

    # 1. Get loggers for two different apps
    log_a = get_logger("app_a")
    log_b = get_logger("app_b")

    # 2. Log messages
    msg_a = "This is a message from App A"
    msg_b = "This is a message from App B"
    log_a.info(msg_a)
    log_b.warning(msg_b)

    # 3. Define log file paths
    log_file_a = tmp_path / "app_a.log"
    log_file_b = tmp_path / "app_b.log"

    # 4. Assert files were created
    assert log_file_a.exists()
    assert log_file_b.exists()

    # 5. Read contents and assert isolation
    content_a = log_file_a.read_text()
    content_b = log_file_b.read_text()

    assert msg_a in content_a
    assert msg_b not in content_a

    assert msg_b in content_b
    assert msg_a not in content_b


def test_console_output(capsys):
    """
    Tests that log messages are correctly written to stderr.
    """
    # The default console logger is INFO level.
    log = get_logger("console_app")

    debug_msg = "This is a debug message."
    info_msg = "This is an info message."

    log.debug(debug_msg)
    log.info(info_msg)

    captured = capsys.readouterr()

    assert info_msg in captured.err
    assert debug_msg not in captured.err # DEBUG is below INFO


def test_log_format(tmp_path, monkeypatch):
    """
    Tests that the log format in the file matches the specification.
    """
    from src.logging import core
    monkeypatch.setattr(core, "Path", lambda _: tmp_path)

    app_name = "format_app"
    log = get_logger(app_name)
    msg = "Testing format."
    log.info(msg)

    log_file = tmp_path / f"{app_name}.log"
    content = log_file.read_text()

    # Example format: {time} | {level} | [{extra[app]}] | {name}:{function}:{line} - {message}
    assert "| INFO     |" in content
    assert f"| [{app_name}] |" in content
    assert msg in content
    assert "test_log_format" in content # function name


def test_sink_initialization_is_idempotent(tmp_path, monkeypatch):
    """
    Tests that calling get_logger multiple times for the same app does not
    add duplicate file sinks.
    """
    from src.logging import core
    monkeypatch.setattr(core, "Path", lambda _: tmp_path)

    app_name = "idempotent_app"
    log_file = tmp_path / f"{app_name}.log"

    # Call get_logger twice for the same app
    log1 = get_logger(app_name)
    log2 = get_logger(app_name)

    # There should be one console sink and one file sink
    # The internal logger object is `global_logger`
    # Note: This is white-box testing, but necessary here.
    assert len(global_logger._core.handlers) == 2

    # Log a message
    msg = "Testing idempotency"
    log1.info(msg)

    # Read the file and ensure the message appears only once
    content = log_file.read_text()
    assert content.count(msg) == 1
