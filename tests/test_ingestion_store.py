"""Tests for parquet-backed ingestion storage."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from app.ingestion.parquet_store import ParquetMarketDataStore
from app.utils.models import Candle


def test_write_candles_deduplicates_overlapping_rows(tmp_path) -> None:
    """Ensure overlapping fetch windows do not create duplicate persisted rows."""
    store = ParquetMarketDataStore(str(tmp_path))
    first_batch = [
        Candle(
            timestamp=datetime(2026, 3, 24, 12, 0, tzinfo=UTC),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
        ),
        Candle(
            timestamp=datetime(2026, 3, 24, 12, 1, tzinfo=UTC),
            open=100.5,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=12.0,
        ),
    ]
    second_batch = [
        Candle(
            timestamp=datetime(2026, 3, 24, 12, 1, tzinfo=UTC),
            open=100.5,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=12.0,
        ),
        Candle(
            timestamp=datetime(2026, 3, 24, 12, 2, tzinfo=UTC),
            open=101.0,
            high=103.0,
            low=100.5,
            close=102.0,
            volume=8.0,
        ),
    ]

    store.write_candles(symbol="BTC-USD", interval="1m", candles=first_batch)
    result = store.write_candles(symbol="BTC-USD", interval="1m", candles=second_batch)

    candles = store.load_recent_candles(symbol="BTC-USD", interval="1m", limit=10)
    assert len(candles) == 3
    assert candles[-1].timestamp == datetime(2026, 3, 24, 12, 2, tzinfo=UTC)
    assert result.rows_written == 1
    assert result.final_rows_persisted == 3


def test_write_candles_partitions_by_day(tmp_path) -> None:
    """Ensure candles land in the expected year/month/day partition."""
    store = ParquetMarketDataStore(str(tmp_path))
    store.write_candles(
        symbol="BTC-USD",
        interval="1m",
        candles=[
            Candle(
                timestamp=datetime(2026, 3, 24, 23, 59, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=5.0,
            )
        ],
    )

    partition_file = (
        tmp_path
        / "symbol=BTC-USD"
        / "interval=1m"
        / "year=2026"
        / "month=03"
        / "day=24"
        / "data.parquet"
    )
    assert partition_file.exists()


def test_write_daily_candles_partition_by_month(tmp_path) -> None:
    """Daily candles should be grouped into a month parquet file."""
    store = ParquetMarketDataStore(str(tmp_path))
    store.write_candles(
        symbol="BTC-USD",
        interval="1d",
        candles=[
            Candle(
                timestamp=datetime(2026, 3, 24, 0, 0, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=5.0,
            )
        ],
    )

    partition_file = (
        tmp_path
        / "symbol=BTC-USD"
        / "interval=1d"
        / "year=2026"
        / "month=03"
        / "data.parquet"
    )
    assert partition_file.exists()


def test_write_weekly_candles_partition_by_year(tmp_path) -> None:
    """Weekly candles should be grouped into a year parquet file."""
    store = ParquetMarketDataStore(str(tmp_path))
    store.write_candles(
        symbol="BTC-USD",
        interval="1week",
        candles=[
            Candle(
                timestamp=datetime(2026, 3, 23, 0, 0, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=5.0,
            )
        ],
    )

    partition_file = (
        tmp_path
        / "symbol=BTC-USD"
        / "interval=1week"
        / "year=2026"
        / "data.parquet"
    )
    assert partition_file.exists()


def test_write_monthly_candles_partition_by_year(tmp_path) -> None:
    """Monthly candles should be grouped into a year parquet file."""
    store = ParquetMarketDataStore(str(tmp_path))
    store.write_candles(
        symbol="BTC-USD",
        interval="1month",
        candles=[
            Candle(
                timestamp=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=5.0,
            )
        ],
    )

    partition_file = (
        tmp_path
        / "symbol=BTC-USD"
        / "interval=1month"
        / "year=2026"
        / "data.parquet"
    )
    assert partition_file.exists()


def test_load_candles_reads_legacy_daily_layout_for_derived_intervals(tmp_path) -> None:
    """Read path should fall back to the legacy day-partition layout until migrated."""
    store = ParquetMarketDataStore(str(tmp_path))
    legacy_partition = (
        tmp_path
        / "symbol=BTC-USD"
        / "interval=1d"
        / "year=2026"
        / "month=03"
        / "day=24"
    )
    legacy_partition.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "timestamp": int(datetime(2026, 3, 24, 0, 0, tzinfo=UTC).timestamp()),
                "datetime": datetime(2026, 3, 24, 0, 0, tzinfo=UTC),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 5.0,
                "symbol": "BTC-USD",
                "interval": "1d",
                "year": 2026,
                "month": 3,
                "day": 24,
            }
        ]
    ).to_parquet(legacy_partition / "data.parquet", index=False)

    candles = store.load_candles(symbol="BTC-USD", interval="1d", limit=None)

    assert len(candles) == 1
    assert candles[0].timestamp == datetime(2026, 3, 24, 0, 0, tzinfo=UTC)
