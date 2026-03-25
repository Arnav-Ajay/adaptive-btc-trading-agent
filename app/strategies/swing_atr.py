"""ATR-aware opportunistic trading strategy."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import AgentContext, Candle, FeatureSet, Signal, StrategyOutcome, TradeSide


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
    ) -> StrategyOutcome:
        """Generate momentum-driven buy signals."""
        _ = candles
        if features.last_price <= 0 or features.atr <= 0:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=[
                    f"skip:invalid_price_or_atr last_price={features.last_price:.2f}",
                    f"observed:atr={features.atr:.2f}",
                ],
            )

        trace = [
            f"check:rsi_lt_65 actual={features.rsi:.2f}",
            f"check:macd_histogram_gt_0 actual={features.macd_histogram:.4f}",
            f"check:ema_fast_gt_ema_slow fast={features.ema_fast:.2f} slow={features.ema_slow:.2f}",
            f"check:available_cash_usd={context.available_cash_usd:.2f}",
        ]

        if features.rsi < 65 and features.macd_histogram > 0 and features.ema_fast > features.ema_slow:
            size_usd = min(250.0, context.available_cash_usd)
            stop_loss = features.last_price - (self.config.trading.atr_multiplier * features.atr)
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[
                    Signal(
                        side=TradeSide.BUY,
                        symbol=self.config.trading.symbol,
                        size_usd=size_usd,
                        reason="momentum_atr_setup",
                        reference_price=features.last_price,
                        stop_loss=stop_loss,
                        strategy_name=self.__class__.__name__,
                    )
                ],
                trace=trace
                + [
                    f"decision:momentum_conditions_met stop_loss={stop_loss:.2f}",
                    f"signal:momentum_atr_setup size_usd={size_usd:.2f}",
                ],
            )
        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[],
            trace=trace + ["skip:momentum_conditions_not_met"],
        )
