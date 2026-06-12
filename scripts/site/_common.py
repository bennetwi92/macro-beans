"""Shared helpers for the site build scripts (build_data.py, build_portfolios.py).

Small, dependency-free utilities so the two builders stay consistent:
  * fetch_with_retry — retry a flaky network fetch a few times with backoff,
    so one transient yfinance hiccup doesn't abort the whole nightly refresh.
  * write_json — write compact JSON the way the browser expects it (no spaces).
  * BuildTally — collect per-item successes/failures and decide, at the end,
    whether coverage is good enough to publish.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")

# Publish only if at least this fraction of items built successfully. One flaky
# ticker shouldn't bin the whole site, but a broad yfinance outage should fail
# the deploy loudly rather than ship a gutted site.
MIN_OK_FRACTION = 0.9


def fetch_with_retry(fn: Callable[[], T], *, tries: int = 3, backoff: float = 2.0) -> T:
    """Call fn(), retrying on any exception up to `tries` times.

    Waits backoff, backoff*2, backoff*4, ... between attempts. Re-raises the
    last exception if every attempt fails.
    """
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — yfinance raises a grab-bag
            last = exc
            if attempt < tries - 1:
                time.sleep(backoff * (2 ** attempt))
    assert last is not None
    raise last


def write_json(path: Path, payload) -> int:
    """Write `payload` as compact JSON (no whitespace). Returns bytes written."""
    text = json.dumps(payload, separators=(",", ":"))
    path.write_text(text)
    return len(text.encode("utf-8"))


class BuildTally:
    """Track which items built and which failed, then gate the exit code."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.ok = 0
        self.failures: list[tuple[str, str]] = []  # (name, error message)

    def record_ok(self) -> None:
        self.ok += 1

    def record_failure(self, name: str, err: Exception) -> None:
        self.failures.append((name, str(err)))

    def report_and_exit_code(self) -> int:
        """Print a summary and return the process exit code (0 = ok)."""
        if not self.failures:
            return 0
        print(f"\n{len(self.failures)} item(s) failed to build:")
        for name, msg in self.failures:
            print(f"  - {name}: {msg}")
        if self.total == 0 or self.ok == 0:
            print("No items built — failing the build.")
            return 1
        frac = self.ok / self.total
        if frac < MIN_OK_FRACTION:
            print(
                f"Only {self.ok}/{self.total} built ({frac:.0%} < "
                f"{MIN_OK_FRACTION:.0%}) — failing the build."
            )
            return 1
        print(
            f"{self.ok}/{self.total} built ({frac:.0%}) — above the "
            f"{MIN_OK_FRACTION:.0%} threshold, publishing without the failed item(s)."
        )
        return 0
