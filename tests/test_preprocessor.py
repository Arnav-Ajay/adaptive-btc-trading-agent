"""Tests for derived interval preprocessing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ingestion.parquet_store import ParquetMarketDataStore
from app.ingestion.preprocessor import DERIVED_INTERVAL_RULES, MarketDataPreprocessor
from app.utils.models import Candle


def _build_candles(start: datetime, count: int) -> list[Candle]:
    """Create sequential 1m candles for resampling tests."""
    candles: list[Candle] = []
    for index in range(count):
        base = 100 + index
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=float(base),
                high=float(base + 2),
                low=float(base - 1),
                close=float(base + 1),
                volume=1.0,
            )
        )
    return candles


def test_resample_to_10m_aggregates_ohlcv_correctly() -> None:
    """10m resampling should use standard OHLCV aggregation."""
    candles = _build_candles(datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 10)
    derived = MarketDataPreprocessor._resample(candles, DERIVED_INTERVAL_RULES["10m"])
    assert len(derived) == 1
    candle = derived[0]
    assert candle.timestamp == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert candle.open == 100.0
    assert candle.high == 111.0
    assert candle.low == 99.0
    assert candle.close == 110.0
    assert candle.volume == 10.0


def test_build_all_writes_requested_intervals(tmp_path) -> None:
    """Preprocessor should write all configured derived interval folders."""
    store = ParquetMarketDataStore(str(tmp_path))
    source_candles = _build_candles(datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 60 * 24 * 10)
    store.write_candles(symbol="BTC-USD", interval="1m", candles=source_candles)
    preprocessor = MarketDataPreprocessor(store)

    results = preprocessor.build_all(symbol="BTC-USD", source_interval="1m")

    assert [result.interval for result in results] == list(DERIVED_INTERVAL_RULES.keys())
    for interval in DERIVED_INTERVAL_RULES:
        interval_path = tmp_path / "symbol=BTC-USD" / f"interval={interval}"
        assert interval_path.exists()
