"""ATR-aware opportunistic trading strategy."""

from __future__ import annotations

from datetime import datetime

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
        """Generate momentum-driven swing entries and exits."""
        latest_timestamp = candles[-1].timestamp if candles else None
        if features.last_price <= 0 or features.atr <= 0:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=[
                    f"skip:invalid_price_or_atr last_price={features.last_price:.2f}",
                    f"observed:atr={features.atr:.2f}",
                ],
            )

        signals: list[Signal] = []
        trace = [
            f"check:rsi_lt_{self.config.trading.swing_entry_rsi_max:.0f} actual={features.rsi:.2f}",
            f"check:macd_histogram_gt_0 actual={features.macd_histogram:.4f}",
            f"check:ema_fast_gt_ema_slow fast={features.ema_fast:.2f} slow={features.ema_slow:.2f}",
            f"check:available_cash_usd={context.available_cash_usd:.2f}",
        ]

        for position in context.active_swing_positions:
            entry_price = float(position.entry_price)
            btc_units = float(position.btc_units)
            take_profit_price = entry_price * (1 + self.config.trading.swing_take_profit_percent / 100)
            candles_since_entry = self._candles_since_entry(candles, position.opened_at)
            follow_through_target = entry_price * (1 + self.config.trading.swing_follow_through_buffer_percent / 100)
            exit_reason: str | None = None
            if features.last_price >= take_profit_price:
                exit_reason = f"swing_take_profit:{position.position_id}"
                trace.append(
                    f"decision:take_profit_hit position_id={position.position_id} target={take_profit_price:.2f} actual={features.last_price:.2f}"
                )
            elif (
                candles_since_entry >= self.config.trading.swing_no_follow_through_candles
                and features.last_price < follow_through_target
            ):
                exit_reason = f"swing_no_follow_through:{position.position_id}"
                trace.append(
                    f"decision:no_follow_through position_id={position.position_id} candles_since_entry={candles_since_entry} required_price={follow_through_target:.2f} actual={features.last_price:.2f}"
                )
            elif features.macd_histogram <= 0 or features.ema_fast <= features.ema_slow:
                exit_reason = f"swing_signal_exit:{position.position_id}"
                trace.append(
                    f"decision:trend_exit position_id={position.position_id} macd_histogram={features.macd_histogram:.4f} ema_fast={features.ema_fast:.2f} ema_slow={features.ema_slow:.2f}"
                )

            if exit_reason is None:
                trace.append(f"hold:open_swing_position position_id={position.position_id}")
                continue

            signals.append(
                Signal(
                    side=TradeSide.SELL,
                    symbol=position.symbol,
                    size_usd=btc_units * features.last_price,
                    reason=exit_reason,
                    reference_price=features.last_price,
                    strategy_name=self.__class__.__name__,
                )
            )
            trace.append(
                f"signal:{exit_reason.split(':', 1)[0]} btc_units={btc_units:.6f} size_usd={(btc_units * features.last_price):.2f}"
            )

        if (
            not context.active_swing_positions
            and features.rsi < self.config.trading.swing_entry_rsi_max
            and features.macd_histogram > 0
            and features.ema_fast > features.ema_slow
        ):
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
        if signals:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=signals,
                trace=trace,
            )
        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[],
            trace=trace + ["skip:momentum_conditions_not_met"],
        )

    @staticmethod
    def _candles_since_entry(candles: list[Candle], opened_at: str) -> int:
        """Count how many candles have elapsed since a tracked swing position was opened."""
        try:
            opened_timestamp = datetime.fromisoformat(opened_at)
        except ValueError:
            return 0
        return sum(1 for candle in candles if candle.timestamp >= opened_timestamp)
