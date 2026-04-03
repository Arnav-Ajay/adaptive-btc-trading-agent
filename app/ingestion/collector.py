# app/ingestion/collector.py
"""Coinbase market data collection orchestration."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config.schema import AppConfig
from app.data.coinbase_client import CoinbaseClient
from app.ingestion.parquet_store import ParquetMarketDataStore, WriteResult
from app.ingestion.preprocessor import MarketDataPreprocessor
from app.ingestion.state_store import IngestionState, StateStore
from app.utils.models import Candle


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CollectionResult:
    """High-level result from a collection cycle."""

    success: bool
    write_result: WriteResult
    started_at: str
    ended_at: str
    duration_ms: int


class CoinbaseIngestionService:
    """Fetch candles from Coinbase and persist them to partitioned parquet."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the ingestion service."""
        self.config = config
        self.client = CoinbaseClient(
            api_key=config.env.get("COINBASE_API_KEY", ""),
            api_secret=config.env.get("COINBASE_API_SECRET", ""),
        )
        self.store = ParquetMarketDataStore(config.data.data_lake_path)
        self.preprocessor = MarketDataPreprocessor(self.store)
        self.state_store = StateStore(config.ingestion.state_path)
        state_dir = Path(config.data.data_lake_path) / "state" / "ingestion"
        self.gap_audit_path = state_dir / "ingestion_gap_audit.json"
        self.gap_events_path = state_dir / "ingestion_gap_events.jsonl"

    def collect_once(self) -> CollectionResult:
        """Run a single ingestion cycle with retries and persisted state."""
        started_at_dt = datetime.now(UTC)
        started_at = started_at_dt.replace(microsecond=0).isoformat()
        records = self._fetch_with_retries()
        source_gaps = self._detect_gaps(records)
        if source_gaps:
            logger.warning("Detected %s source gaps in fetched Coinbase candles", len(source_gaps))
        write_result = self.store.write_candles(
            symbol=self.config.trading.symbol,
            interval=self.config.ingestion.interval,
            candles=records,
        )
        lake_gaps = self._detect_recent_lake_gaps()
        if lake_gaps:
            logger.warning("Detected %s recent lake gaps after canonical 1m write", len(lake_gaps))
        derived_results = self.preprocessor.build_all(
            symbol=self.config.trading.symbol,
            source_interval=self.config.ingestion.interval,
        )
        ended_at_dt = datetime.now(UTC)
        duration_ms = int((ended_at_dt - started_at_dt).total_seconds() * 1000)
        self._persist_gap_audit(
            recorded_at=ended_at_dt.replace(microsecond=0).isoformat(),
            source_gaps=source_gaps,
            lake_gaps=lake_gaps,
        )

        state = IngestionState(
            last_successful_run_at=ended_at_dt.replace(microsecond=0).isoformat(),
            last_ingested_timestamp=write_result.latest_timestamp,
            rows_written=write_result.rows_written,
            provider=self.config.ingestion.provider,
            metadata={
                "rows_received": write_result.rows_received,
                "rows_read_existing": write_result.rows_read_existing,
                "final_rows_persisted": write_result.final_rows_persisted,
                "partitions_updated": write_result.partitions_updated,
                "duration_ms": duration_ms,
                "symbol": self.config.trading.symbol,
                "interval": self.config.ingestion.interval,
                "source_gap_count": len(source_gaps),
                "lake_gap_count": len(lake_gaps),
                "derived_intervals": [
                    {
                        "interval": result.interval,
                        "rows_written": result.write_result.rows_written,
                        "final_rows_persisted": result.write_result.final_rows_persisted,
                    }
                    for result in derived_results
                ],
            },
        )
        self.state_store.save(state)

        ended_at = ended_at_dt.replace(microsecond=0).isoformat()
        logger.info(
            (
                "Ingestion cycle complete: symbol=%s interval=%s received=%s "
                "new_rows=%s final_rows=%s existing_rows=%s partitions=%s latest=%s "
                "derived=%s duration_ms=%s"
            ),
            self.config.trading.symbol,
            self.config.ingestion.interval,
            write_result.rows_received,
            write_result.rows_written,
            write_result.final_rows_persisted,
            write_result.rows_read_existing,
            write_result.partitions_updated,
            write_result.latest_timestamp,
            ",".join(result.interval for result in derived_results) if derived_results else "none",
            duration_ms,
        )
        return CollectionResult(
            success=True,
            write_result=write_result,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
        )

    def _fetch_with_retries(self) -> list[Candle]:
        """Fetch candles from Coinbase with bounded retries."""
        return self._fetch_window()

    def _fetch_window(self) -> list[Candle]:
        """Fetch an overlapping window of candles from Coinbase."""
        end_at = datetime.now(UTC)
        start_at = self._determine_start_at(end_at=end_at)
        interval_seconds = CoinbaseClient.interval_seconds(self.config.ingestion.interval)
        step = timedelta(seconds=interval_seconds)
        chunk_span = timedelta(seconds=interval_seconds * self.config.ingestion.fetch_limit)
        cursor = start_at
        candles: list[Candle] = []

        logger.info(
            "Fetching Coinbase candles for symbol=%s interval=%s start=%s end=%s overlap_minutes=%s",
            self.config.trading.symbol,
            self.config.ingestion.interval,
            start_at.isoformat(),
            end_at.isoformat(),
            self.config.ingestion.overlap_minutes,
        )
        while cursor < end_at:
            chunk_end = min(cursor + chunk_span, end_at)
            chunk = self._fetch_chunk_with_retries(start_at=cursor, end_at=chunk_end)
            if chunk:
                candles.extend(chunk)
                cursor = chunk[-1].timestamp.astimezone(UTC) + step
            else:
                cursor = chunk_end

        deduped: dict[datetime, Candle] = {}
        for candle in candles:
            deduped[candle.timestamp.astimezone(UTC)] = candle
        return [deduped[timestamp] for timestamp in sorted(deduped)]

    def _detect_gaps(self, candles: list[Candle]) -> list[dict[str, object]]:
        """Detect missing timestamps within a candle sequence."""
        if len(candles) < 2:
            return []
        step = timedelta(seconds=CoinbaseClient.interval_seconds(self.config.ingestion.interval))
        gaps: list[dict[str, object]] = []
        normalized = sorted((candle.timestamp.astimezone(UTC) for candle in candles))
        for previous, current in zip(normalized, normalized[1:]):
            gap = current - previous
            if gap <= step:
                continue
            missing_count = int(gap.total_seconds() // step.total_seconds()) - 1
            gaps.append(
                {
                    "start": (previous + step).replace(microsecond=0).isoformat(),
                    "end": (current - step).replace(microsecond=0).isoformat(),
                    "missing_count": missing_count,
                }
            )
        return gaps

    def _detect_recent_lake_gaps(self) -> list[dict[str, object]]:
        """Detect recent continuity gaps in the canonical parquet lake."""
        lookback_candles = max(self.config.ingestion.schedule_minutes * 12, 360)
        candles = self.store.load_candles(
            symbol=self.config.trading.symbol,
            interval=self.config.ingestion.interval,
            limit=lookback_candles,
        )
        return self._detect_gaps(candles)

    def _persist_gap_audit(
        self,
        recorded_at: str,
        source_gaps: list[dict[str, object]],
        lake_gaps: list[dict[str, object]],
    ) -> None:
        """Persist a latest summary and append structured gap events."""
        self.gap_audit_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "recorded_at": recorded_at,
            "symbol": self.config.trading.symbol,
            "interval": self.config.ingestion.interval,
            "source_gap_count": len(source_gaps),
            "lake_gap_count": len(lake_gaps),
            "source_gaps": source_gaps,
            "lake_gaps": lake_gaps,
        }
        temp_path = self.gap_audit_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
        temp_path.replace(self.gap_audit_path)

        if not source_gaps and not lake_gaps:
            return

        with self.gap_events_path.open("a", encoding="utf-8") as handle:
            for kind, gaps in (("source_gap", source_gaps), ("lake_gap", lake_gaps)):
                for gap in gaps:
                    handle.write(
                        json.dumps(
                            {
                                "recorded_at": recorded_at,
                                "kind": kind,
                                "symbol": self.config.trading.symbol,
                                "interval": self.config.ingestion.interval,
                                **gap,
                            }
                        )
                        + "\n"
                    )

    def _determine_start_at(self, end_at: datetime) -> datetime:
        """Choose the fetch start time using overlap and persisted ingestion state."""
        default_start = end_at - timedelta(minutes=self.config.ingestion.overlap_minutes)
        state = self.state_store.load()
        if not state.last_ingested_timestamp:
            return default_start
        try:
            last_ingested = datetime.fromisoformat(state.last_ingested_timestamp).astimezone(UTC)
        except ValueError:
            logger.warning("Unable to parse last_ingested_timestamp=%s", state.last_ingested_timestamp)
            return default_start
        step = timedelta(seconds=CoinbaseClient.interval_seconds(self.config.ingestion.interval))
        state_based_start = last_ingested - step
        if state_based_start < default_start:
            logger.warning(
                "Detected ingestion gap beyond overlap window; expanding fetch start from %s to %s",
                default_start.isoformat(),
                state_based_start.isoformat(),
            )
            return state_based_start
        return default_start

    def _fetch_chunk_with_retries(self, start_at: datetime, end_at: datetime) -> list[Candle]:
        """Fetch one Coinbase chunk with bounded retries."""
        last_error: Exception | None = None
        for attempt in range(1, self.config.ingestion.max_retries + 1):
            try:
                return self.client.fetch_ohlcv(
                    symbol=self.config.trading.symbol,
                    interval=self.config.ingestion.interval,
                    start=start_at,
                    end=end_at,
                    limit=self.config.ingestion.fetch_limit,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Ingestion fetch attempt %s/%s failed for chunk start=%s end=%s: %s",
                    attempt,
                    self.config.ingestion.max_retries,
                    start_at.isoformat(),
                    end_at.isoformat(),
                    exc,
                )
                if attempt < self.config.ingestion.max_retries:
                    time.sleep(self.config.ingestion.retry_delay_seconds)

        assert last_error is not None
        raise last_error
