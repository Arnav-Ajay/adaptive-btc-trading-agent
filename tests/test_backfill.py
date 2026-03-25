"""Tests for backfill chunking helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from app.data.coinbase_client import CoinbaseClient
from app.ingestion.backfill import _chunk_span_for_limit, _parse_datetime


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
