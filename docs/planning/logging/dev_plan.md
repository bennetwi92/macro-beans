# Logging Module Development Plan

## 1. Objective
To implement the generic logging module as defined in the `specification.md`. The module will provide a factory function `get_logger(app_name)` that returns a pre-configured, isolated logger instance for any application in the repository.

## 2. Directory and File Structure
1.  Create the source directory for the module: `src/logging/`.
2.  Create the main implementation file: `src/logging/core.py`.
3.  Create an `__init__.py` file to expose the public interface: `src/logging/__init__.py`.

```
src/
└───logging/
    ├───__init__.py
    └───core.py
```

## 3. Implementation Steps

### Step 3.1: Implement `core.py`
- Import `sys` and `loguru`.
- In `core.py`, define the main factory function `get_logger(app_name: str)`.
- **Initial Setup**: Inside the function or at the module level, ensure the default `loguru` handler is removed (`logger.remove()`) and a base console logger is added. This should be done only once to avoid duplicating handlers.
- **File Sink Configuration**: The `get_logger` function will add a new sink for the specified `app_name`:
    - **Path**: `logs/{app_name}.log`
    - **Filter**: Use a lambda filter to ensure the sink only processes records where `record["extra"].get("app") == app_name`.
    - **Rotation & Retention**: Implement size-based rotation (`100 MB`) and retention (`7 days`) as per the specification.
    - **Format**: Set the log format to `{time} {level} [{extra[app]}] {message}`.
    - **Process Safety**: Use `enqueue=True` to make logging safe across multiple processes.
- **Return Value**: The function will return `logger.bind(app=app_name)`.

### Step 3.2: Expose Public API in `__init__.py`
- In `src/logging/__init__.py`, import and expose the `get_logger` function.
- Add `__all__ = ["get_logger"]` to define the public API.

```python
# src/logging/__init__.py
from .core import get_logger

__all__ = ["get_logger"]
```

## 4. Documentation
- Add comprehensive docstrings to the `get_logger` function in `core.py`, explaining its purpose, parameters, return value, and the isolation mechanism.
- Add a `README.md` inside `src/logging/` explaining how to use the module with a clear code example.

## 5. Example/Demonstration
- Create a temporary script (e.g., `scripts/test_logging.py`) that imports and uses the logger for two different "apps" to manually verify that logs are correctly isolated to their respective files while both appear on the console. This script will be for development purposes and can be removed later.

## 6. Timeline
- **Phase 1**: Implement `core.py` and `__init__.py`. (Estimated: 1-2 hours)
- **Phase 2**: Write unit tests as per the test plan. (Estimated: 2-3 hours)
- **Phase 3**: Add documentation and usage examples. (Estimated: 1 hour)
- **Phase 4**: Code review and integration.