"""Structure-aware pullback trend strategy."""

from __future__ import annotations

from datetime import datetime

from app.config.schema import AppConfig
from app.features.regime_features import SwingPoint, extract_swing_points
from app.utils.models import AgentContext, Candle, FeatureSet, MarketRegime, Signal, StrategyOutcome, TradeSide


class PullbackTrendStrategy:
    """Trade bullish pullbacks into higher-low structure with bounded exits."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def generate(
        self,
        context: AgentContext,
        candles: list[Candle],
        features: FeatureSet,
    ) -> StrategyOutcome:
        if features.last_price <= 0 or features.atr <= 0 or not candles:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:invalid_price_or_atr"],
            )

        managed_positions = [
            position
            for position in context.active_swing_positions
            if position.strategy_name in {"", self.__class__.__name__}
        ]
        if managed_positions:
            return self._manage_open_positions(managed_positions, candles, features)

        if context.market_regime is not MarketRegime.BULLISH:
            regime = context.market_regime.value if context.market_regime is not None else "unknown"
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:pullback_regime_blocked", f"regime={regime}"],
            )

        anchor = self._pullback_anchor(candles)
        if anchor is None:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:no_valid_pullback_anchor"],
            )

        anchor_high, anchor_low, prior_high, prior_low = anchor
        if anchor_high.price <= prior_high.price or anchor_low.price <= prior_low.price:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:bullish_structure_not_confirmed"],
            )

        swing_range = anchor_high.price - anchor_low.price
        if swing_range <= 0:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:non_positive_swing_range"],
            )

        retracement = (anchor_high.price - features.last_price) / swing_range
        if not (
            self.config.trading.pullback_min_retracement
            <= retracement
            <= self.config.trading.pullback_max_retracement
        ):
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=[
                    "skip:retracement_out_of_range",
                    f"retracement={retracement:.3f}",
                ],
            )

        if not self._shows_pullback_stabilization(candles):
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:no_price_stabilization"],
            )

        stop_loss = anchor_low.price - (self.config.trading.pullback_stop_atr_multiplier * features.atr)
        if stop_loss >= features.last_price:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:invalid_stop_loss_geometry"],
            )

        size_usd = min(250.0, context.available_cash_usd)
        if size_usd <= 0:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=["skip:no_available_cash"],
            )

        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[
                Signal(
                    side=TradeSide.BUY,
                    symbol=self.config.trading.symbol,
                    size_usd=size_usd,
                    reason="pullback_trend_entry",
                    reference_price=features.last_price,
                    stop_loss=stop_loss,
                    strategy_name=self.__class__.__name__,
                )
            ],
            trace=[
                "decision:bullish_pullback_entry",
                f"anchor_high={anchor_high.price:.2f}",
                f"anchor_low={anchor_low.price:.2f}",
                f"retracement={retracement:.3f}",
                f"stop_loss={stop_loss:.2f}",
                f"signal:pullback_trend_entry size_usd={size_usd:.2f}",
            ],
        )

    def _manage_open_positions(
        self,
        positions: list,
        candles: list[Candle],
        features: FeatureSet,
    ) -> StrategyOutcome:
        signals: list[Signal] = []
        trace: list[str] = []
        for position in positions:
            risk_per_unit = max(position.entry_price - position.stop_loss, 0.0)
            take_profit_price = position.entry_price + (self.config.trading.pullback_take_profit_r * risk_per_unit)
            candles_since_entry = self._candles_since_entry(candles, position.opened_at)
            follow_through_target = position.entry_price * (
                1 + self.config.trading.pullback_follow_through_buffer_percent / 100
            )
            exit_reason: str | None = None
            if risk_per_unit > 0 and features.last_price >= take_profit_price:
                exit_reason = f"pullback_take_profit:{position.position_id}"
            elif (
                candles_since_entry >= self.config.trading.pullback_no_follow_through_candles
                and features.last_price < follow_through_target
            ):
                exit_reason = f"pullback_no_follow_through:{position.position_id}"
            elif features.ema_fast <= features.ema_slow and features.macd_histogram <= 0:
                exit_reason = f"pullback_signal_exit:{position.position_id}"

            if exit_reason is None:
                trace.append(f"hold:pullback_position position_id={position.position_id}")
                continue

            trace.append(f"decision:{exit_reason}")
            signals.append(
                Signal(
                    side=TradeSide.SELL,
                    symbol=position.symbol,
                    size_usd=position.btc_units * features.last_price,
                    reason=exit_reason,
                    reference_price=features.last_price,
                    strategy_name=self.__class__.__name__,
                )
            )
        return StrategyOutcome(strategy_name=self.__class__.__name__, signals=signals, trace=trace)

    @staticmethod
    def _candles_since_entry(candles: list[Candle], opened_at: str) -> int:
        try:
            opened_timestamp = datetime.fromisoformat(opened_at)
        except ValueError:
            return 0
        return sum(1 for candle in candles if candle.timestamp >= opened_timestamp)

    @staticmethod
    def _pullback_anchor(candles: list[Candle]) -> tuple[SwingPoint, SwingPoint, SwingPoint, SwingPoint] | None:
        swings = extract_swing_points(candles, lookback=120, pivot_span=2, min_move_percent=0.2)
        highs = [swing for swing in swings if swing.kind == "high"]
        lows = [swing for swing in swings if swing.kind == "low"]
        if len(highs) < 2 or len(lows) < 2:
            return None

        anchor_high = highs[-1]
        prior_high = highs[-2]
        candidate_lows = [low for low in lows if low.timestamp < anchor_high.timestamp]
        if len(candidate_lows) < 2:
            return None
        anchor_low = candidate_lows[-1]
        prior_low = candidate_lows[-2]
        return anchor_high, anchor_low, prior_high, prior_low

    @staticmethod
    def _shows_pullback_stabilization(candles: list[Candle]) -> bool:
        if not candles:
            return False
        latest = candles[-1]
        candle_range = latest.high - latest.low
        if candle_range <= 0:
            return False

        closes = [candle.close for candle in candles[-3:]]
        recent_low_close = min(closes)
        close_in_upper_half = latest.close >= (latest.low + (candle_range * 0.5))
        close_recovering = latest.close >= recent_low_close
        return close_in_upper_half and close_recovering
