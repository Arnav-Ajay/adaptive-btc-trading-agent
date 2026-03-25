from __future__ import annotations

from datetime import UTC, datetime

from app.config.settings import load_config
from app.ingestion.collector import CoinbaseIngestionService
from app.ingestion.state_store import IngestionState


def test_determine_start_at_uses_overlap_when_state_missing() -> None:
    config = load_config()
    service = CoinbaseIngestionService(config=config)
    service.state_store.load = lambda: IngestionState()  # type: ignore[method-assign]
    end_at = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)

    start_at = service._determine_start_at(end_at=end_at)

    assert start_at == datetime(2026, 3, 25, 10, 30, tzinfo=UTC)


def test_determine_start_at_expands_when_gap_exceeds_overlap() -> None:
    config = load_config()
    service = CoinbaseIngestionService(config=config)
    service.state_store.load = lambda: IngestionState(  # type: ignore[method-assign]
        last_ingested_timestamp="2026-03-25T10:00:00+00:00"
    )
    end_at = datetime(2026, 3, 25, 12, 38, tzinfo=UTC)

    start_at = service._determine_start_at(end_at=end_at)

    assert start_at == datetime(2026, 3, 25, 9, 59, tzinfo=UTC)

