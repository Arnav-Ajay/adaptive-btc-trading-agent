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
    ) -> DCAStrategy | SwingATRStrategy | HybridStrategy:
        """Select a strategy for the current market regime."""
        if regime is MarketRegime.BULLISH or bullish_trend or has_open_swing_positions:
            return self.hybrid
        return self.dca
