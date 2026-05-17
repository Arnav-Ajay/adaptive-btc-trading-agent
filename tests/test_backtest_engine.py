from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from pytest import approx

import app.backtest.engine as backtest_engine_module
from app.backtest.engine import BacktestEngine, BacktestResult
from app.config.settings import load_config
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.utils.models import Candle, MarketRegime, OrderResult, TradeSide


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
    config.trading.dca_enabled_in_bearish = True
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
    """Replay should halt trading but still carry the curves through the full window."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.trading.dca_order_size_usd = 100.0
    config.trading.dca_enabled_in_bearish = True
    config.trading.max_drawdown_percent = 0.05
    config.execution.initial_cash_usd = 1_000.0

    store = ParquetMarketDataStore(str(tmp_path))
    _write_backtest_candles(store)

    engine = BacktestEngine(config=config)
    result = engine.run(symbol="BTC-USD", interval="1m")

    assert result.halted_reason == "max_drawdown_reached"
    assert result.halted_at is not None
    assert result.steps[-1].decision == "HALT"
    assert len(result.steps) == 101
    assert len(result.equity_curve) == 101
    halted_index = next(index for index, step in enumerate(result.steps) if step.timestamp == result.halted_at)
    halted_equity = result.equity_curve[halted_index]["equity_usd"]
    assert all(point["equity_usd"] == halted_equity for point in result.equity_curve[halted_index:])


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


def _write_uptrend_then_drop_candles(store: ParquetMarketDataStore, count: int = 60) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    close = 100.0
    for index in range(count):
        if index < 24:
            close += 0.8
        elif index == 24:
            close += 0.4
        elif index == 25:
            close -= 18.0
        else:
            close += 0.2
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


def _write_oscillating_downtrend_candles(store: ParquetMarketDataStore, count: int = 120) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    close = 100.0
    for index in range(count):
        close += 0.8 if index % 2 == 0 else -1.0
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=close - 0.3,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1.0,
            )
        )
    store.write_candles(symbol="BTC-USD", interval="1m", candles=candles)


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


def test_backtest_engine_blocks_dca_entries_in_bearish_regime(tmp_path) -> None:
    """Bearish structure should keep the base DCA layer inactive by default."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 100.0
    config.trading.dca_enabled_in_bearish = False

    store = ParquetMarketDataStore(str(tmp_path))
    _write_backtest_candles(store)

    engine = BacktestEngine(config=config)
    result = engine.run(symbol="BTC-USD", interval="1m", strategy_profile="dca_only")

    assert result.metrics.filled_trade_count == 0
    assert result.final_snapshot.cash_usd == approx(config.execution.initial_cash_usd)
    assert all(step.decision in {"NO BUY", "HOLD"} for step in result.steps)


def test_decision_cadence_changes_entry_frequency(tmp_path, monkeypatch) -> None:
    """Higher cadence frequencies should expose more entry opportunities."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 100.0
    config.trading.dca_enabled_in_bearish = True

    store = ParquetMarketDataStore(str(tmp_path))
    _write_oscillating_downtrend_candles(store)
    monkeypatch.setattr(backtest_engine_module, "detect_regime_score", lambda window, features: _fake_regime_state())

    results: dict[int, BacktestResult] = {}
    for cadence in (30, 5, 1):
        config.runtime.decision_cadence_minutes = cadence
        engine = BacktestEngine(config=config)
        results[cadence] = engine.run(symbol="BTC-USD", interval="1m", strategy_profile="dca_only")

    assert results[1].metrics.filled_trade_count >= results[5].metrics.filled_trade_count >= results[30].metrics.filled_trade_count
    assert results[1].metrics.filled_trade_count > 0


def test_stop_losses_still_run_between_cadence_windows(tmp_path, monkeypatch) -> None:
    """Stop-loss exits should fire even when no decision boundary is reached."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.swing_entry_rsi_max = 100.0
    config.trading.atr_multiplier = 0.1
    config.trading.swing_enabled_in_sideways = True
    config.trading.swing_enabled_in_weakening_bull = True
    config.trading.swing_enabled_in_bearish = True
    config.runtime.decision_cadence_minutes = 30

    store = ParquetMarketDataStore(str(tmp_path))
    _write_uptrend_then_drop_candles(store)
    monkeypatch.setattr(backtest_engine_module, "detect_regime_score", lambda window, features: _fake_regime_state())
    stop_loss_calls = {"count": 0}

    def fake_stop_losses(self):
        stop_loss_calls["count"] += 1
        if stop_loss_calls["count"] == 2:
            return [
                OrderResult(
                    accepted=True,
                    order_id="stop-loss-1",
                    reason="forced_stop_loss",
                    side=TradeSide.SELL,
                    symbol="BTC-USD",
                    size_usd=100.0,
                    price=100.0,
                    strategy_name="SwingATRStrategy",
                    stop_loss=99.0,
                )
            ]
        return []

    monkeypatch.setattr(backtest_engine_module.OrderManager, "evaluate_stop_losses", fake_stop_losses)

    engine = BacktestEngine(config=config)
    result = engine.run(symbol="BTC-USD", interval="1m", strategy_profile="swing_only")

    stop_loss_steps = [step for step in result.steps if step.strategy_name == "StopLossExit"]
    assert stop_loss_steps
    stop_loss_step = stop_loss_steps[0]
    replay_start = datetime.fromisoformat(result.start_at)
    stop_loss_time = datetime.fromisoformat(stop_loss_step.timestamp)
    minutes_since_start = int((stop_loss_time - replay_start).total_seconds() // 60)
    assert minutes_since_start % result.decision_cadence_minutes != 0


def test_cadence_only_affects_entries(tmp_path, monkeypatch) -> None:
    """Changing cadence should not alter feature or price history inputs."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 20
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 100.0
    config.trading.dca_enabled_in_bearish = True

    store = ParquetMarketDataStore(str(tmp_path))
    _write_oscillating_downtrend_candles(store)
    monkeypatch.setattr(backtest_engine_module, "detect_regime_score", lambda window, features: _fake_regime_state())

    recordings: dict[int, dict[str, list[float | int]]] = {
        1: {"window_lengths": [], "feature_prices": [], "mark_prices": []},
        30: {"window_lengths": [], "feature_prices": [], "mark_prices": []},
    }
    current_cadence = 30
    original_compute = backtest_engine_module.compute_indicator_bundle
    original_mark_price = backtest_engine_module.OrderManager.mark_price

    def wrapped_compute_indicator_bundle(window):
        recordings[current_cadence]["window_lengths"].append(len(window))
        recordings[current_cadence]["feature_prices"].append(float(window[-1].close))
        return original_compute(window)

    def wrapped_mark_price(self, price: float):
        recordings[current_cadence]["mark_prices"].append(float(price))
        return original_mark_price(self, price)

    monkeypatch.setattr(backtest_engine_module, "compute_indicator_bundle", wrapped_compute_indicator_bundle)
    monkeypatch.setattr(backtest_engine_module.OrderManager, "mark_price", wrapped_mark_price)

    for cadence in (30, 1):
        current_cadence = cadence
        config.runtime.decision_cadence_minutes = cadence
        engine = BacktestEngine(config=config)
        engine.run(symbol="BTC-USD", interval="1m", strategy_profile="dca_only")

    assert recordings[1]["window_lengths"] == recordings[30]["window_lengths"]
    assert recordings[1]["feature_prices"] == recordings[30]["feature_prices"]
    assert recordings[1]["mark_prices"] == recordings[30]["mark_prices"]


def test_30m_clock_alignment() -> None:
    """30m cadence should hit clock-aligned half-hour boundaries."""
    assert BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 30)
    assert BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 30, tzinfo=UTC), 30)
    assert BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 1, 0, tzinfo=UTC), 30)
    assert not BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 19, tzinfo=UTC), 30)
    assert not BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 49, tzinfo=UTC), 30)


def test_5m_clock_alignment() -> None:
    """5m cadence should hit each five-minute clock boundary."""
    assert BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 5)
    assert BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 5, tzinfo=UTC), 5)
    assert BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 10, tzinfo=UTC), 5)
    assert not BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 1, tzinfo=UTC), 5)
    assert not BacktestEngine._is_decision_cadence_boundary(datetime(2026, 1, 1, 0, 7, tzinfo=UTC), 5)


def test_replay_start_time_does_not_shift_boundaries(tmp_path) -> None:
    """Replay start offsets should not move a clock-aligned cadence boundary."""
    config = load_config()
    config.data.data_lake_path = str(tmp_path)
    config.data.min_candles_required = 1
    config.execution.initial_cash_usd = 1_000.0
    config.trading.dca_order_size_usd = 0.0
    config.runtime.decision_cadence_minutes = 30

    store = ParquetMarketDataStore(str(tmp_path))
    _write_backtest_candles(store, count=60)

    engine = BacktestEngine(config=config)
    early_result = engine.run(
        symbol="BTC-USD",
        interval="1m",
        start_at=datetime(2026, 1, 1, 0, 19, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 0, 59, tzinfo=UTC),
        strategy_profile="dca_only",
    )
    late_result = engine.run(
        symbol="BTC-USD",
        interval="1m",
        start_at=datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 0, 59, tzinfo=UTC),
        strategy_profile="dca_only",
    )

    early_first_boundary = next(step.timestamp for step in early_result.steps if step.strategy_name != "CadenceGate")
    late_first_boundary = next(step.timestamp for step in late_result.steps if step.strategy_name != "CadenceGate")
    assert early_first_boundary == "2026-01-01T00:30:00+00:00"
    assert late_first_boundary == "2026-01-01T00:30:00+00:00"

