"""Strategy selection and orchestration."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.strategies.dca import DCAStrategy
from app.strategies.hybrid import HybridStrategy
from app.strategies.profiles import STRATEGY_PROFILES, normalize_strategy_profile
from app.strategies.swing_atr import SwingATRStrategy
from app.utils.models import MarketRegime


class StrategyRouter:
    """Route market regimes to concrete strategy implementations."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the strategy router."""
        self.config = config
        self.dca = DCAStrategy(config=config)
        self.swing = SwingATRStrategy(config=config)
        self.hybrid = HybridStrategy(config=config)

    def select(
        self,
        regime: MarketRegime,
        strategy_profile: str | None = None,
        bullish_trend: bool = False,
        has_open_swing_positions: bool = False,
        regime_score: float | None = None,
        regime_confidence: float | None = None,
        deterioration_score: float | None = None,
    ) -> DCAStrategy | SwingATRStrategy | HybridStrategy:
        """Select a strategy for the current market regime."""
        normalized_profile = normalize_strategy_profile(strategy_profile)
        if normalized_profile not in STRATEGY_PROFILES:
            normalized_profile = "hybrid_current"
        if normalized_profile == "dca_only":
            return self.dca
        if normalized_profile == "swing_only":
            return self.swing
        if normalized_profile == "hybrid_current":
            return self.hybrid
        if normalized_profile == "buy_and_hold":
            normalized_profile = "hybrid_current"
        if has_open_swing_positions:
            return self.hybrid
        if regime_score is not None and regime_confidence is not None:
            if deterioration_score is not None and regime_score > 0.0 and deterioration_score >= 0.65:
                return self.dca
            if regime_score >= 0.4 and regime_confidence >= 0.5:
                return self.hybrid
            if regime_score >= 0.15 and regime_confidence >= 0.45:
                return self.hybrid
            if regime_score <= -0.35 and regime_confidence >= 0.5:
                return self.dca
            if regime_score > 0.0 and regime in {MarketRegime.BULLISH, MarketRegime.WEAKENING_BULL}:
                return self.hybrid
            return self.dca
        if regime is MarketRegime.BULLISH or bullish_trend:
            return self.hybrid
        return self.dca
