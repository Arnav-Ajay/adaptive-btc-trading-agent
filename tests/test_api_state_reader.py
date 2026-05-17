"""Tests for dashboard state loading."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from datetime import UTC, datetime, timedelta

from app.api.state_reader import load_dashboard_state
from app.config.schema import (
    AppConfig,
    DataConfig,
    ExecutionConfig,
    IngestionConfig,
    LLMConfig,
    LoggingConfig,
    NotificationConfig,
    RuntimeConfig,
    TradingConfig,
)
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.utils.models import Candle


def _build_config(base_dir: Path) -> AppConfig:
    state_dir = base_dir / "state"
    ingestion_dir = state_dir / "ingestion"
    paper_trade_dir = state_dir / "paper_trade"
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(data_lake_path=str(base_dir)),
        ingestion=IngestionConfig(state_path=str(ingestion_dir / "ingestion.json")),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(
            paper_state_path=str(paper_trade_dir / "broker_state.json"),
            paper_trade_log_path=str(paper_trade_dir / "trade.jsonl"),
            paper_cycle_log_path=str(paper_trade_dir / "cycle.jsonl"),
            paper_snapshot_path=str(paper_trade_dir / "snapshot.json"),
            paper_decision_trace_path=str(paper_trade_dir / "trace.jsonl"),
        ),
        env={},
        cache_path="",
    )


def test_load_dashboard_state_reads_latest_artifacts() -> None:
    """Dashboard state loader should assemble the latest runtime artifacts."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config = _build_config(base_dir)
        state_dir = base_dir / "state"
        ingestion_dir = state_dir / "ingestion"
        paper_trade_dir = state_dir / "paper_trade"
        ingestion_dir.mkdir(parents=True, exist_ok=True)
        paper_trade_dir.mkdir(parents=True, exist_ok=True)

        (ingestion_dir / "ingestion.json").write_text(json.dumps({"provider": "coinbase"}), encoding="utf-8")
        (paper_trade_dir / "snapshot.json").write_text(json.dumps({"snapshot": {"equity_usd": 10_000.0}}), encoding="utf-8")
        (paper_trade_dir / "trade.jsonl").write_text(json.dumps({"side": "buy"}) + "\n", encoding="utf-8")
        (paper_trade_dir / "cycle.jsonl").write_text(
            json.dumps({"cycle": 4, "llm_review": {"enabled": True, "used": True, "status": "reviewed", "summary": "ok", "action_count": 1}})
            + "\n",
            encoding="utf-8",
        )
        (paper_trade_dir / "trace.jsonl").write_text(
            json.dumps({"strategy_name": "DCAStrategy", "llm_review": {"enabled": True, "used": True, "status": "reviewed", "summary": "ok", "action_count": 1}})
            + "\n",
            encoding="utf-8",
        )

        state = load_dashboard_state(config)
        assert state["ingestion_state"]["provider"] == "coinbase"
        assert state["broker_state"] is None
        assert state["portfolio_snapshot"]["snapshot"]["equity_usd"] == 10_000.0
        assert state["latest_trade"]["side"] == "buy"
        assert state["latest_cycle"]["cycle"] == 4
        assert state["latest_trace"]["strategy_name"] == "DCAStrategy"
        assert state["llm_state"]["enabled"] is True
        assert state["llm_state"]["used_in_last_cycle"] is True


def test_load_dashboard_state_can_skip_full_chart_sets() -> None:
    """Trades-page state loading should be able to avoid loading large chart payloads."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config = _build_config(base_dir)
        ingestion_dir = base_dir / "state" / "ingestion"
        ingestion_dir.mkdir(parents=True, exist_ok=True)

        (ingestion_dir / "ingestion.json").write_text(json.dumps({"provider": "coinbase"}), encoding="utf-8")

        state = load_dashboard_state(config, include_candles=False)
        assert state["recent_candles"] == []
        assert state["chart_candles"] == {}


def test_load_dashboard_state_includes_simulation_artifacts() -> None:
    """State loader should surface latest simulation files when they exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config = _build_config(base_dir)
        simulation_dir = base_dir / "state" / "simulations"
        simulation_dir.mkdir(parents=True, exist_ok=True)

        (simulation_dir / "simulation_latest.json").write_text(json.dumps({"candidate_count": 4}), encoding="utf-8")
        (simulation_dir / "simulation_history.jsonl").write_text(json.dumps({"recorded_at": "2026-03-25T00:00:00+00:00"}) + "\n", encoding="utf-8")

        state = load_dashboard_state(config, include_candles=False)
        assert state["latest_simulation"]["candidate_count"] == 4
        assert len(state["recent_simulations"]) == 1


def test_load_dashboard_state_can_skip_backtest_and_simulation_artifacts() -> None:
    """Trades subviews should be able to avoid loading unrelated heavy history payloads."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config = _build_config(base_dir)
        state_dir = base_dir / "state"
        backtest_dir = state_dir / "backtesting"
        simulation_dir = state_dir / "simulations"
        backtest_dir.mkdir(parents=True, exist_ok=True)
        simulation_dir.mkdir(parents=True, exist_ok=True)

        (backtest_dir / "backtest_latest.json").write_text(json.dumps({"interval": "30m"}), encoding="utf-8")
        (backtest_dir / "backtest_history.jsonl").write_text(json.dumps({"recorded_at": "2026-03-25T00:00:00+00:00"}) + "\n", encoding="utf-8")
        (simulation_dir / "simulation_latest.json").write_text(json.dumps({"candidate_count": 4}), encoding="utf-8")
        (simulation_dir / "simulation_history.jsonl").write_text(json.dumps({"recorded_at": "2026-03-25T00:00:00+00:00"}) + "\n", encoding="utf-8")

        state = load_dashboard_state(
            config,
            include_candles=False,
            include_backtests=False,
            include_simulations=False,
        )
        assert state["latest_backtest"] is None
        assert state["latest_simulation"] is None
        assert state["recent_backtests"] == []
        assert state["recent_simulations"] == []


def test_load_dashboard_state_can_skip_ingestion_and_paper_artifacts() -> None:
    """Backtest and simulation views should be able to avoid paper-trading and ingestion logs entirely."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config = _build_config(base_dir)
        state_dir = base_dir / "state"
        ingestion_dir = state_dir / "ingestion"
        paper_trade_dir = state_dir / "paper_trade"
        ingestion_dir.mkdir(parents=True, exist_ok=True)
        paper_trade_dir.mkdir(parents=True, exist_ok=True)

        (ingestion_dir / "ingestion.json").write_text(json.dumps({"provider": "coinbase"}), encoding="utf-8")
        (ingestion_dir / "ingestion_gap_audit.json").write_text(json.dumps({"gap_count": 2}), encoding="utf-8")
        (paper_trade_dir / "broker_state.json").write_text(json.dumps({"open_swing_positions": []}), encoding="utf-8")
        (paper_trade_dir / "snapshot.json").write_text(json.dumps({"snapshot": {"equity_usd": 10_000.0}}), encoding="utf-8")
        (paper_trade_dir / "trade.jsonl").write_text(json.dumps({"side": "buy"}) + "\n", encoding="utf-8")
        (paper_trade_dir / "cycle.jsonl").write_text(json.dumps({"cycle": 4}) + "\n", encoding="utf-8")
        (paper_trade_dir / "trace.jsonl").write_text(json.dumps({"strategy_name": "DCAStrategy"}) + "\n", encoding="utf-8")

        state = load_dashboard_state(
            config,
            include_candles=False,
            include_ingestion=False,
            include_paper=False,
            include_backtests=False,
            include_simulations=False,
        )
        assert state["ingestion_state"] is None
        assert state["ingestion_gap_audit"] is None
        assert state["broker_state"] is None
        assert state["portfolio_snapshot"] is None
        assert state["latest_trade"] is None
        assert state["latest_cycle"] is None
        assert state["latest_trace"] is None
        assert state["recent_trades"] == []
        assert state["recent_cycles"] == []


def test_load_dashboard_state_falls_back_to_parquet_when_ingestion_state_is_missing() -> None:
    """Bitcoin/UI state should still show freshness when canonical parquet exists but ingestion.json was deleted."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        config = _build_config(base_dir)
        store = ParquetMarketDataStore(str(base_dir))
        start = datetime(2026, 4, 4, 0, 0, tzinfo=UTC)
        candles = [
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=100.0 + index,
                high=101.0 + index,
                low=99.0 + index,
                close=100.5 + index,
                volume=1.0,
            )
            for index in range(3)
        ]
        store.write_candles(symbol="BTC-USD", interval="1m", candles=candles)

        state = load_dashboard_state(config, include_candles=False, include_paper=False, include_backtests=False, include_simulations=False)

        assert state["ingestion_state"] is not None
        assert state["ingestion_state"]["status"] == "parquet_fallback"
        assert state["ingestion_state"]["last_ingested_timestamp"] == "2026-04-04T00:02:00+00:00"
