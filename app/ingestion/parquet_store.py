# app/ingestion/parquet_store.py
"""Partitioned parquet storage for market data."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.utils.models import Candle


logger = logging.getLogger(__name__)
_PARTITION_VALUE_RE = re.compile(r"^[^=]+=([0-9]+)$")


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
        return self.load_candles(symbol=symbol, interval=interval, limit=limit)

    def load_candles(self, symbol: str, interval: str, limit: int | None = None) -> list[Candle]:
        """Load candles from the partitioned parquet store with an optional row limit."""
        symbol_path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        if not symbol_path.exists():
            return []

        if limit is not None:
            parquet_files = self._recent_partition_files(symbol=symbol, interval=interval, limit=limit)
        else:
            parquet_files = list(self._iter_partition_files_reverse(symbol_path))
        if not parquet_files:
            return []

        frames: list[pd.DataFrame] = []
        for parquet_file in parquet_files:
            frames.append(pd.read_parquet(parquet_file))
            combined_rows = sum(len(frame.index) for frame in frames)
            if limit is not None and combined_rows >= limit:
                break

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
        recent = combined.tail(limit) if limit is not None else combined
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

    def _recent_partition_files(self, symbol: str, interval: str, limit: int) -> list[Path]:
        """Return likely-recent partition files without scanning the whole interval tree."""
        interval_rows_per_day = {
            "1m": 1440,
            "10m": 144,
            "30m": 48,
            "1hr": 24,
            "1d": 1,
        }
        rows_per_day = interval_rows_per_day.get(interval)
        if rows_per_day is None:
            return list(self._iter_partition_files_reverse(self.root_path / f"symbol={symbol}" / f"interval={interval}"))

        estimated_days = max(3, (limit + rows_per_day - 1) // rows_per_day + 2)
        files: list[Path] = []
        current_day = datetime.now(UTC).date()
        for offset in range(estimated_days):
            candidate_day = current_day - timedelta(days=offset)
            parquet_file = self._partition_file_path(
                symbol=symbol,
                interval=interval,
                year=candidate_day.year,
                month=candidate_day.month,
                day=candidate_day.day,
            )
            if parquet_file.exists():
                files.append(parquet_file)
        if files:
            return files
        return list(self._iter_partition_files_reverse(self.root_path / f"symbol={symbol}" / f"interval={interval}"))

    def _iter_partition_files_reverse(self, interval_path: Path) -> list[Path]:
        """Return partition parquet files ordered from newest to oldest."""
        files: list[Path] = []
        for year_dir in self._sorted_partition_dirs(interval_path):
            for month_dir in self._sorted_partition_dirs(year_dir):
                for day_dir in self._sorted_partition_dirs(month_dir):
                    parquet_file = day_dir / "data.parquet"
                    if parquet_file.exists():
                        files.append(parquet_file)
        return files

    def _sorted_partition_dirs(self, root: Path) -> list[Path]:
        """Sort partition directories in descending numeric partition order."""
        partition_dirs = [path for path in root.iterdir() if path.is_dir()]
        return sorted(partition_dirs, key=self._partition_sort_key, reverse=True)

    @staticmethod
    def _partition_sort_key(path: Path) -> int:
        """Extract the numeric suffix from partition directory names like year=2026."""
        match = _PARTITION_VALUE_RE.match(path.name)
        if match is None:
            return -1
        return int(match.group(1))

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
