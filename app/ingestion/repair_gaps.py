"""Temporary targeted repair for missing 1m parquet candles."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd

from app.config.settings import load_config
from app.data.coinbase_client import CoinbaseClient
from app.ingestion.backfill import _chunk_span_for_limit, _parse_datetime, MAX_COINBASE_CANDLES_PER_CALL
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.ingestion.preprocessor import MarketDataPreprocessor
from app.monitoring.logger import configure_logging
from app.utils.models import Candle


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GapRange:
    """Contiguous missing-timestamp range."""

    start: datetime
    end: datetime
    count: int


def _build_argument_parser() -> argparse.ArgumentParser:
    """Build CLI args for targeted gap repair."""
    parser = argparse.ArgumentParser(description="Repair missing 1m BTC-USD parquet gaps from Coinbase")
    parser.add_argument("--start", default="2026-01-01T00:00:00Z", help="Gap scan start, ISO 8601 UTC")
    parser.add_argument("--end", default=None, help="Gap scan end, ISO 8601 UTC; defaults to now")
    parser.add_argument("--symbol", default=None, help="Override trading symbol")
    parser.add_argument("--interval", default="1m", help="Only 1m is supported for gap repair")
    parser.add_argument("--limit", type=int, default=MAX_COINBASE_CANDLES_PER_CALL, help="Max Coinbase candles per call")
    parser.add_argument("--sleep-seconds", type=float, default=0.2, help="Sleep between Coinbase calls")
    parser.add_argument("--max-gap-ranges", type=int, default=None, help="Optional cap on repaired contiguous ranges")
    return parser


def _find_missing_ranges(
    store: ParquetMarketDataStore,
    symbol: str,
    interval: str,
    start_at: datetime,
    end_at: datetime,
) -> list[GapRange]:
    """Find contiguous missing 1m timestamp ranges in the parquet lake."""
    candles = store.load_candles(symbol=symbol, interval=interval, limit=None)
    observed = pd.to_datetime([candle.timestamp.astimezone(UTC) for candle in candles], utc=True)
    observed = pd.Series(observed).dt.floor("min").dropna().drop_duplicates().sort_values()

    expected = pd.date_range(start=start_at, end=end_at, freq="1min", tz="UTC")
    missing = expected.difference(observed)
    if len(missing) == 0:
        return []

    ranges: list[GapRange] = []
    range_start = missing[0].to_pydatetime()
    previous = range_start
    count = 1

    for timestamp in missing[1:]:
        current = timestamp.to_pydatetime()
        if current - previous == timedelta(minutes=1):
            previous = current
            count += 1
            continue
        ranges.append(GapRange(start=range_start, end=previous, count=count))
        range_start = current
        previous = current
        count = 1

    ranges.append(GapRange(start=range_start, end=previous, count=count))
    return ranges


def _fetch_gap_range(
    client: CoinbaseClient,
    symbol: str,
    interval: str,
    gap: GapRange,
    limit: int,
    sleep_seconds: float,
) -> list[Candle]:
    """Fetch a gap range in chunks using corrected inclusive span math."""
    interval_seconds = CoinbaseClient.interval_seconds(interval)
    chunk_span = _chunk_span_for_limit(interval_seconds=interval_seconds, limit=limit)
    step = timedelta(seconds=interval_seconds)
    cursor = gap.start
    hard_end = gap.end + step
    recovered: list[Candle] = []

    while cursor < hard_end:
        window_end = min(cursor + chunk_span, hard_end)
        candles = client.fetch_ohlcv(
            symbol=symbol,
            interval=interval,
            start=cursor,
            end=window_end,
            limit=limit,
        )
        if candles:
            recovered.extend(candles)
            cursor = candles[-1].timestamp.astimezone(UTC) + step
        else:
            cursor = window_end
        if cursor < hard_end and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    deduped: dict[datetime, Candle] = {}
    for candle in recovered:
        deduped[candle.timestamp.astimezone(UTC)] = candle
    return [deduped[timestamp] for timestamp in sorted(deduped)]


def run_gap_repair(
    start_at: datetime,
    end_at: datetime,
    symbol: str,
    interval: str,
    limit: int,
    sleep_seconds: float,
    max_gap_ranges: int | None = None,
) -> dict[str, object]:
    """Repair missing 1m gaps and rebuild derived intervals once at the end."""
    if interval != "1m":
        raise ValueError("gap repair currently supports only interval=1m")

    config = load_config()
    client = CoinbaseClient(
        api_key=config.env.get("COINBASE_API_KEY", ""),
        api_secret=config.env.get("COINBASE_API_SECRET", ""),
    )
    store = ParquetMarketDataStore(config.data.data_lake_path)
    preprocessor = MarketDataPreprocessor(store)

    missing_ranges = _find_missing_ranges(store, symbol=symbol, interval=interval, start_at=start_at, end_at=end_at)
    if max_gap_ranges is not None:
        missing_ranges = missing_ranges[:max_gap_ranges]

    logger.info(
        "Gap repair starting symbol=%s interval=%s start=%s end=%s gap_ranges=%s",
        symbol,
        interval,
        start_at.isoformat(),
        end_at.isoformat(),
        len(missing_ranges),
    )

    rows_written = 0
    api_calls_estimate = 0
    repaired_ranges = 0
    for gap in missing_ranges:
        logger.info(
            "Repairing gap start=%s end=%s missing_rows=%s",
            gap.start.isoformat(),
            gap.end.isoformat(),
            gap.count,
        )
        candles = _fetch_gap_range(
            client=client,
            symbol=symbol,
            interval=interval,
            gap=gap,
            limit=limit,
            sleep_seconds=sleep_seconds,
        )
        api_calls_estimate += max(1, (gap.count + limit - 1) // limit)
        if not candles:
            logger.warning("Gap fetch returned no candles for start=%s end=%s", gap.start.isoformat(), gap.end.isoformat())
            continue
        write_result = store.write_candles(symbol=symbol, interval=interval, candles=candles)
        rows_written += write_result.rows_written
        repaired_ranges += 1
        logger.info(
            "Gap repair complete start=%s end=%s received=%s new_rows=%s latest=%s",
            gap.start.isoformat(),
            gap.end.isoformat(),
            len(candles),
            write_result.rows_written,
            write_result.latest_timestamp,
        )

    derived_results = preprocessor.build_all(symbol=symbol, source_interval=interval)
    logger.info(
        "Gap repair finished repaired_ranges=%s rows_written=%s derived=%s",
        repaired_ranges,
        rows_written,
        ",".join(result.interval for result in derived_results) if derived_results else "none",
    )
    return {
        "gap_ranges_detected": len(missing_ranges),
        "gap_ranges_repaired": repaired_ranges,
        "rows_written": rows_written,
        "api_calls_estimate": api_calls_estimate,
        "derived_intervals": [result.interval for result in derived_results],
    }


def main() -> None:
    """CLI entrypoint for one-off gap repair."""
    args = _build_argument_parser().parse_args()
    config = load_config()
    configure_logging(config.logging.level, service_name="ingestion")

    start_at = _parse_datetime(args.start)
    end_at = _parse_datetime(args.end) if args.end else datetime.now(UTC).replace(second=0, microsecond=0)
    symbol = args.symbol or config.trading.symbol

    result = run_gap_repair(
        start_at=start_at,
        end_at=end_at,
        symbol=symbol,
        interval=args.interval,
        limit=min(args.limit, MAX_COINBASE_CANDLES_PER_CALL),
        sleep_seconds=args.sleep_seconds,
        max_gap_ranges=args.max_gap_ranges,
    )
    print(result)


if __name__ == "__main__":
    main()
