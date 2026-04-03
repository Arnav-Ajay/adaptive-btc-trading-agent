# app/data/parquet_market_data.py
"""Local parquet-backed market data reader."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.ingestion.parquet_store import CandleBounds, ParquetMarketDataStore
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

    def fetch_dashboard_candles(self, interval: str | None = None, limit: int | None = None) -> list[Candle]:
        """Load a deeper candle history for UI/charting use cases."""
        return self.store.load_candles(
            symbol=self.config.trading.symbol,
            interval=interval or self.config.ingestion.interval,
            limit=limit if limit is not None else self.config.data.dashboard_lookback,
        )

    def fetch_candle_bounds(self, interval: str | None = None) -> CandleBounds:
        """Load the earliest and latest available timestamps for a given interval."""
        return self.store.load_candle_bounds(
            symbol=self.config.trading.symbol,
            interval=interval or self.config.ingestion.interval,
        )
