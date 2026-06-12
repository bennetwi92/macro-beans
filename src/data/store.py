"""MarketStore -- the single read surface for cached price data.

All analysis code reads prices through ``MarketStore.get_prices(ticker)``,
which returns a pandas DataFrame in the **same shape the old CSV cache
produced**: a ``DatetimeIndex`` named ``Date`` with capitalized
``Open/High/Low/Close/Volume`` columns. This keeps existing consumers working
with near-zero changes.

The store opens DuckDB **read-only** by default, so any number of analysis
processes can read concurrently. Only ``refresh.py`` writes.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.data.paths import DB_PATH

# DuckDB column order matches the OHLCV schema; we re-capitalize on the way out
# to match the historical CSV shape.
_PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Required columns / minimum rows for a usable series. Shared validation so
# every caller fails the same way (mirrors the old storage_model loader).
REQUIRED_COLUMNS = set(_PRICE_COLUMNS)


class MarketStore:
    """Read-only access to the DuckDB price cache."""

    def __init__(self, db_path: Path | str = DB_PATH, read_only: bool = True):
        self.db_path = Path(db_path)
        self.read_only = read_only
        if read_only and not self.db_path.exists():
            raise FileNotFoundError(
                f"Price database not found at {self.db_path}. "
                f"Build it with: python -m src.data.refresh --full"
            )

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path), read_only=self.read_only)

    def available_tickers(self) -> list[str]:
        """Every ticker that has price rows in the cache (sorted)."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT ticker FROM meta ORDER BY ticker"
            ).fetchall()
        return [r[0] for r in rows]

    def get_prices(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return OHLCV for ``ticker`` as a Date-indexed DataFrame.

        Empty DataFrame (with the right columns) if the ticker is absent, so
        callers can branch on ``.empty`` exactly as they did with missing CSVs.
        """
        query = (
            "SELECT date, open, high, low, close, volume "
            "FROM prices WHERE ticker = ?"
        )
        params: list = [ticker]
        if start is not None:
            query += " AND date >= ?"
            params.append(start)
        if end is not None:
            query += " AND date <= ?"
            params.append(end)
        query += " ORDER BY date"

        with self._connect() as con:
            df = con.execute(query, params).df()

        if df.empty:
            return pd.DataFrame(columns=_PRICE_COLUMNS).rename_axis("Date")

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df.index.name = "Date"
        df.columns = _PRICE_COLUMNS
        return df

    def meta(self) -> pd.DataFrame:
        """The staleness catalog: per-ticker first/last date, rows, fetched_at."""
        with self._connect() as con:
            return con.execute(
                "SELECT ticker, first_date, last_date, n_rows, fetched_at "
                "FROM meta ORDER BY ticker"
            ).df()


def validate_prices(df: pd.DataFrame, ticker: str, min_rows: int = 100) -> None:
    """Raise if a price frame is missing columns or too short to be useful."""
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{ticker}: missing columns {missing}")
    if len(df) < min_rows:
        raise ValueError(
            f"{ticker}: only {len(df)} rows -- need at least {min_rows} "
            f"for meaningful analysis"
        )


__all__ = ["MarketStore", "validate_prices", "REQUIRED_COLUMNS"]
