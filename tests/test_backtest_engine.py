from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.backtest.engine import BacktestEngine
from app.config.settings import load_config
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.utils.models import Candle


def _write_backtest_candles(store: ParquetMarketDataStore, count: int = 120) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(count):
        base = 100.0 - (index * 0.2)
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=base,
                high=base + 1.0,
                low=base - 1.0,
                close=base - 0.1,
                volume=1.0,
            )
        )
    store.write_candles(symbol="BTC-USD", interval="1m", candles=candles)


def test_backtest_engine_replays_parquet_history(tmp_path) -> None:
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.trading.dca_order_size_usd = 100.0
    config.execution.initial_cash_usd = 1_000.0

    store = ParquetMarketDataStore(str(tmp_path))
    _write_backtest_candles(store)

    engine = BacktestEngine(config=config)
    result = engine.run(symbol="BTC-USD", interval="1m")

    assert result.candles_processed == 120
    assert result.start_at == "2026-01-01T00:00:00+00:00"
    assert result.end_at == "2026-01-01T01:59:00+00:00"
    assert len(result.steps) == 101
    assert len(result.equity_curve) == 101
    assert result.metrics.filled_trade_count >= 1
    assert result.final_snapshot.cash_usd < config.execution.initial_cash_usd

