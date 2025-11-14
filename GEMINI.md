# Project Overview

This project is a repo to support my swing trading activities.

**Core Values:** Extremely lightweight and simple implementation

| Topic | Description |
| :--- | :--- |
| Language | Python |
| UI Framework | Streamlit |
| Database | MongoDB |
| Data Source | Interactive Brokers TWS API |
| Logging | Use Loguru |
| Environment | Conda |
| Code Style | PEP 8 |
| Testing | pytest >75% coverage |

**Important Note for Agents:** When running tests, always ensure they are executed within the `replay-tool` conda environment. Use the command `conda run -n replay-tool pytest <path_to_tests>`.

**Navigation:**

`docs/`: for planning development and training guides
`logs/`: storing all logs
`scripts/`: for adhoc scripts that demostrate different functionalities
`src/`: All permanent source code is stored here.
`src/broker/`: Source code for the broker connection to TWS API
`src/logging/`: Source code for the logging utility.
`src/mongodb/`: Util functions for database connection
`src/replay/`: The source code for the streamlit replay app.
`tests/`: Parent test directory. No tests should be stored in this directory. instead they should be in the child directories
`tests/broker/`: tests related to the broker connection
`tests/logging/`: tests related to the logging utility
`tests/mongodb/`: tests related to the database connection




