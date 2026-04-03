"""Tests for dashboard state loading."""

from __future__ import annotations

import json
from pathlib import Path

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


def _build_config(tmp_path: Path) -> AppConfig:
    state_dir = tmp_path / "state"
    ingestion_dir = state_dir / "ingestion"
    paper_trade_dir = state_dir / "paper_trade"
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(data_lake_path=str(tmp_path)),
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


def test_load_dashboard_state_reads_latest_artifacts(tmp_path) -> None:
    """Dashboard state loader should assemble the latest runtime artifacts."""
    config = _build_config(tmp_path)
    state_dir = tmp_path / "state"
    ingestion_dir = state_dir / "ingestion"
    paper_trade_dir = state_dir / "paper_trade"
    ingestion_dir.mkdir(parents=True, exist_ok=True)
    paper_trade_dir.mkdir(parents=True, exist_ok=True)

    (ingestion_dir / "ingestion.json").write_text(json.dumps({"provider": "coinbase"}), encoding="utf-8")
    (paper_trade_dir / "snapshot.json").write_text(json.dumps({"snapshot": {"equity_usd": 10_000.0}}), encoding="utf-8")
    (paper_trade_dir / "trade.jsonl").write_text(json.dumps({"side": "buy"}) + "\n", encoding="utf-8")
    (paper_trade_dir / "cycle.jsonl").write_text(json.dumps({"cycle": 4}) + "\n", encoding="utf-8")
    (paper_trade_dir / "trace.jsonl").write_text(json.dumps({"strategy_name": "DCAStrategy"}) + "\n", encoding="utf-8")

    state = load_dashboard_state(config)
    assert state["ingestion_state"]["provider"] == "coinbase"
    assert state["broker_state"] is None
    assert state["portfolio_snapshot"]["snapshot"]["equity_usd"] == 10_000.0
    assert state["latest_trade"]["side"] == "buy"
    assert state["latest_cycle"]["cycle"] == 4
    assert state["latest_trace"]["strategy_name"] == "DCAStrategy"


def test_load_dashboard_state_can_skip_full_chart_sets(tmp_path) -> None:
    """Trades-page state loading should be able to avoid loading large chart payloads."""
    config = _build_config(tmp_path)
    ingestion_dir = tmp_path / "state" / "ingestion"
    ingestion_dir.mkdir(parents=True, exist_ok=True)

    (ingestion_dir / "ingestion.json").write_text(json.dumps({"provider": "coinbase"}), encoding="utf-8")

    state = load_dashboard_state(config, include_candles=False)
    assert state["recent_candles"] == []
    assert state["chart_candles"] == {}


def test_load_dashboard_state_includes_simulation_artifacts(tmp_path) -> None:
    """State loader should surface latest simulation files when they exist."""
    config = _build_config(tmp_path)
    simulation_dir = tmp_path / "state" / "simulations"
    simulation_dir.mkdir(parents=True, exist_ok=True)

    (simulation_dir / "simulation_latest.json").write_text(json.dumps({"candidate_count": 4}), encoding="utf-8")
    (simulation_dir / "simulation_history.jsonl").write_text(json.dumps({"recorded_at": "2026-03-25T00:00:00+00:00"}) + "\n", encoding="utf-8")

    state = load_dashboard_state(config, include_candles=False)
    assert state["latest_simulation"]["candidate_count"] == 4
    assert len(state["recent_simulations"]) == 1


def test_load_dashboard_state_can_skip_backtest_and_simulation_artifacts(tmp_path) -> None:
    """Trades subviews should be able to avoid loading unrelated heavy history payloads."""
    config = _build_config(tmp_path)
    state_dir = tmp_path / "state"
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


def test_load_dashboard_state_can_skip_ingestion_and_paper_artifacts(tmp_path) -> None:
    """Backtest and simulation views should be able to avoid paper-trading and ingestion logs entirely."""
    config = _build_config(tmp_path)
    state_dir = tmp_path / "state"
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
