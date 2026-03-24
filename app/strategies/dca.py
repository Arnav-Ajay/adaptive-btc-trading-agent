"""Dollar-cost averaging strategy."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import AgentContext, Candle, FeatureSet, Signal, TradeSide


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
    ) -> list[Signal]:
        """Generate DCA signals based on price pullback and schedule."""
        _ = candles
        if features.last_price <= 0:
            return []

        if context.last_buy_price is None:
            return [
                Signal(
                    side=TradeSide.BUY,
                    symbol=self.config.trading.symbol,
                    size_usd=self.config.trading.dca_order_size_usd,
                    reason="initial_dca_entry",
                    reference_price=features.last_price,
                )
            ]

        drop_threshold = context.last_buy_price * (
            1 - self.config.trading.dca_drop_percent / 100
        )
        if features.last_price <= drop_threshold:
            return [
                Signal(
                    side=TradeSide.BUY,
                    symbol=self.config.trading.symbol,
                    size_usd=self.config.trading.dca_order_size_usd,
                    reason="price_drop_dca_entry",
                    reference_price=features.last_price,
                )
            ]
        return []
