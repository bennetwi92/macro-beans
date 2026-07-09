"""Regression tests for date handling in the DuckDB cache writer.

Run with the project interpreter (no pytest needed):

    /usr/local/bin/python3 -m unittest tests.data.test_normalize_ohlcv -v

The bug these guard against: yfinance indexes ``.L`` (London) daily bars at
local midnight in the exchange timezone. Converting to UTC before dropping the
tz shifts every British-Summer-Time bar back one calendar day (Mon -> Sun),
which silently dropped the two most recent trading days from the v2 scanner's
date picker. ``normalize_ohlcv`` must store the *local* trading day.
"""

from __future__ import annotations

import unittest

import pandas as pd

from src.data.refresh import _calendar_dates, normalize_ohlcv


def _lse_frame(days, tz="Europe/London"):
    """A yfinance-shaped OHLCV frame indexed at local midnight in ``tz``."""
    idx = pd.DatetimeIndex(pd.to_datetime(days)).tz_localize(tz)
    idx.name = "Date"
    return pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 100},
        index=idx,
    )


class CalendarDatesTests(unittest.TestCase):
    def test_bst_london_bars_keep_their_local_day(self):
        # British Summer Time (UTC+1): local midnight must NOT slip to the
        # previous calendar day.
        days = ["2026-07-03", "2026-07-06", "2026-07-07"]  # Fri, Mon, Tue
        got = [d.date().isoformat() for d in _calendar_dates(_lse_frame(days).reset_index()["Date"])]
        self.assertEqual(got, days)

    def test_gmt_london_bars_unchanged(self):
        # Winter (UTC+0) was never affected; make sure the fix keeps it correct.
        days = ["2026-01-05", "2026-01-06"]  # Mon, Tue
        got = [d.date().isoformat() for d in _calendar_dates(_lse_frame(days).reset_index()["Date"])]
        self.assertEqual(got, days)

    def test_tz_naive_input_passes_through(self):
        days = ["2026-07-06", "2026-07-07"]
        naive = pd.to_datetime(pd.Series(days))
        got = [d.date().isoformat() for d in _calendar_dates(naive)]
        self.assertEqual(got, days)


class NormalizeOhlcvTests(unittest.TestCase):
    def test_lse_summer_dates_are_preserved_end_to_end(self):
        days = ["2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07"]
        out = normalize_ohlcv(_lse_frame(days), "VUSA.L")
        self.assertEqual(
            [d.date().isoformat() for d in out["date"]],
            days,
            "London summer bars must be stored under their real trading day",
        )
        # No spurious weekend dates should appear.
        weekdays = {d.weekday() for d in out["date"]}
        self.assertTrue(weekdays.issubset({0, 1, 2, 3, 4}), "no Sat/Sun labels")


if __name__ == "__main__":
    unittest.main()
