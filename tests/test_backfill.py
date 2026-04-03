"""Tests for backfill chunking helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.data.coinbase_client import CoinbaseClient
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.ingestion.backfill import _chunk_span_for_limit, _parse_datetime, run_backfill
from app.ingestion.state_store import StateStore
from app.utils.models import Candle


def test_parse_datetime_normalizes_to_utc() -> None:
    """Backfill datetime parsing should produce UTC-aware timestamps."""
    parsed = _parse_datetime("2026-01-01T00:00:00Z")
    assert parsed == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_coinbase_interval_seconds_for_one_minute() -> None:
    """Backfill chunk sizing depends on interval-to-seconds resolution."""
    assert CoinbaseClient.interval_seconds("1m") == 60


def test_chunk_span_for_limit_avoids_off_by_one_gap() -> None:
    """A 350-candle one-minute chunk should span 349 minutes, not 350."""
    span = _chunk_span_for_limit(interval_seconds=60, limit=350)
    assert int(span.total_seconds()) == 349 * 60


def test_run_backfill_uses_main_ingestion_state_path_by_default(tmp_path, monkeypatch) -> None:
    config = SimpleNamespace(
        env={},
        data=SimpleNamespace(data_lake_path=str(tmp_path)),
        ingestion=SimpleNamespace(state_path=str(tmp_path / "state" / "coinbase_btc_usd_1m.json")),
        logging=SimpleNamespace(level="INFO"),
    )

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        @staticmethod
        def interval_seconds(interval: str) -> int:
            assert interval == "1m"
            return 60

        def fetch_ohlcv(self, **kwargs):
            return [
                Candle(
                    timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1.0,
                )
            ]

    class FakePreprocessor:
        def __init__(self, store) -> None:
            self.store = store

        def build_all(self, symbol: str, source_interval: str):
            return []

    monkeypatch.setattr("app.ingestion.backfill.load_config", lambda: config)
    monkeypatch.setattr("app.ingestion.backfill.CoinbaseClient", FakeClient)
    monkeypatch.setattr("app.ingestion.backfill.MarketDataPreprocessor", FakePreprocessor)

    run_backfill(
        start_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        symbol="BTC-USD",
        interval="1m",
        limit=350,
        sleep_seconds=0,
    )

    state = StateStore(config.ingestion.state_path).load()
    assert state.last_successful_run_at is not None
    assert state.provider == "coinbase_backfill"


def test_run_backfill_reuses_existing_source_without_coinbase_fetch(tmp_path, monkeypatch) -> None:
    """Backfill should skip Coinbase fetch when local source data fully covers the requested window."""
    config = SimpleNamespace(
        env={},
        data=SimpleNamespace(data_lake_path=str(tmp_path)),
        ingestion=SimpleNamespace(state_path=str(tmp_path / "state" / "coinbase_btc_usd_1m.json")),
        logging=SimpleNamespace(level="INFO"),
    )
    store = ParquetMarketDataStore(str(tmp_path))
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles = [
        Candle(
            timestamp=start + timedelta(minutes=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1.0,
        )
        for index in range(5)
    ]
    store.write_candles(symbol="BTC-USD", interval="1m", candles=candles)

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Coinbase client should not be created when reusing local source data")

    class FakePreprocessor:
        def __init__(self, store) -> None:
            self.store = store

        def build_all(self, symbol: str, source_interval: str):
            assert symbol == "BTC-USD"
            assert source_interval == "1m"
            return []

    monkeypatch.setattr("app.ingestion.backfill.load_config", lambda: config)
    monkeypatch.setattr("app.ingestion.backfill.CoinbaseClient", FakeClient)
    monkeypatch.setattr("app.ingestion.backfill.MarketDataPreprocessor", FakePreprocessor)

    result = run_backfill(
        start_at=start,
        end_at=start + timedelta(minutes=4),
        symbol="BTC-USD",
        interval="1m",
        limit=350,
        sleep_seconds=0,
        reuse_existing_source=True,
    )

    assert result.api_calls == 0
    assert result.rows_written == 0
    state = StateStore(config.ingestion.state_path).load()
    assert state.provider == "local_rebuild"
