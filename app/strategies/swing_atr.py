"""ATR-aware opportunistic trading strategy."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import AgentContext, Candle, FeatureSet, Signal, TradeSide


class SwingATRStrategy:
    """Generate opportunistic swing signals bounded by ATR logic."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the swing strategy."""
        self.config = config

    def generate(
        self,
        context: AgentContext,
        candles: list[Candle],
        features: FeatureSet,
    ) -> list[Signal]:
        """Generate momentum-driven buy signals."""
        _ = candles
        if features.last_price <= 0 or features.atr <= 0:
            return []

        if features.rsi < 65 and features.macd_histogram > 0 and features.ema_fast > features.ema_slow:
            return [
                Signal(
                    side=TradeSide.BUY,
                    symbol=self.config.trading.symbol,
                    size_usd=min(250.0, context.available_cash_usd),
                    reason="momentum_atr_setup",
                    reference_price=features.last_price,
                    stop_loss=features.last_price - (self.config.trading.atr_multiplier * features.atr),
                )
            ]
        return []
