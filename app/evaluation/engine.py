"""Counterfactual evaluation harness for BTC trading experiments."""

from __future__ import annotations

import copy
import json
import math
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from app.backtest.engine import BacktestEngine, BacktestResult
from app.backtest.metrics import compute_drawdown_series
from app.config.schema import AppConfig
from app.evaluation.policies import (
    NoOpReviewPolicy,
    RandomReviewPolicy,
    ReviewPolicy,
    RsiReviewPolicy,
    ScoreHardReviewPolicy,
    ScoreSoftReviewPolicy,
    ScoreWeightedReviewPolicy,
    VolatilityReviewPolicy,
)
from app.llm.advisor import LLMAdvisor


@dataclass(slots=True)
class EvalRecord:
    """One aligned per-step comparison record."""

    timestamp: str
    baseline_signal_generated: bool
    overlay_signal_generated: bool
    baseline_trade_taken: bool
    overlay_trade_taken: bool
    pnl_det: float
    llm_action: str
    llm_confidence: float
    llm_score: float
    llm_decision_present: bool
    llm_decision_valid: bool
    pnl_llm: float
    was_good_trade: bool
    llm_decision_applied: bool
    behavior_label: str


@dataclass(slots=True)
class EvaluationModeResult:
    """Summary for one comparison mode."""

    mode: str
    trade_count: int
    trades_blocked: int
    bad_trades_blocked: int
    good_trades_blocked: int
    block_precision: float
    total_return_percent: float
    max_drawdown_percent: float
    sharpe_ratio: float
    avg_confidence: float
    confidence_vs_pnl_correlation: float | None
    avg_score: float
    score_vs_pnl_correlation: float | None
    pnl_delta_percent: float
    drawdown_delta_percent: float
    record_count: int


@dataclass(slots=True)
class EvaluationResult:
    """Top-level evaluation artifact."""

    symbol: str
    strategy_profile: str
    interval: str
    start_at: str
    end_at: str
    baseline_mode: str
    mode_results: list[EvaluationModeResult]
    records_by_mode: dict[str, list[EvalRecord]] = field(default_factory=dict)


class EvaluationEngine:
    """Run counterfactual comparisons on top of the replay engine."""

    DEFAULT_MODES = ("llm_hard", "llm_soft", "llm_weighted", "random_20", "rsi_70", "volatility_2_5")

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(
        self,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        strategy_profile: str | None = None,
        modes: list[str] | None = None,
        random_block_rate: float = 0.2,
        rsi_block_threshold: float = 70.0,
        volatility_block_threshold_percent: float = 2.5,
        max_records_per_mode: int = 250,
    ) -> EvaluationResult:
        """Replay one baseline run and multiple counterfactual overlay modes."""
        symbol = symbol or self.config.trading.symbol
        interval = interval or self.config.ingestion.interval
        strategy_profile = strategy_profile or "hybrid_current"
        mode_names = modes or list(self.DEFAULT_MODES)

        baseline = self._run_backtest(
            policy=NoOpReviewPolicy(),
            symbol=symbol,
            interval=interval,
            start_at=start_at,
            end_at=end_at,
            strategy_profile=strategy_profile,
        )
        comparison_results: dict[str, BacktestResult] = {}
        for mode_name in mode_names:
            policy = self._policy_for_mode(
                mode_name,
                random_block_rate=random_block_rate,
                rsi_block_threshold=rsi_block_threshold,
                volatility_block_threshold_percent=volatility_block_threshold_percent,
            )
            if policy is None:
                continue
            comparison_results[mode_name] = self._run_backtest(
                policy=policy,
                symbol=symbol,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
                strategy_profile=strategy_profile,
            )

        evaluation = self.evaluate_runs(baseline=baseline, comparisons=comparison_results)
        evaluation.records_by_mode = {
            mode: records[:max_records_per_mode] for mode, records in evaluation.records_by_mode.items()
        }
        return evaluation

    def evaluate_runs(self, *, baseline: BacktestResult, comparisons: dict[str, BacktestResult]) -> EvaluationResult:
        """Compare a baseline backtest to one or more counterfactual runs."""
        mode_results: list[EvaluationModeResult] = []
        records_by_mode: dict[str, list[EvalRecord]] = {}
        for mode_name, comparison in comparisons.items():
            records = self._build_records(baseline, comparison)
            records_by_mode[mode_name] = records
            mode_results.append(self._summarize_mode(mode_name, baseline, comparison, records))
        mode_results.sort(key=lambda item: item.mode)
        return EvaluationResult(
            symbol=baseline.symbol,
            strategy_profile=baseline.strategy_profile,
            interval=baseline.interval,
            start_at=baseline.start_at,
            end_at=baseline.end_at,
            baseline_mode="deterministic",
            mode_results=mode_results,
            records_by_mode=records_by_mode,
        )

    def _run_backtest(
        self,
        *,
        policy: ReviewPolicy,
        symbol: str,
        interval: str,
        start_at: datetime | None,
        end_at: datetime | None,
        strategy_profile: str,
    ) -> BacktestResult:
        """Run a backtest with a specific review policy."""
        config = copy.deepcopy(self.config)
        if hasattr(policy, "review"):
            config.llm.enabled = bool(getattr(policy, "enabled", config.llm.enabled))
        engine = BacktestEngine(config=config, review_policy=policy)
        return engine.run(
            symbol=symbol,
            interval=interval,
            start_at=start_at,
            end_at=end_at,
            strategy_profile=strategy_profile,
        )

    def _policy_for_mode(
        self,
        mode: str,
        *,
        random_block_rate: float,
        rsi_block_threshold: float,
        volatility_block_threshold_percent: float,
    ) -> ReviewPolicy | None:
        if mode == "baseline":
            return NoOpReviewPolicy()
        if mode in {"llm", "llm_hard", "llm_soft", "llm_weighted"}:
            if not self.config.llm.enabled:
                return None
            if not self.config.env.get("OPENAI_API_KEY", "").strip():
                return None
            advisor = LLMAdvisor(config=self.config)
            if mode in {"llm", "llm_hard"}:
                return ScoreHardReviewPolicy(base_policy=advisor, block_threshold=0.0)
            if mode == "llm_soft":
                return ScoreSoftReviewPolicy(base_policy=advisor, block_threshold=-0.25, reduce_threshold=0.25, reduce_multiplier=0.5)
            return ScoreWeightedReviewPolicy(base_policy=advisor, min_size_multiplier=self.config.llm.min_size_multiplier)
        if mode == "random_20":
            return RandomReviewPolicy(block_rate=random_block_rate)
        if mode == "rsi_70":
            return RsiReviewPolicy(block_threshold=rsi_block_threshold)
        if mode == "volatility_2_5":
            return VolatilityReviewPolicy(block_threshold_percent=volatility_block_threshold_percent)
        return None

    def _build_records(self, baseline: BacktestResult, comparison: BacktestResult) -> list[EvalRecord]:
        """Align two replay runs into per-step counterfactual records."""
        records: list[EvalRecord] = []
        baseline_equity = self._equity_deltas(baseline.equity_curve)
        comparison_equity = self._equity_deltas(comparison.equity_curve)
        for index, (baseline_step, comparison_step) in enumerate(zip(baseline.steps, comparison.steps, strict=False)):
            llm_review = comparison_step.llm_review or {}
            decision = llm_review.get("decision") if isinstance(llm_review, dict) else None
            llm_action = "allow"
            llm_confidence = 0.0
            llm_score = 0.0
            decision_present = bool(llm_review.get("decision_present")) if isinstance(llm_review, dict) else False
            decision_valid = bool(llm_review.get("decision_valid")) if isinstance(llm_review, dict) else False
            if isinstance(decision, dict):
                llm_action = str(decision.get("action", "allow"))
                try:
                    llm_confidence = float(decision.get("confidence", 0.0))
                except (TypeError, ValueError):
                    llm_confidence = 0.0
                try:
                    llm_score = float(decision.get("score", 0.0))
                except (TypeError, ValueError):
                    llm_score = 0.0
            baseline_signal_generated = baseline_step.signal_count > 0
            overlay_signal_generated = comparison_step.signal_count > 0
            baseline_trade_taken = baseline_step.execution_count > 0
            overlay_trade_taken = comparison_step.execution_count > 0
            llm_decision_applied = bool(decision_present and decision_valid and overlay_signal_generated)
            behavior_label = self._classify_behavior(
                baseline_signal_generated=baseline_signal_generated,
                overlay_signal_generated=overlay_signal_generated,
                baseline_trade_taken=baseline_trade_taken,
                overlay_trade_taken=overlay_trade_taken,
                was_good_trade=baseline_equity[index] > 0,
            )
            records.append(
                EvalRecord(
                    timestamp=baseline_step.timestamp,
                    baseline_signal_generated=baseline_signal_generated,
                    overlay_signal_generated=overlay_signal_generated,
                    baseline_trade_taken=baseline_trade_taken,
                    overlay_trade_taken=overlay_trade_taken,
                    pnl_det=baseline_equity[index],
                    llm_action=llm_action,
                    llm_confidence=llm_confidence,
                    llm_score=llm_score,
                    llm_decision_present=decision_present,
                    llm_decision_valid=decision_valid,
                    pnl_llm=comparison_equity[index],
                    was_good_trade=baseline_equity[index] > 0,
                    llm_decision_applied=llm_decision_applied,
                    behavior_label=behavior_label,
                )
            )
        return records

    def _summarize_mode(
        self,
        mode: str,
        baseline: BacktestResult,
        comparison: BacktestResult,
        records: list[EvalRecord],
    ) -> EvaluationModeResult:
        """Summarize a comparison mode against the deterministic baseline."""
        trade_count = sum(1 for record in records if record.overlay_trade_taken)
        trades_blocked = sum(1 for record in records if record.baseline_trade_taken and not record.overlay_trade_taken)
        bad_trades_blocked = sum(
            1 for record in records if record.baseline_trade_taken and not record.overlay_trade_taken and not record.was_good_trade
        )
        good_trades_blocked = sum(
            1 for record in records if record.baseline_trade_taken and not record.overlay_trade_taken and record.was_good_trade
        )
        block_precision = 0.0 if trades_blocked == 0 else bad_trades_blocked / trades_blocked
        confidences = [
            record.llm_confidence
            for record in records
            if record.llm_decision_present and record.llm_decision_valid
        ]
        scores = [
            record.llm_score
            for record in records
            if record.llm_decision_present and record.llm_decision_valid
        ]
        avg_confidence = 0.0 if not confidences else mean(confidences)
        avg_score = 0.0 if not scores else mean(scores)
        pnl_samples = [record.pnl_llm for record in records if record.llm_decision_present and record.llm_decision_valid]
        confidence_corr = self._pearson_correlation(confidences, pnl_samples)
        score_corr = self._pearson_correlation(scores, pnl_samples)
        return EvaluationModeResult(
            mode=mode,
            trade_count=trade_count,
            trades_blocked=trades_blocked,
            bad_trades_blocked=bad_trades_blocked,
            good_trades_blocked=good_trades_blocked,
            block_precision=block_precision,
            total_return_percent=comparison.metrics.total_return_percent,
            max_drawdown_percent=comparison.metrics.max_drawdown_percent,
            sharpe_ratio=comparison.metrics.sharpe_ratio,
            avg_confidence=avg_confidence,
            confidence_vs_pnl_correlation=confidence_corr,
            avg_score=avg_score,
            score_vs_pnl_correlation=score_corr,
            pnl_delta_percent=comparison.metrics.total_return_percent - baseline.metrics.total_return_percent,
            drawdown_delta_percent=baseline.metrics.max_drawdown_percent - comparison.metrics.max_drawdown_percent,
            record_count=len(records),
        )

    @staticmethod
    def _equity_deltas(equity_curve: list[dict[str, object]]) -> list[float]:
        """Return point-to-point equity deltas for a curve."""
        deltas: list[float] = []
        previous = None
        for point in equity_curve:
            equity = float(point.get("equity_usd", 0.0))
            if previous is None:
                deltas.append(0.0)
            else:
                deltas.append(equity - previous)
            previous = equity
        return deltas

    @staticmethod
    def _pearson_correlation(left: list[float], right: list[float]) -> float | None:
        """Compute a simple Pearson correlation coefficient."""
        if len(left) < 2 or len(right) < 2 or len(left) != len(right):
            return None
        left_mean = mean(left)
        right_mean = mean(right)
        numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=False))
        left_denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left))
        right_denominator = math.sqrt(sum((y - right_mean) ** 2 for y in right))
        denominator = left_denominator * right_denominator
        if denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def _classify_behavior(
        *,
        baseline_signal_generated: bool,
        overlay_signal_generated: bool,
        baseline_trade_taken: bool,
        overlay_trade_taken: bool,
        was_good_trade: bool,
    ) -> str:
        """Classify the overlay outcome relative to the baseline."""
        if baseline_trade_taken and not overlay_trade_taken:
            return "blocked_good_trade" if was_good_trade else "blocked_bad_trade"
        if not baseline_trade_taken and overlay_trade_taken:
            return "harmful_override" if was_good_trade else "overlay_added_trade"
        if baseline_trade_taken and overlay_trade_taken:
            if baseline_signal_generated and overlay_signal_generated:
                return "matched_trade"
            return "sized_trade"
        return "neutral"


def serialize_evaluation_result(result: EvaluationResult) -> dict[str, Any]:
    """Convert an evaluation result into a JSON-serializable payload."""
    return {
        "recorded_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "symbol": result.symbol,
        "strategy_profile": result.strategy_profile,
        "interval": result.interval,
        "start_at": result.start_at,
        "end_at": result.end_at,
        "baseline_mode": result.baseline_mode,
        "mode_results": [asdict(mode_result) for mode_result in result.mode_results],
        "records_by_mode": {
            mode: [asdict(record) for record in records]
            for mode, records in result.records_by_mode.items()
        },
    }
