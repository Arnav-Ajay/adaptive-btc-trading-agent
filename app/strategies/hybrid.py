"""Hybrid strategy that keeps DCA as the base layer."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.strategies.dca import DCAStrategy
from app.strategies.swing_atr import SwingATRStrategy
from app.utils.models import AgentContext, Candle, FeatureSet, StrategyOutcome


class HybridStrategy:
    """Combine base-layer DCA with opportunistic swing entries."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the hybrid strategy stack."""
        self.dca = DCAStrategy(config=config)
        self.swing = SwingATRStrategy(config=config)

    def generate(
        self,
        context: AgentContext,
        candles: list[Candle],
        features: FeatureSet,
    ) -> StrategyOutcome:
        """Run DCA first, then add swing opportunities when conditions align."""
        dca_outcome = self.dca.generate(context=context, candles=candles, features=features)
        swing_outcome = self.swing.generate(context=context, candles=candles, features=features)
        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[*dca_outcome.signals, *swing_outcome.signals],
            trace=[
                "component:DCAStrategy",
                *dca_outcome.trace,
                "component:SwingATRStrategy",
                *swing_outcome.trace,
            ],
        )
