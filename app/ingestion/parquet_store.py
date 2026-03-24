# app/ingestion/parquet_store.py
"""Partitioned parquet storage for market data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.utils.models import Candle


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WriteResult:
    """Result of a parquet write operation."""

    rows_read_existing: int
    rows_received: int
    rows_written: int
    final_rows_persisted: int
    partitions_updated: int
    latest_timestamp: str | None


class ParquetMarketDataStore:
    """Store normalized candle records in partitioned parquet files."""

    def __init__(self, root_path: str) -> None:
        """Initialize the parquet store."""
        self.root_path = Path(root_path)

    def write_candles(
        self,
        symbol: str,
        interval: str,
        candles: list[Candle],
    ) -> WriteResult:
        """Merge, deduplicate, validate, and persist candle records."""
        if not candles:
            return WriteResult(0, 0, 0, 0, 0, None)

        frame = self._to_frame(candles=candles, symbol=symbol, interval=interval)
        frame = self._validate(frame)
        frame = frame.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")

        total_existing = 0
        total_rows_added = 0
        total_persisted = 0
        partitions_updated = 0

        for partition_key, partition_frame in frame.groupby(["year", "month", "day"], sort=True):
            target_path = self._partition_file_path(
                symbol=symbol,
                interval=interval,
                year=int(partition_key[0]),
                month=int(partition_key[1]),
                day=int(partition_key[2]),
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists():
                existing = pd.read_parquet(target_path)
                total_existing += len(existing.index)
                merged = pd.concat([existing, partition_frame], ignore_index=True)
            else:
                existing = pd.DataFrame(columns=partition_frame.columns)
                merged = partition_frame.copy()

            existing_unique = existing.drop_duplicates(subset=["timestamp"], keep="last")
            merged = merged.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
            self._atomic_write(frame=merged, path=target_path)
            rows_added = max(len(merged.index) - len(existing_unique.index), 0)
            total_rows_added += rows_added
            total_persisted += len(merged.index)
            partitions_updated += 1

        latest_timestamp = frame["datetime"].max().isoformat() if not frame.empty else None
        return WriteResult(
            rows_read_existing=total_existing,
            rows_received=len(candles),
            rows_written=total_rows_added,
            final_rows_persisted=total_persisted,
            partitions_updated=partitions_updated,
            latest_timestamp=latest_timestamp,
        )

    def load_recent_candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        """Load the most recent candles from the partitioned parquet store."""
        symbol_path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        if not symbol_path.exists():
            return []

        parquet_files = sorted(symbol_path.rglob("*.parquet"))
        if not parquet_files:
            return []

        frames: list[pd.DataFrame] = []
        for parquet_file in reversed(parquet_files):
            frames.append(pd.read_parquet(parquet_file))
            combined_rows = sum(len(frame.index) for frame in frames)
            if combined_rows >= limit:
                break

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
        recent = combined.tail(limit)
        candles: list[Candle] = []
        for row in recent.to_dict(orient="records"):
            candles.append(
                Candle(
                    timestamp=row["datetime"].to_pydatetime() if hasattr(row["datetime"], "to_pydatetime") else row["datetime"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return candles

    def _partition_file_path(self, symbol: str, interval: str, year: int, month: int, day: int) -> Path:
        """Build the partition file path for a given date."""
        return (
            self.root_path
            / f"symbol={symbol}"
            / f"interval={interval}"
            / f"year={year:04d}"
            / f"month={month:02d}"
            / f"day={day:02d}"
            / "data.parquet"
        )

    def _to_frame(self, candles: list[Candle], symbol: str, interval: str) -> pd.DataFrame:
        """Convert normalized candles into a DataFrame with partition columns."""
        normalized_rows: list[dict[str, Any]] = []
        for candle in candles:
            if not isinstance(candle.timestamp, datetime):
                raise TypeError("Ingestion candles must contain datetime timestamps")
            timestamp = candle.timestamp.astimezone(UTC)
            normalized_rows.append(
                {
                    "timestamp": int(timestamp.timestamp()),
                    "datetime": timestamp,
                    "open": float(candle.open),
                    "high": float(candle.high),
                    "low": float(candle.low),
                    "close": float(candle.close),
                    "volume": float(candle.volume),
                    "symbol": symbol,
                    "interval": interval,
                    "year": timestamp.year,
                    "month": timestamp.month,
                    "day": timestamp.day,
                }
            )
        return pd.DataFrame(normalized_rows)

    def _validate(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Apply basic OHLCV sanity checks."""
        if frame.empty:
            return frame

        valid = frame[
            (frame["open"] >= 0)
            & (frame["high"] >= frame["open"])
            & (frame["high"] >= frame["close"])
            & (frame["low"] <= frame["open"])
            & (frame["low"] <= frame["close"])
            & (frame["low"] >= 0)
            & (frame["close"] >= 0)
            & (frame["volume"] >= 0)
        ]
        dropped = len(frame.index) - len(valid.index)
        if dropped > 0:
            logger.warning("Dropped %s invalid candle rows during validation", dropped)
        return valid

    @staticmethod
    def _atomic_write(frame: pd.DataFrame, path: Path) -> None:
        """Write parquet atomically to avoid partial partition files."""
        temp_path = path.with_suffix(".tmp.parquet")
        frame.to_parquet(temp_path, index=False)
        temp_path.replace(path)
