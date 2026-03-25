"""Dollar-cost averaging strategy."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import AgentContext, Candle, FeatureSet, Signal, StrategyOutcome, TradeSide


class DCAStrategy:
    """Generate deterministic DCA buy signals."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the DCA strategy."""
        self.config = config

    def generate(
        self,
        context: AgentContext,
        candles: list[Candle],
        features: FeatureSet,
    ) -> StrategyOutcome:
        """Generate DCA signals based on price pullback and schedule."""
        _ = candles
        if features.last_price <= 0:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:last_price_non_positive"],
            )

        if context.latest_buy_fill_price is None:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[
                    Signal(
                    side=TradeSide.BUY,
                    symbol=self.config.trading.symbol,
                    size_usd=self.config.trading.dca_order_size_usd,
                    reason="initial_dca_entry",
                    reference_price=features.last_price,
                    strategy_name=self.__class__.__name__,
                )
                ],
                trace=[
                    "decision:no_prior_buy_fill",
                    f"signal:initial_dca_entry size_usd={self.config.trading.dca_order_size_usd:.2f}",
                ],
            )

        drop_threshold = context.latest_buy_fill_price * (
            1 - self.config.trading.dca_drop_percent / 100
        )
        if features.last_price <= drop_threshold:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[
                    Signal(
                        side=TradeSide.BUY,
                        symbol=self.config.trading.symbol,
                        size_usd=self.config.trading.dca_order_size_usd,
                        reason="price_drop_dca_entry",
                        reference_price=features.last_price,
                        strategy_name=self.__class__.__name__,
                    )
                ],
                trace=[
                    f"decision:price_below_drop_threshold threshold={drop_threshold:.2f}",
                    f"signal:price_drop_dca_entry size_usd={self.config.trading.dca_order_size_usd:.2f}",
                ],
            )

        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[],
            trace=[
                f"skip:price_above_drop_threshold latest_buy_fill_price={context.latest_buy_fill_price:.2f}",
                f"threshold:required_price_at_or_below={drop_threshold:.2f}",
                f"observed:last_price={features.last_price:.2f}",
            ],
        )
