"""Hybrid strategy combining DCA base allocation with pullback entries."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.strategies.dca import DCAStrategy
from app.strategies.pullback_trend import PullbackTrendStrategy
from app.strategies.pullback_selector import PullbackHybridSelector
from app.utils.models import AgentContext, Candle, FeatureSet, StrategyOutcome


class HybridPullbackStrategy:
    """Combine DCA base exposure logic with pullback-trend active trades."""

    def __init__(self, config: AppConfig) -> None:
        self.dca = DCAStrategy(config=config)
        self.pullback = PullbackTrendStrategy(config=config)
        self.selector = PullbackHybridSelector(config=config)

    def generate(
        self,
        context: AgentContext,
        candles: list[Candle],
        features: FeatureSet,
    ) -> StrategyOutcome:
        pullback_outcome = self.pullback.generate(context=context, candles=candles, features=features)
        selection = self.selector.select(context=context, pullback_outcome=pullback_outcome)
        dca_outcome = (
            self.dca.generate(context=context, candles=candles, features=features)
            if selection.allow_dca
            else StrategyOutcome(strategy_name="DCAStrategy", signals=[], trace=["skip:dca_selector_suppressed"])
        )
        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[*dca_outcome.signals, *pullback_outcome.signals],
            trace=[
                *selection.trace,
                "component:DCAStrategy",
                *dca_outcome.trace,
                "component:PullbackTrendStrategy",
                *pullback_outcome.trace,
            ],
        )
