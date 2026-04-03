"""One-off and catch-up backfill for Coinbase candle data."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config.settings import load_config
from app.data.coinbase_client import CoinbaseClient
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.ingestion.preprocessor import MarketDataPreprocessor
from app.ingestion.state_store import IngestionState, StateStore
from app.monitoring.logger import configure_logging
from app.utils.models import Candle


logger = logging.getLogger(__name__)


DEFAULT_BACKFILL_START = datetime(2026, 1, 1, tzinfo=UTC)
MAX_COINBASE_CANDLES_PER_CALL = 350


@dataclass(slots=True)
class BackfillResult:
    """Summary of a backfill run."""

    api_calls: int
    candles_received: int
    rows_written: int
    chunks_with_data: int
    partitions_touched: int
    last_candle_timestamp: str | None
    start_at: str
    end_at: str


def _chunk_span_for_limit(interval_seconds: int, limit: int) -> timedelta:
    """Return a chunk span that yields at most `limit` candles inclusively."""
    if limit <= 1:
        return timedelta(seconds=max(interval_seconds, 1))
    return timedelta(seconds=interval_seconds * (limit - 1))


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime into UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the backfill script."""
    parser = argparse.ArgumentParser(description="Backfill Coinbase candle data into the parquet lake")
    parser.add_argument("--start", default=DEFAULT_BACKFILL_START.isoformat(), help="ISO 8601 UTC start time")
    parser.add_argument("--end", default=None, help="ISO 8601 UTC end time; defaults to now")
    parser.add_argument("--symbol", default=None, help="Override trading symbol")
    parser.add_argument("--interval", default=None, help="Override ingestion interval")
    parser.add_argument("--limit", type=int, default=MAX_COINBASE_CANDLES_PER_CALL, help="Max candles per Coinbase call")
    parser.add_argument("--sleep-seconds", type=float, default=0.2, help="Sleep between Coinbase calls")
    parser.add_argument("--state-path", default=None, help="Optional path for backfill run state")
    parser.add_argument(
        "--reuse-existing-source",
        action="store_true",
        help="Skip Coinbase fetch when local source interval data already exists and rebuild from local parquet only",
    )
    return parser


def _existing_source_state(
    store: ParquetMarketDataStore,
    *,
    symbol: str,
    interval: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> tuple[bool, bool, str | None]:
    """Return whether local source candles exist and whether they cover the requested window."""
    candles = store.load_candles(symbol=symbol, interval=interval, limit=None)
    if not candles:
        return False, False, None

    first_timestamp = candles[0].timestamp.astimezone(UTC)
    last_timestamp = candles[-1].timestamp.astimezone(UTC)
    last_timestamp_iso = last_timestamp.replace(microsecond=0).isoformat()
    if start_at is None or end_at is None:
        return True, False, last_timestamp_iso
    covers_window = first_timestamp <= start_at.astimezone(UTC) and last_timestamp >= end_at.astimezone(UTC)
    return True, covers_window, last_timestamp_iso


def run_backfill(
    start_at: datetime,
    end_at: datetime,
    symbol: str,
    interval: str,
    limit: int,
    sleep_seconds: float,
    state_path: str | None = None,
    reuse_existing_source: bool = False,
) -> BackfillResult:
    """Run a backfill from start time to end time inclusive."""
    config = load_config()
    store = ParquetMarketDataStore(config.data.data_lake_path)
    preprocessor = MarketDataPreprocessor(store)
    cursor = start_at.astimezone(UTC)
    hard_end = end_at.astimezone(UTC)
    backfill_state_path = state_path or config.ingestion.state_path
    state_store = StateStore(backfill_state_path)

    api_calls = 0
    candles_received = 0
    rows_written = 0
    chunks_with_data = 0
    partitions_touched = 0
    last_candle_timestamp: str | None = None
    provider = "coinbase_backfill"

    logger.info(
        "Starting backfill symbol=%s interval=%s start=%s end=%s limit=%s state_path=%s reuse_existing_source=%s",
        symbol,
        interval,
        cursor.isoformat(),
        hard_end.isoformat(),
        limit,
        backfill_state_path,
        reuse_existing_source,
    )

    has_existing_source = False
    has_local_coverage = False
    if reuse_existing_source:
        has_existing_source, has_local_coverage, last_candle_timestamp = _existing_source_state(
            store,
            symbol=symbol,
            interval=interval,
            start_at=start_at,
            end_at=end_at,
        )
        if has_existing_source:
            provider = "local_rebuild"
            logger.info(
                "Skipping Coinbase fetch because local %s candles already exist; local coverage for %s -> %s is %s",
                interval,
                cursor.isoformat(),
                hard_end.isoformat(),
                has_local_coverage,
            )

    if not has_existing_source:
        client = CoinbaseClient(
            api_key=config.env.get("COINBASE_API_KEY", ""),
            api_secret=config.env.get("COINBASE_API_SECRET", ""),
        )
        interval_seconds = CoinbaseClient.interval_seconds(interval)
        chunk_span = _chunk_span_for_limit(interval_seconds=interval_seconds, limit=limit)
        step = timedelta(seconds=interval_seconds)

        while cursor < hard_end:
            window_end = min(cursor + chunk_span, hard_end)
            logger.info(
                "Backfill chunk fetch symbol=%s interval=%s start=%s end=%s",
                symbol,
                interval,
                cursor.isoformat(),
                window_end.isoformat(),
            )
            candles = client.fetch_ohlcv(
                symbol=symbol,
                interval=interval,
                start=cursor,
                end=window_end,
                limit=limit,
            )
            api_calls += 1
            candles_received += len(candles)

            if candles:
                write_result = store.write_candles(symbol=symbol, interval=interval, candles=candles)
                rows_written += write_result.rows_written
                chunks_with_data += 1
                partitions_touched += write_result.partitions_updated
                last_candle_timestamp = write_result.latest_timestamp
                last_candle = candles[-1].timestamp.astimezone(UTC)
                cursor = last_candle + step
                logger.info(
                    (
                        "Backfill chunk complete symbol=%s interval=%s received=%s new_rows=%s "
                        "partitions=%s latest=%s next_cursor=%s"
                    ),
                    symbol,
                    interval,
                    len(candles),
                    write_result.rows_written,
                    write_result.partitions_updated,
                    write_result.latest_timestamp,
                    cursor.isoformat(),
                )
            else:
                cursor = window_end
                logger.warning(
                    "Backfill chunk returned no candles symbol=%s interval=%s advancing_to=%s",
                    symbol,
                    interval,
                    cursor.isoformat(),
                )

            if cursor < hard_end and sleep_seconds > 0:
                time.sleep(sleep_seconds)

    completed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    derived_results = preprocessor.build_all(symbol=symbol, source_interval=interval)
    if last_candle_timestamp is None:
        _, _, last_candle_timestamp = _existing_source_state(
            store,
            symbol=symbol,
            interval=interval,
            start_at=start_at,
            end_at=end_at,
        )
    state_store.save(
        IngestionState(
            last_successful_run_at=completed_at,
            last_ingested_timestamp=last_candle_timestamp,
            rows_written=rows_written,
            provider=provider,
            metadata={
                "api_calls": api_calls,
                "candles_received": candles_received,
                "chunks_with_data": chunks_with_data,
                "partitions_touched": partitions_touched,
                "symbol": symbol,
                "interval": interval,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "reuse_existing_source": reuse_existing_source,
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
    )

    logger.info(
        (
            "Backfill complete symbol=%s interval=%s provider=%s api_calls=%s candles_received=%s "
            "new_rows=%s chunks_with_data=%s partitions_touched=%s last_candle=%s derived=%s"
        ),
        symbol,
        interval,
        provider,
        api_calls,
        candles_received,
        rows_written,
        chunks_with_data,
        partitions_touched,
        last_candle_timestamp,
        ",".join(result.interval for result in derived_results) if derived_results else "none",
    )
    return BackfillResult(
        api_calls=api_calls,
        candles_received=candles_received,
        rows_written=rows_written,
        chunks_with_data=chunks_with_data,
        partitions_touched=partitions_touched,
        last_candle_timestamp=last_candle_timestamp,
        start_at=start_at.isoformat(),
        end_at=end_at.isoformat(),
    )


def main() -> None:
    """CLI entrypoint for Coinbase candle backfill."""
    args = _build_argument_parser().parse_args()
    config = load_config()
    configure_logging(config.logging.level, service_name="ingestion")

    start_at = _parse_datetime(args.start)
    end_at = _parse_datetime(args.end) if args.end else datetime.now(UTC)
    symbol = args.symbol or config.trading.symbol
    interval = args.interval or config.ingestion.interval

    result = run_backfill(
        start_at=start_at,
        end_at=end_at,
        symbol=symbol,
        interval=interval,
        limit=min(args.limit, MAX_COINBASE_CANDLES_PER_CALL),
        sleep_seconds=args.sleep_seconds,
        state_path=args.state_path,
        reuse_existing_source=args.reuse_existing_source,
    )
    print(
        {
            "api_calls": result.api_calls,
            "candles_received": result.candles_received,
            "rows_written": result.rows_written,
            "chunks_with_data": result.chunks_with_data,
            "partitions_touched": result.partitions_touched,
            "last_candle_timestamp": result.last_candle_timestamp,
            "start_at": result.start_at,
            "end_at": result.end_at,
        }
    )


if __name__ == "__main__":
    main()
