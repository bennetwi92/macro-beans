import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from src.data.provider import DataProvider


@pytest.fixture
def provider(tmp_path):
    return DataProvider(cache_dir=str(tmp_path / "cache"))


def _mock_download(ticker, start, end, auto_adjust, progress):
    """Return a simple DataFrame mimicking yfinance output."""
    dates = pd.bdate_range(start, periods=10, freq="B")
    return pd.DataFrame({
        "Open": [25.0] * 10,
        "High": [26.0] * 10,
        "Low": [24.0] * 10,
        "Close": [25.5] * 10,
        "Volume": [500000] * 10,
    }, index=dates)


class TestDataProvider:
    @patch("src.data.provider.yf.download", side_effect=_mock_download)
    def test_fetch_returns_dataframe(self, mock_dl, provider):
        df = provider.fetch("BRNT.L", "2023-01-01", "2023-02-01")
        assert isinstance(df, pd.DataFrame)
        assert "close" in df.columns
        assert "open" in df.columns
        assert len(df) == 10

    @patch("src.data.provider.yf.download", side_effect=_mock_download)
    def test_fetch_caches_to_csv(self, mock_dl, provider):
        provider.fetch("BRNT.L", "2023-01-01", "2023-02-01")
        provider.fetch("BRNT.L", "2023-01-01", "2023-02-01")
        # yfinance should only be called once due to cache
        assert mock_dl.call_count == 1

    @patch("src.data.provider.yf.download", return_value=pd.DataFrame())
    def test_fetch_empty_returns_empty(self, mock_dl, provider):
        df = provider.fetch("FAKE.L", "2023-01-01", "2023-02-01")
        assert df.empty

    @patch("src.data.provider.yf.download", side_effect=_mock_download)
    def test_columns_lowercase(self, mock_dl, provider):
        df = provider.fetch("BRNT.L", "2023-01-01", "2023-02-01")
        for col in df.columns:
            assert col == col.lower()
