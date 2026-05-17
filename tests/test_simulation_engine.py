from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import app.backtest.engine as backtest_engine_module
from app.config.settings import load_config
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.simulation.engine import SimulationEngine
from app.utils.models import Candle, MarketRegime


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


def _fake_regime_state(regime_label: MarketRegime = MarketRegime.BULLISH) -> SimpleNamespace:
    diagnostics = SimpleNamespace(
        swing_count=1,
        high_count=1,
        low_count=1,
        rising_high_ratio=0.0,
        rising_low_ratio=0.0,
        falling_high_ratio=0.0,
        falling_low_ratio=0.0,
        last_price_vs_prior_low=0.0,
        ema_spread_percent=0.0,
        rsi_centered=0.0,
        macd_histogram_percent=0.0,
        atr_percent=0.0,
    )
    return SimpleNamespace(
        regime_label=regime_label,
        regime_score=0.5,
        confidence=0.8,
        deterioration_score=0.1,
        diagnostics=diagnostics,
    )


def test_simulation_engine_runs_parameter_sweep(tmp_path) -> None:
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 0.0

    store = ParquetMarketDataStore(str(tmp_path))
    _write_simulation_candles(store, interval="30m", step_minutes=30, count=40)
    backtest_engine_module.detect_regime_score = lambda window, features: _fake_regime_state()

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
    assert result.decision_cadence_minutes == config.runtime.decision_cadence_minutes
