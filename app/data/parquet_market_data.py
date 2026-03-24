# app/data/parquet_market_data.py
"""Local parquet-backed market data reader."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.utils.models import Candle


class ParquetMarketDataClient:
    """Read normalized candles from the local parquet data lake."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the parquet-backed market data client."""
        self.config = config
        self.store = ParquetMarketDataStore(config.data.data_lake_path)

    def fetch_candles(self) -> list[Candle]:
        """Load the most recent candles required by the trading runtime."""
        return self.store.load_recent_candles(
            symbol=self.config.trading.symbol,
            interval=self.config.ingestion.interval,
            limit=self.config.data.trading_lookback,
        )
