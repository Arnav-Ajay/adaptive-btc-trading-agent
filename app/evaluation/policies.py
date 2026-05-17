"""Deterministic and score-aware review policies for evaluation runs."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from app.utils.models import FeatureSet, LLMAdvice, LLMSignalAction, MarketRegime, PortfolioSnapshot, Signal


class ReviewPolicy(Protocol):
    """Policy interface used to produce bounded LLM-style advice."""

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        """Return a bounded review payload."""


def _copy_advice(advice: LLMAdvice, *, signal_actions: list[LLMSignalAction], status: str) -> LLMAdvice:
    """Create a shallow copy of an advice payload with replacement signal actions."""
    return LLMAdvice(
        summary=advice.summary,
        parameter_suggestions=dict(advice.parameter_suggestions),
        signal_actions=signal_actions,
        decision=advice.decision,
        decision_present=advice.decision_present,
        decision_valid=advice.decision_valid,
        enabled=advice.enabled,
        used=advice.used,
        status=status,
    )


def _block_all_signals(signals: list[Signal], *, rationale: str) -> list[LLMSignalAction]:
    """Return block actions for every signal."""
    return [
        LLMSignalAction(signal_index=index, action="block", size_multiplier=0.0, rationale=rationale)
        for index, _signal in enumerate(signals)
    ]


def _reduce_all_signals(signals: list[Signal], *, size_multiplier: float, rationale: str) -> list[LLMSignalAction]:
    """Return reduce actions for every signal."""
    return [
        LLMSignalAction(
            signal_index=index,
            action="reduce",
            size_multiplier=size_multiplier,
            rationale=rationale,
        )
        for index, _signal in enumerate(signals)
    ]


def _decision_score(advice: LLMAdvice) -> float | None:
    """Extract a usable decision score from the advisory payload."""
    if not advice.decision_present or not advice.decision_valid or advice.decision is None:
        return None
    return advice.decision.score


@dataclass(slots=True)
class NoOpReviewPolicy:
    """Deterministic baseline that leaves all signals unchanged."""

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        return LLMAdvice(
            summary="Deterministic baseline",
            parameter_suggestions={},
            signal_actions=[],
            enabled=False,
            used=False,
            status="baseline",
        )


@dataclass(slots=True)
class RandomReviewPolicy:
    """Random blocking baseline with deterministic seeding per review call."""

    block_rate: float = 0.2
    seed: int = 13

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        key = f"{self.seed}:{regime.value}:{features.last_price:.2f}:{features.rsi:.2f}:{len(signals)}"
        rng = random.Random(key)
        actions: list[LLMSignalAction] = []
        for index, signal in enumerate(signals):
            if rng.random() < self.block_rate:
                actions.append(
                    LLMSignalAction(
                        signal_index=index,
                        action="block",
                        size_multiplier=0.0,
                        rationale="Randomized baseline block",
                    )
                )
        return LLMAdvice(
            summary="Random baseline",
            parameter_suggestions={},
            signal_actions=actions,
            enabled=False,
            used=True,
            status="random_baseline",
        )


@dataclass(slots=True)
class RsiReviewPolicy:
    """Simple RSI threshold baseline."""

    block_threshold: float = 70.0

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        actions: list[LLMSignalAction] = []
        if features.rsi >= self.block_threshold:
            actions = [
                LLMSignalAction(
                    signal_index=index,
                    action="block",
                    size_multiplier=0.0,
                    rationale=f"RSI above {self.block_threshold:.2f}",
                )
                for index, signal in enumerate(signals)
                if signal.side.value == "buy"
            ]
        return LLMAdvice(
            summary="RSI threshold baseline",
            parameter_suggestions={},
            signal_actions=actions,
            enabled=False,
            used=True,
            status="rsi_baseline",
        )


@dataclass(slots=True)
class VolatilityReviewPolicy:
    """Simple ATR-percent threshold baseline."""

    block_threshold_percent: float = 2.5

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        atr_percent = 0.0 if features.last_price <= 0 else (features.atr / features.last_price) * 100
        actions: list[LLMSignalAction] = []
        if atr_percent >= self.block_threshold_percent:
            actions = [
                LLMSignalAction(
                    signal_index=index,
                    action="block",
                    size_multiplier=0.0,
                    rationale=f"ATR percent above {self.block_threshold_percent:.2f}",
                )
                for index, signal in enumerate(signals)
                if signal.side.value == "buy"
            ]
        return LLMAdvice(
            summary="Volatility threshold baseline",
            parameter_suggestions={},
            signal_actions=actions,
            enabled=False,
            used=True,
            status="volatility_baseline",
        )


@dataclass(slots=True)
class ScoreHardReviewPolicy:
    """Convert LLM scores into a hard keep/block decision."""

    base_policy: ReviewPolicy
    block_threshold: float = 0.0

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        advice = self.base_policy.review(signals=signals, features=features, regime=regime, snapshot=snapshot)
        score = _decision_score(advice)
        if score is None:
            return advice
        if score < self.block_threshold:
            rationale = f"Score {score:.2f} below hard threshold {self.block_threshold:.2f}"
            return _copy_advice(advice, signal_actions=_block_all_signals(signals, rationale=rationale), status="score_hard_block")
        return _copy_advice(advice, signal_actions=[], status="score_hard_allow")


@dataclass(slots=True)
class ScoreSoftReviewPolicy:
    """Convert LLM scores into allow / reduce / block decisions."""

    base_policy: ReviewPolicy
    block_threshold: float = -0.25
    reduce_threshold: float = 0.25
    reduce_multiplier: float = 0.5

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        advice = self.base_policy.review(signals=signals, features=features, regime=regime, snapshot=snapshot)
        score = _decision_score(advice)
        if score is None:
            return advice
        if score <= self.block_threshold:
            rationale = f"Score {score:.2f} below soft block threshold {self.block_threshold:.2f}"
            return _copy_advice(advice, signal_actions=_block_all_signals(signals, rationale=rationale), status="score_soft_block")
        if score < self.reduce_threshold:
            multiplier = min(max(self.reduce_multiplier, 0.0), 1.0)
            rationale = f"Score {score:.2f} between soft thresholds"
            return _copy_advice(
                advice,
                signal_actions=_reduce_all_signals(signals, size_multiplier=multiplier, rationale=rationale),
                status="score_soft_reduce",
            )
        return _copy_advice(advice, signal_actions=[], status="score_soft_allow")


@dataclass(slots=True)
class ScoreWeightedReviewPolicy:
    """Scale exposure directly from the LLM score."""

    base_policy: ReviewPolicy
    min_size_multiplier: float = 0.35

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
        snapshot: PortfolioSnapshot,
    ) -> LLMAdvice:
        advice = self.base_policy.review(signals=signals, features=features, regime=regime, snapshot=snapshot)
        score = _decision_score(advice)
        if score is None:
            return advice
        normalized = (score + 1.0) / 2.0
        normalized = min(max(normalized, 0.0), 1.0)
        min_multiplier = min(max(self.min_size_multiplier, 0.0), 1.0)
        multiplier = min_multiplier + (normalized * (1.0 - min_multiplier))
        if multiplier >= 0.999:
            return _copy_advice(advice, signal_actions=[], status="score_weighted_allow")
        rationale = f"Score {score:.2f} mapped to weighted multiplier {multiplier:.2f}"
        return _copy_advice(
            advice,
            signal_actions=_reduce_all_signals(signals, size_multiplier=multiplier, rationale=rationale),
            status="score_weighted_reduce",
        )
