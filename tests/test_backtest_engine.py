from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pytest import approx

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
    assert result.start_at == "2026-01-01T00:19:00+00:00"
    assert result.end_at == "2026-01-01T01:59:00+00:00"
    assert len(result.steps) == 101
    assert len(result.equity_curve) == 101
    assert result.benchmark_curve[0]["equity_usd"] == approx(config.execution.initial_cash_usd)
    assert result.metrics.filled_trade_count >= 1
    assert result.final_snapshot.cash_usd < config.execution.initial_cash_usd


def test_backtest_engine_halts_when_drawdown_limit_is_breached(tmp_path) -> None:
    """Replay should stop once the portfolio drawdown guard is breached."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.trading.dca_order_size_usd = 100.0
    config.trading.max_drawdown_percent = 0.05
    config.execution.initial_cash_usd = 1_000.0

    store = ParquetMarketDataStore(str(tmp_path))
    _write_backtest_candles(store)

    engine = BacktestEngine(config=config)
    result = engine.run(symbol="BTC-USD", interval="1m")

    assert result.halted_reason == "max_drawdown_reached"
    assert result.halted_at is not None
    assert result.steps[-1].decision == "HALT"


def test_backtest_engine_continues_after_stop_loss_exit(tmp_path) -> None:
    """A stop-loss exit should close the position without terminating the replay."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 0.0
    config.trading.atr_multiplier = 0.1
    config.trading.swing_entry_rsi_max = 65.0

    store = ParquetMarketDataStore(str(tmp_path))
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    close = 100.0
    for index in range(60):
        if index < 40:
            close += 0.8 if index % 2 == 0 else -0.6
        elif index == 40:
            close -= 5.0
        else:
            close += 0.5
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=close - 0.3,
                high=close + 0.8,
                low=close - 0.8,
                close=close,
                volume=1.0,
            )
        )
    store.write_candles(symbol="BTC-USD", interval="1m", candles=candles)

    engine = BacktestEngine(config=config)
    result = engine.run(symbol="BTC-USD", interval="1m")

    stop_indices = [idx for idx, step in enumerate(result.steps) if step.strategy_name == "StopLossExit"]
    assert stop_indices
    assert result.halted_reason is None
    assert len(result.steps) > stop_indices[0] + 1

