"""Tests for persistent trading-cycle journal outputs."""

from __future__ import annotations

import json
from pathlib import Path

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
from app.monitoring.trading_journal import TradingJournal
from app.utils.models import OrderResult, PortfolioSnapshot


def _build_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(data_lake_path=str(tmp_path)),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(
            paper_cycle_log_path=str(tmp_path / "cycle_log.jsonl"),
            paper_snapshot_path=str(tmp_path / "portfolio_snapshot.json"),
            paper_decision_trace_path=str(tmp_path / "decision_trace.jsonl"),
        ),
        env={},
        cache_path="",
    )


def test_trading_journal_persists_cycle_log_and_snapshot(tmp_path) -> None:
    """Trading journal should append one cycle record and refresh the latest snapshot."""
    journal = TradingJournal(_build_config(tmp_path))
    snapshot = PortfolioSnapshot(
        cash_usd=9_900.0,
        btc_units=0.001,
        equity_usd=10_000.0,
        drawdown_percent=0.0,
        avg_entry_price=50_000.0,
        last_mark_price=100_000.0,
    )
    journal.record_cycle(
        cycle=3,
        regime="bullish",
        strategy_name="SwingATRStrategy",
        indicator_snapshot={
            "candle_count": 120,
            "latest_candle_timestamp": "2026-03-24T22:00:00+00:00",
            "last_price": 100_000.0,
            "atr": 1_000.0,
            "rsi": 60.0,
            "ema_fast": 99_500.0,
            "ema_slow": 99_000.0,
            "macd": 10.0,
            "macd_signal": 9.5,
            "macd_histogram": 0.5,
        },
        decision_trace=["decision:example"],
        signal_count=1,
        execution_results=[OrderResult(accepted=True, order_id="paper-1", reason="filled")],
        snapshot=snapshot,
        summary="equity_usd=10000.00",
    )

    cycle_log_path = tmp_path / "cycle_log.jsonl"
    snapshot_path = tmp_path / "portfolio_snapshot.json"
    decision_trace_path = tmp_path / "decision_trace.jsonl"
    assert cycle_log_path.exists()
    assert snapshot_path.exists()
    assert decision_trace_path.exists()

    records = [json.loads(line) for line in cycle_log_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["cycle"] == 3
    assert records[0]["execution_results"][0]["accepted"] is True
    assert records[0]["indicator_snapshot"]["last_price"] == 100_000.0
    assert records[0]["decision_trace"] == ["decision:example"]

    latest_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert latest_snapshot["cycle"] == 3
    assert latest_snapshot["snapshot"]["equity_usd"] == 10_000.0

    trace_records = [json.loads(line) for line in decision_trace_path.read_text(encoding="utf-8").splitlines()]
    assert len(trace_records) == 1
    assert trace_records[0]["strategy_name"] == "SwingATRStrategy"
