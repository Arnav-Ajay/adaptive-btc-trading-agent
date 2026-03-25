"""Derived interval preprocessing from canonical 1m candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC

import pandas as pd

from app.ingestion.parquet_store import ParquetMarketDataStore, WriteResult
from app.utils.models import Candle


DERIVED_INTERVAL_RULES = {
    "10m": "10min",
    "30m": "30min",
    "1hr": "1h",
    "1d": "1D",
    "1week": "W-MON",
    "1month": "MS",
}


@dataclass(slots=True)
class DerivedIntervalResult:
    """Write summary for one derived interval."""

    interval: str
    write_result: WriteResult


class MarketDataPreprocessor:
    """Build derived interval parquet datasets from canonical 1m data."""

    def __init__(self, store: ParquetMarketDataStore) -> None:
        """Initialize the preprocessor with the shared market-data store."""
        self.store = store

    def build_all(self, symbol: str, source_interval: str) -> list[DerivedIntervalResult]:
        """Build all configured derived intervals from the raw source interval."""
        source_candles = self.store.load_candles(symbol=symbol, interval=source_interval, limit=None)
        if not source_candles:
            return []

        results: list[DerivedIntervalResult] = []
        for interval, rule in DERIVED_INTERVAL_RULES.items():
            derived_candles = self._resample(source_candles, rule=rule)
            write_result = self.store.write_candles(
                symbol=symbol,
                interval=interval,
                candles=derived_candles,
            )
            results.append(DerivedIntervalResult(interval=interval, write_result=write_result))
        return results

    @staticmethod
    def _resample(candles: list[Candle], rule: str) -> list[Candle]:
        """Resample candles to a larger interval using OHLCV aggregation."""
        frame = pd.DataFrame(
            [
                {
                    "datetime": candle.timestamp.astimezone(UTC),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in candles
            ]
        )
        if frame.empty:
            return []

        frame = frame.drop_duplicates(subset=["datetime"], keep="last").sort_values("datetime")
        frame = frame.set_index("datetime")
        resampled = frame.resample(rule, label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])

        derived: list[Candle] = []
        for timestamp, row in resampled.iterrows():
            derived.append(
                Candle(
                    timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return derived
