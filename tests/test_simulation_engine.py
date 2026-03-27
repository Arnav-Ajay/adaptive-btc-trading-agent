from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config.settings import load_config
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.simulation.engine import SimulationEngine
from app.utils.models import Candle


def _write_simulation_candles(store: ParquetMarketDataStore, *, interval: str, step_minutes: int, count: int) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    price = 100.0
    for index in range(count):
        price += 0.6 if index % 2 == 0 else -0.4
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=step_minutes * index),
                open=price - 0.4,
                high=price + 0.8,
                low=price - 0.8,
                close=price,
                volume=1.0,
            )
        )
    store.write_candles(symbol="BTC-USD", interval=interval, candles=candles)


def test_simulation_engine_runs_parameter_sweep(tmp_path) -> None:
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 0.0

    store = ParquetMarketDataStore(str(tmp_path))
    _write_simulation_candles(store, interval="30m", step_minutes=30, count=40)

    result = SimulationEngine(config).run(
        symbol="BTC-USD",
        interval="30m",
        parameter_grid={
            "swing_entry_rsi_max": [35.0, 45.0],
            "swing_take_profit_percent": [2.0],
            "swing_no_follow_through_candles": [3],
            "swing_follow_through_buffer_percent": [0.2],
            "atr_multiplier": [1.5],
        },
    )

    assert result.candidate_count == 2
    assert len(result.candidates) == 2
    assert result.best_candidate_id == result.candidates[0].candidate_id
