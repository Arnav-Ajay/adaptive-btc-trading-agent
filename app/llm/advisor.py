"""LLM advisory layer."""

from __future__ import annotations

import logging

from app.config.schema import AppConfig
from app.llm.prompts import build_review_prompt
from app.utils.models import FeatureSet, LLMAdvice, MarketRegime, Signal


logger = logging.getLogger(__name__)


class LLMAdvisor:
    """Review deterministic signals without controlling execution."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the advisor."""
        self.config = config

    def review(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
    ) -> LLMAdvice:
        """Generate bounded advisory output."""
        prompt = build_review_prompt(signals=signals, features=features, regime=regime)
        logger.debug("LLM review prompt prepared: %s", prompt)
        if not self.config.llm.enabled:
            return LLMAdvice(summary="LLM disabled", parameter_suggestions={})
        return LLMAdvice(summary="LLM integration pending", parameter_suggestions={})
