from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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
from app.monitoring.weekly_report import build_weekly_report


def _build_config(base_dir: Path) -> AppConfig:
    state_dir = base_dir / "state"
    ingestion_dir = state_dir / "ingestion"
    paper_trade_dir = state_dir / "paper_trade"
    return AppConfig(
        trading=TradingConfig(strategy_profile="hybrid_current", dca_drop_percent=1.5, dca_order_size_usd=100.0),
        data=DataConfig(data_lake_path=str(base_dir)),
        ingestion=IngestionConfig(state_path=str(ingestion_dir / "ingestion.json"), health_max_staleness_minutes=120),
        runtime=RuntimeConfig(health_max_staleness_minutes=120),
        logging=LoggingConfig(),
        notifications=NotificationConfig(gmail_enabled=True),
        llm=LLMConfig(enabled=False),
        execution=ExecutionConfig(
            fee_pct=0.001,
            spread_pct=0.0005,
            slippage_pct=0.0005,
            paper_state_path=str(paper_trade_dir / "broker_state.json"),
            paper_trade_log_path=str(paper_trade_dir / "trade.jsonl"),
            paper_cycle_log_path=str(paper_trade_dir / "cycle.jsonl"),
            paper_snapshot_path=str(paper_trade_dir / "snapshot.json"),
            paper_decision_trace_path=str(paper_trade_dir / "trace.jsonl"),
        ),
        env={"REPORT_TIMEZONE": "America/Toronto"},
        cache_path="",
    )


def test_build_weekly_report_uses_existing_artifacts(tmp_path) -> None:
    """Weekly report should summarize portfolio, activity, health, and config from current artifacts."""
    config = _build_config(tmp_path)
    paper_dir = tmp_path / "state" / "paper_trade"
    ingestion_dir = tmp_path / "state" / "ingestion"
    paper_dir.mkdir(parents=True, exist_ok=True)
    ingestion_dir.mkdir(parents=True, exist_ok=True)

    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    cycle_time = now - timedelta(days=1)
    cycle_snapshot = {
        "cash_usd": 9800.0,
        "btc_units": 0.0025,
        "equity_usd": 10020.0,
        "drawdown_percent": 0.4,
        "avg_entry_price": 72000.0,
        "last_mark_price": 72800.0,
        "dca_btc_units": 0.0020,
        "swing_btc_units": 0.0005,
        "realized_pnl_usd": 15.0,
        "total_fees_usd": 1.0,
        "total_spread_cost_usd": 0.4,
        "total_slippage_cost_usd": 0.6,
    }
    latest_snapshot = {
        "recorded_at": cycle_time.isoformat(),
        "cycle": 42,
        "regime": "weakening_bull",
        "strategy_name": "HybridStrategy",
        "summary": "equity_usd=10020.00, cash_usd=9800.00, btc_units=0.002500, drawdown=0.40%",
        "snapshot": cycle_snapshot,
        "llm_review": {"enabled": False, "used": False, "status": "disabled", "summary": "LLM disabled", "action_count": 0},
    }
    (paper_dir / "snapshot.json").write_text(json.dumps(latest_snapshot), encoding="utf-8")
    broker_state = {
        "cash_usd": 9800.0,
        "dca_btc_units": 0.0020,
        "dca_avg_entry_price": 72000.0,
        "open_swing_positions": [
            {
                "position_id": "swing-1",
                "symbol": "BTC-USD",
                "entry_price": 73000.0,
                "stop_loss": 71000.0,
                "btc_units": 0.0005,
                "size_usd": 36.5,
                "opened_at": (now - timedelta(days=2)).isoformat(),
                "origin_strategy": "SwingATRStrategy",
                "strategy_name": "SwingATRStrategy",
            }
        ],
        "last_mark_price": 72800.0,
        "peak_equity": 10100.0,
        "realized_pnl_usd": 15.0,
        "total_fees_usd": 1.0,
        "total_spread_cost_usd": 0.4,
        "total_slippage_cost_usd": 0.6,
        "updated_at": cycle_time.isoformat(),
        "latest_dca_buy_price": 72100.0,
        "recent_signal_keys": [],
    }
    (paper_dir / "broker_state.json").write_text(json.dumps(broker_state), encoding="utf-8")
    trades = [
        {
            "timestamp": (now - timedelta(days=3)).isoformat(),
            "side": "buy",
            "symbol": "BTC-USD",
            "size_usd": 100.0,
            "price": 72000.0,
            "btc_units": 0.00138,
            "order_id": "paper-1",
            "reason": "initial_dca_entry",
            "strategy_name": "DCAStrategy",
            "stop_loss": None,
            "fee_usd": 0.10,
            "spread_cost_usd": 0.05,
            "slippage_cost_usd": 0.05,
            "execution_cost_usd": 0.20,
            "reference_price": 71900.0,
            "realized_pnl_usd": None,
        },
        {
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "side": "sell",
            "symbol": "BTC-USD",
            "size_usd": 120.0,
            "price": 73500.0,
            "btc_units": 0.00163,
            "order_id": "paper-2",
            "reason": "swing_take_profit:swing-1",
            "strategy_name": "SwingATRStrategy",
            "stop_loss": 71000.0,
            "fee_usd": 0.12,
            "spread_cost_usd": 0.06,
            "slippage_cost_usd": 0.06,
            "execution_cost_usd": 0.24,
            "reference_price": 73600.0,
            "realized_pnl_usd": 18.5,
        },
    ]
    (paper_dir / "trade.jsonl").write_text("\n".join(json.dumps(trade) for trade in trades) + "\n", encoding="utf-8")
    cycles = [
        {
            "recorded_at": (now - timedelta(days=6)).isoformat(),
            "cycle": 36,
            "regime": "sideways",
            "strategy_name": "HybridStrategy",
            "indicator_snapshot": {"last_price": 72000.0},
            "decision_trace": [],
            "signal_count": 1,
            "llm_review": {"enabled": False, "used": False, "status": "disabled", "summary": "LLM disabled", "action_count": 0},
            "execution_results": [],
            "summary": "equity_usd=9900.00",
            "snapshot": {**cycle_snapshot, "equity_usd": 9900.0},
        },
        {
            "recorded_at": cycle_time.isoformat(),
            "cycle": 42,
            "regime": "weakening_bull",
            "strategy_name": "HybridStrategy",
            "indicator_snapshot": {"last_price": 72800.0},
            "decision_trace": [],
            "signal_count": 1,
            "llm_review": {"enabled": False, "used": False, "status": "disabled", "summary": "LLM disabled", "action_count": 0},
            "execution_results": [],
            "summary": "equity_usd=10020.00",
            "snapshot": cycle_snapshot,
        },
    ]
    (paper_dir / "cycle.jsonl").write_text("\n".join(json.dumps(cycle) for cycle in cycles) + "\n", encoding="utf-8")
    ingestion_state = {
        "last_successful_run_at": cycle_time.isoformat(),
        "last_ingested_timestamp": (now - timedelta(days=1, minutes=3)).isoformat(),
        "rows_written": 25,
        "provider": "coinbase",
    }
    (ingestion_dir / "ingestion.json").write_text(json.dumps(ingestion_state), encoding="utf-8")
    gap_audit = {
        "recorded_at": cycle_time.isoformat(),
        "symbol": "BTC-USD",
        "interval": "1m",
        "source_gap_count": 0,
        "lake_gap_count": 0,
        "source_gaps": [],
        "lake_gaps": [],
    }
    (ingestion_dir / "ingestion_gap_audit.json").write_text(json.dumps(gap_audit), encoding="utf-8")

    report = build_weekly_report(config, now=now)

    assert "Adaptive BTC Trading Agent Weekly Report" in report.subject
    assert "Portfolio Summary" in report.html
    assert "Trading Activity" in report.html
    assert "Strategy Breakdown" in report.html
    assert "Trade Breakdown" in report.html
    assert "Open Positions" in report.html
    assert "System Health" in report.html
    assert "Configuration Snapshot" in report.html
    assert "$10,020.00" in report.html
    assert "+$120.00" in report.html
    assert "Decision Owner" in report.html
    assert "Execution Source" in report.html
    assert "SwingATRStrategy" in report.html
    assert "HybridStrategy" in report.html
    assert "hybrid_current" in report.html
