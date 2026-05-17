"""Strategy selection and orchestration."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.strategies.dca import DCAStrategy
from app.strategies.hybrid import HybridStrategy
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
        bullish_trend: bool = False,
        has_open_swing_positions: bool = False,
        regime_score: float | None = None,
        regime_confidence: float | None = None,
        deterioration_score: float | None = None,
    ) -> DCAStrategy | SwingATRStrategy | HybridStrategy:
        """Select a strategy for the current market regime."""
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
