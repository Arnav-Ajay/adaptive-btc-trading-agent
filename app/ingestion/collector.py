# app/ingestion/collector.py
"""Coinbase market data collection orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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

    def collect_once(self) -> CollectionResult:
        """Run a single ingestion cycle with retries and persisted state."""
        started_at_dt = datetime.now(UTC)
        started_at = started_at_dt.replace(microsecond=0).isoformat()
        records = self._fetch_with_retries()
        write_result = self.store.write_candles(
            symbol=self.config.trading.symbol,
            interval=self.config.ingestion.interval,
            candles=records,
        )
        derived_results = self.preprocessor.build_all(
            symbol=self.config.trading.symbol,
            source_interval=self.config.ingestion.interval,
        )
        ended_at_dt = datetime.now(UTC)
        duration_ms = int((ended_at_dt - started_at_dt).total_seconds() * 1000)

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
        last_error: Exception | None = None
        for attempt in range(1, self.config.ingestion.max_retries + 1):
            try:
                return self._fetch_window()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Ingestion fetch attempt %s/%s failed: %s",
                    attempt,
                    self.config.ingestion.max_retries,
                    exc,
                )
                if attempt < self.config.ingestion.max_retries:
                    time.sleep(self.config.ingestion.retry_delay_seconds)

        assert last_error is not None
        raise last_error

    def _fetch_window(self) -> list[Candle]:
        """Fetch an overlapping window of candles from Coinbase."""
        end_at = datetime.now(UTC)
        start_at = end_at - timedelta(minutes=self.config.ingestion.overlap_minutes)
        logger.info(
            "Fetching Coinbase candles for symbol=%s interval=%s start=%s end=%s overlap_minutes=%s",
            self.config.trading.symbol,
            self.config.ingestion.interval,
            start_at.isoformat(),
            end_at.isoformat(),
            self.config.ingestion.overlap_minutes,
        )
        return self.client.fetch_ohlcv(
            symbol=self.config.trading.symbol,
            interval=self.config.ingestion.interval,
            start=start_at,
            end=end_at,
            limit=self.config.ingestion.fetch_limit,
        )
