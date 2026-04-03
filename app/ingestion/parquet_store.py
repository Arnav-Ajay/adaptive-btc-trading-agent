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
_PARTITION_LEVELS_BY_INTERVAL: dict[str, tuple[str, ...]] = {
    "1m": ("year", "month", "day"),
    "10m": ("year", "month", "day"),
    "30m": ("year", "month", "day"),
    "1hr": ("year", "month", "day"),
    "1d": ("year", "month"),
    "1week": ("year",),
    "1month": ("year",),
}
_LEGACY_PARTITION_LEVELS_BY_INTERVAL: dict[str, tuple[str, ...]] = {
    "1d": ("year", "month", "day"),
    "1week": ("year", "month", "day"),
    "1month": ("year", "month", "day"),
}


@dataclass(slots=True)
class WriteResult:
    """Result of a parquet write operation."""

    rows_read_existing: int
    rows_received: int
    rows_written: int
    final_rows_persisted: int
    partitions_updated: int
    latest_timestamp: str | None


@dataclass(slots=True)
class CandleBounds:
    """Earliest and latest timestamps available for a stored interval."""

    earliest: datetime | None
    latest: datetime | None


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
        partition_columns = list(self._partition_levels(interval))

        for partition_key, partition_frame in frame.groupby(partition_columns, sort=True):
            partition_values = self._partition_value_map(partition_columns, partition_key)
            target_path = self._partition_file_path(symbol=symbol, interval=interval, partition_values=partition_values)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_files = self._legacy_partition_files_for_partition(
                symbol=symbol,
                interval=interval,
                partition_values=partition_values,
            )

            existing_frames: list[pd.DataFrame] = []
            if target_path.exists():
                existing_frames.append(pd.read_parquet(target_path))
            existing_frames.extend(pd.read_parquet(path) for path in legacy_files)

            if existing_frames:
                existing = pd.concat(existing_frames, ignore_index=True)
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
            self._delete_legacy_files(legacy_files)

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

    def load_candle_bounds(self, symbol: str, interval: str) -> CandleBounds:
        """Load the earliest and latest available timestamps for an interval."""
        earliest_file = self._boundary_partition_file(symbol=symbol, interval=interval, newest=False)
        latest_file = self._boundary_partition_file(symbol=symbol, interval=interval, newest=True)
        if earliest_file is None or latest_file is None:
            return CandleBounds(earliest=None, latest=None)

        earliest = self._boundary_timestamp(earliest_file, first=True)
        latest = self._boundary_timestamp(latest_file, first=False)
        return CandleBounds(earliest=earliest, latest=latest)

    def load_candles(self, symbol: str, interval: str, limit: int | None = None) -> list[Candle]:
        """Load candles from the partitioned parquet store with an optional row limit."""
        symbol_path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        if not symbol_path.exists():
            return []

        if limit is not None:
            parquet_files = self._recent_partition_files(symbol=symbol, interval=interval, limit=limit)
        else:
            parquet_files = self._partition_files_for_interval(symbol=symbol, interval=interval)
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
        interval_rows_per_partition = {
            "1m": 1440,
            "10m": 144,
            "30m": 48,
            "1hr": 24,
            "1d": 31,
            "1week": 53,
            "1month": 12,
        }
        rows_per_partition = interval_rows_per_partition.get(interval)
        if rows_per_partition is None:
            return self._partition_files_for_interval(symbol=symbol, interval=interval)

        estimated_partitions = max(3, (limit + rows_per_partition - 1) // rows_per_partition + 2)
        files: list[Path] = []
        for partition_values in self._recent_partition_value_maps(interval=interval, count=estimated_partitions):
            parquet_file = self._partition_file_path(symbol=symbol, interval=interval, partition_values=partition_values)
            if parquet_file.exists():
                files.append(parquet_file)
        if files:
            return files
        return self._partition_files_for_interval(symbol=symbol, interval=interval)

    def _partition_files_for_interval(self, symbol: str, interval: str) -> list[Path]:
        """Return partition parquet files ordered from newest to oldest for the active layout."""
        interval_path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        files = self._iter_partition_files_reverse(interval_path, levels=self._partition_levels(interval))
        if files:
            return files
        legacy_levels = _LEGACY_PARTITION_LEVELS_BY_INTERVAL.get(interval)
        if legacy_levels is None:
            return []
        return self._iter_partition_files_reverse(interval_path, levels=legacy_levels)

    def _partition_files_oldest_to_newest(self, symbol: str, interval: str) -> list[Path]:
        """Return partition parquet files ordered from oldest to newest."""
        return list(reversed(self._partition_files_for_interval(symbol=symbol, interval=interval)))

    def _boundary_partition_file(self, symbol: str, interval: str, *, newest: bool) -> Path | None:
        """Return the oldest or newest partition file without traversing the full tree."""
        interval_path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        file = self._walk_boundary_file(interval_path, levels=self._partition_levels(interval), newest=newest)
        if file is not None:
            return file
        legacy_levels = _LEGACY_PARTITION_LEVELS_BY_INTERVAL.get(interval)
        if legacy_levels is None:
            return None
        return self._walk_boundary_file(interval_path, levels=legacy_levels, newest=newest)

    def _walk_boundary_file(self, root: Path, *, levels: tuple[str, ...], newest: bool) -> Path | None:
        """Walk a single oldest/newest branch of the partition tree to a parquet file."""
        if not root.exists():
            return None

        current = root
        remaining_levels = levels
        while remaining_levels:
            children = self._sorted_partition_dirs(current)
            if not children:
                return None
            current = children[0] if newest else children[-1]
            remaining_levels = remaining_levels[1:]

        parquet_file = current / "data.parquet"
        return parquet_file if parquet_file.exists() else None

    def _iter_partition_files_reverse(self, interval_path: Path, levels: tuple[str, ...]) -> list[Path]:
        """Return partition parquet files ordered from newest to oldest for a partition depth."""
        if not interval_path.exists():
            return []

        def walk(root: Path, remaining_levels: tuple[str, ...]) -> list[Path]:
            if not remaining_levels:
                parquet_file = root / "data.parquet"
                return [parquet_file] if parquet_file.exists() else []

            nested_files: list[Path] = []
            for child in self._sorted_partition_dirs(root):
                nested_files.extend(walk(child, remaining_levels[1:]))
            return nested_files

        return walk(interval_path, levels)

    def _recent_partition_value_maps(self, interval: str, count: int) -> list[dict[str, int]]:
        """Build recent partition keys in newest-to-oldest order for an interval."""
        values: list[dict[str, int]] = []
        today = datetime.now(UTC).date()
        if self._partition_levels(interval) == ("year", "month", "day"):
            for offset in range(count):
                current = today - timedelta(days=offset)
                values.append({"year": current.year, "month": current.month, "day": current.day})
            return values

        if self._partition_levels(interval) == ("year", "month"):
            current_year = today.year
            current_month = today.month
            for offset in range(count):
                year = current_year
                month = current_month - offset
                while month <= 0:
                    year -= 1
                    month += 12
                values.append({"year": year, "month": month})
            return values

        current_year = today.year
        for offset in range(count):
            values.append({"year": current_year - offset})
        return values

    def _legacy_partition_files_for_partition(
        self,
        symbol: str,
        interval: str,
        partition_values: dict[str, int],
    ) -> list[Path]:
        """Return matching legacy day-partition files for intervals whose layout changed."""
        legacy_levels = _LEGACY_PARTITION_LEVELS_BY_INTERVAL.get(interval)
        if legacy_levels is None:
            return []

        interval_path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        if not interval_path.exists():
            return []

        files: list[Path] = []
        year_dir = interval_path / f"year={partition_values['year']:04d}"
        if not year_dir.exists():
            return []

        if legacy_levels == ("year", "month", "day"):
            months = [partition_values["month"]] if "month" in partition_values else [
                self._partition_sort_key(path) for path in self._sorted_partition_dirs(year_dir)
            ]
            for month in months:
                month_dir = year_dir / f"month={month:02d}"
                if not month_dir.exists():
                    continue
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

    def _partition_levels(self, interval: str) -> tuple[str, ...]:
        """Return the directory partition levels for an interval."""
        return _PARTITION_LEVELS_BY_INTERVAL.get(interval, ("year", "month", "day"))

    @staticmethod
    def _partition_value_map(columns: list[str], partition_key: object) -> dict[str, int]:
        """Normalize pandas groupby keys into a named partition-value mapping."""
        if not isinstance(partition_key, tuple):
            partition_key = (partition_key,)
        return {column: int(value) for column, value in zip(columns, partition_key)}

    def _partition_file_path(self, symbol: str, interval: str, partition_values: dict[str, int]) -> Path:
        """Build the partition file path for a given date."""
        path = self.root_path / f"symbol={symbol}" / f"interval={interval}"
        for level in self._partition_levels(interval):
            value = partition_values[level]
            path = path / f"{level}={value:02d}" if level in {"month", "day"} else path / f"{level}={value:04d}"
        return path / "data.parquet"

    @staticmethod
    def _delete_legacy_files(paths: list[Path]) -> None:
        """Remove migrated legacy files and empty parent directories."""
        for path in paths:
            path.unlink(missing_ok=True)
            for parent in path.parents:
                if parent.name == "":
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break

    @staticmethod
    def _boundary_timestamp(path: Path, *, first: bool) -> datetime | None:
        """Read the earliest or latest timestamp from a parquet partition."""
        frame = pd.read_parquet(path, columns=["datetime"])
        if frame.empty:
            return None
        value = frame.iloc[0 if first else -1]["datetime"]
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        return value.astimezone(UTC) if isinstance(value, datetime) and value.tzinfo else value

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
