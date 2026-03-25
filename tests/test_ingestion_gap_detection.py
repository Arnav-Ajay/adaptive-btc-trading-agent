from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config.settings import load_config
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.scheduler.collector_runner import _find_recent_gap_start, _has_bootstrap_data
from app.utils.models import Candle


def test_find_recent_gap_start_detects_missing_one_minute_gap(tmp_path) -> None:
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    store = ParquetMarketDataStore(str(tmp_path))
    start = datetime(2026, 3, 25, 10, 0, tzinfo=UTC)
    candles: list[Candle] = []
    for minute in range(6):
        if minute == 3:
            continue
        timestamp = start + timedelta(minutes=minute)
        candles.append(
            Candle(
                timestamp=timestamp,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1.0,
            )
        )
    store.write_candles(symbol="BTC-USD", interval="1m", candles=candles)

    gap_start = _find_recent_gap_start(config)

    assert gap_start == datetime(2026, 3, 25, 10, 3, tzinfo=UTC)


def test_has_bootstrap_data_detects_existing_canonical_candles(tmp_path) -> None:
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    store = ParquetMarketDataStore(str(tmp_path))
    store.write_candles(
        symbol="BTC-USD",
        interval="1m",
        candles=[
            Candle(
                timestamp=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1.0,
            )
        ],
    )

    assert _has_bootstrap_data(config) is True
