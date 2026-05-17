from __future__ import annotations

from datetime import UTC, datetime

from app.backtest.engine import BacktestResult, BacktestStep
from app.backtest.metrics import BacktestMetrics, compute_drawdown_series, compute_max_drawdown_percent, compute_sharpe_ratio
from app.config.schema import AppConfig, DataConfig, ExecutionConfig, IngestionConfig, LLMConfig, LoggingConfig, NotificationConfig, RuntimeConfig, TradingConfig
from app.evaluation.engine import EvaluationEngine
from app.utils.models import PortfolioSnapshot


def _config() -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env={},
        cache_path="",
    )


def _result(*, symbol: str, profile: str, interval: str, equity_curve: list[float], steps: list[BacktestStep]) -> BacktestResult:
    metrics = BacktestMetrics(
        initial_equity_usd=10_000.0,
        final_equity_usd=equity_curve[-1],
        total_return_percent=((equity_curve[-1] - 10_000.0) / 10_000.0) * 100,
        buy_and_hold_return_percent=0.0,
        max_drawdown_percent=compute_max_drawdown_percent(equity_curve),
        sharpe_ratio=compute_sharpe_ratio(equity_curve, periods_per_year=365),
        trade_count=sum(step.execution_count for step in steps),
        filled_trade_count=sum(step.execution_count for step in steps),
        closed_trade_count=0,
        win_rate_percent=0.0,
        avg_win_usd=0.0,
        avg_loss_usd=0.0,
        profit_factor=0.0,
    )
    drawdowns = [
        {"timestamp": step.timestamp, "drawdown_percent": drawdown}
        for step, drawdown in zip(steps, compute_drawdown_series(equity_curve), strict=False)
    ]
    return BacktestResult(
        symbol=symbol,
        strategy_profile=profile,
        interval=interval,
        start_at="2026-01-01T00:00:00+00:00",
        end_at="2026-01-01T00:03:00+00:00",
        candles_processed=len(steps),
        metrics=metrics,
        final_snapshot=PortfolioSnapshot(cash_usd=0.0, btc_units=0.0, equity_usd=equity_curve[-1], drawdown_percent=metrics.max_drawdown_percent),
        trades=[],
        steps=steps,
        equity_curve=[{"timestamp": step.timestamp, "equity_usd": equity} for step, equity in zip(steps, equity_curve, strict=False)],
        benchmark_curve=[],
        drawdowns=drawdowns,
        halted_reason=None,
        halted_at=None,
    )


def _step(
    *,
    timestamp: str,
    signal_count: int,
    execution_count: int,
    decision: str,
    equity_usd: float,
    action: str | None = None,
    confidence: float = 0.0,
    score: float = 0.0,
) -> BacktestStep:
    return BacktestStep(
        timestamp=timestamp,
        regime="bullish",
        strategy_name="SwingATRStrategy",
        signal_count=signal_count,
        execution_count=execution_count,
        decision=decision,
        equity_usd=equity_usd,
        drawdown_percent=0.0,
        trace=[],
        llm_review=(
            {
                "enabled": True,
                "used": True,
                "status": "reviewed",
                "summary": "ok",
                "action_count": 1 if action else 0,
                "decision_present": bool(action),
                "decision_valid": bool(action),
                "decision": {
                    "action": action,
                    "confidence": confidence,
                    "reason": "policy",
                    "reason_code": "test_policy",
                    "score": score,
                }
                if action
                else None,
            }
            if action
            else {
                "enabled": False,
                "used": False,
                "status": "baseline",
                "summary": "baseline",
                "action_count": 0,
                "decision_present": False,
                "decision_valid": False,
                "decision": None,
            }
        ),
    )


def test_evaluation_engine_summarizes_block_precision() -> None:
    engine = EvaluationEngine(_config())
    baseline = _result(
        symbol="BTC-USD",
        profile="hybrid_current",
        interval="30m",
        equity_curve=[10_000.0, 10_100.0, 9_900.0],
        steps=[
            _step(timestamp="2026-01-01T00:00:00+00:00", signal_count=0, execution_count=0, decision="HOLD", equity_usd=10_000.0),
            _step(timestamp="2026-01-01T00:01:00+00:00", signal_count=1, execution_count=1, decision="BUY", equity_usd=10_100.0),
            _step(timestamp="2026-01-01T00:02:00+00:00", signal_count=1, execution_count=1, decision="BUY", equity_usd=9_900.0),
        ],
    )
    overlay = _result(
        symbol="BTC-USD",
        profile="hybrid_current",
        interval="30m",
        equity_curve=[10_000.0, 10_100.0, 10_100.0],
        steps=[
            _step(timestamp="2026-01-01T00:00:00+00:00", signal_count=0, execution_count=0, decision="HOLD", equity_usd=10_000.0),
            _step(timestamp="2026-01-01T00:01:00+00:00", signal_count=1, execution_count=1, decision="BUY", equity_usd=10_100.0, action="allow", confidence=0.91, score=0.84),
            _step(timestamp="2026-01-01T00:02:00+00:00", signal_count=1, execution_count=0, decision="NO BUY", equity_usd=10_100.0, action="block", confidence=0.84, score=-0.72),
        ],
    )

    evaluation = engine.evaluate_runs(baseline=baseline, comparisons={"llm": overlay})
    mode = evaluation.mode_results[0]

    assert mode.mode == "llm"
    assert mode.trades_blocked == 1
    assert mode.bad_trades_blocked == 1
    assert mode.good_trades_blocked == 0
    assert mode.block_precision == 1.0
    assert mode.pnl_delta_percent > 0
    assert len(evaluation.records_by_mode["llm"]) == 3
    assert evaluation.records_by_mode["llm"][2].llm_action == "block"
    assert evaluation.records_by_mode["llm"][2].behavior_label == "blocked_bad_trade"
    assert evaluation.records_by_mode["llm"][2].baseline_signal_generated is True
    assert evaluation.records_by_mode["llm"][2].overlay_signal_generated is True
    assert evaluation.records_by_mode["llm"][2].llm_decision_applied is True
    assert mode.avg_score == 0.06
