# `src` Directory for Agents

This document outlines the purpose of the `src` directory and provides guidelines for agents interacting with its contents, including conventions and best practices.

## Purpose of the `src` Directory

The `src` directory contains all the core source code for the `replay-tool` project. It is organized into submodules, each responsible for a distinct part of the application's functionality.

## Submodules Overview

-   **`broker/`**: Contains logic for interacting with the Interactive Brokers (IB) TWS API. This includes connection management, historical data requests, and error handling specific to the TWS API.
-   **`logging/`**: Provides a centralized and consistent logging mechanism for the entire project, built on `loguru`.
-   **`market_data/`**: (This module) Responsible for collecting specific market datasets (e.g., 5-second intraday, daily historical) by wrapping the `broker` service.
-   **`mongodb/`**: (Placeholder) Expected to contain logic for interacting with MongoDB, likely for data storage or retrieval.
-   **`replay/`**: (Placeholder) Expected to contain the core logic for the replay functionality of the tool.

## Agent Interaction Guidelines and Conventions

When interacting with or modifying code within the `src` directory, agents should adhere to the following conventions:

1.  **Code Style**:
    -   **PEP 8**: All Python code must conform to PEP 8 style guidelines.
    -   **Formatting**: Use an auto-formatter like `black` or `ruff format` if available in the project's CI/CD pipeline or pre-commit hooks.
    -   **Naming**: Follow Python's standard naming conventions (e.g., `snake_case` for functions/variables, `CamelCase` for classes).

2.  **Testing**:
    -   **Unit Tests**: For any new features or bug fixes, corresponding unit tests must be added in the `tests/` directory, mirroring the `src/` directory structure (e.g., `src/module/file.py` -> `tests/module/test_file.py`).
    -   **Framework**: Use `pytest` for all testing.
    -   **Mocking**: When testing modules that interact with external services (like `broker` or `market_data`), mock external dependencies to ensure tests are fast and isolated.

3.  **Logging**:
    -   **Centralized Logging**: Always use the `get_logger` function from `src.logging.core` to obtain a logger instance for your module. Do not import `loguru` directly.
    -   **Context**: Bind an `app` name to your logger (e.g., `logger = get_logger("my_module_name")`) to ensure logs are correctly filtered and routed.
    -   **Levels**: Use appropriate logging levels (`info`, `debug`, `warning`, `error`, `critical`, `success`).

4.  **Dependency Management**:
    -   **`environment.yml`**: Any new external Python packages introduced must be added to the `dependencies` list in the `environment.yml` file.

5.  **Documentation**:
    -   **Docstrings**: All public functions, classes, and methods must have comprehensive docstrings explaining their purpose, arguments, and return values.
    -   **`GEMINI.md` Files**: Each significant module or directory should have a `GEMINI.md` file explaining its purpose and how an agent should interact with it.

6.  **Error Handling**:
    -   **Graceful Degradation**: Implement robust error handling. Avoid crashing the application; instead, log errors and, where appropriate, return empty data structures or sensible defaults.
    -   **Custom Exceptions**: Use custom exceptions (e.g., `BrokerError`) where specific error conditions need to be communicated.

7.  **Module Structure**:
    -   **Consistency**: Maintain consistency with existing module structures. For example, if a module has a `collector.py` for its main logic, new modules should follow a similar pattern.
    -   **`__init__.py`**: Ensure `__init__.py` files are present in all package directories to make them importable.

By following these guidelines, agents can ensure their contributions are consistent, maintainable, and align with the overall project architecture.
