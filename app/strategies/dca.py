"""Dollar-cost averaging strategy."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import AgentContext, Candle, FeatureSet, MarketRegime, PortfolioSnapshot, Signal, StrategyOutcome, TradeSide


class DCAStrategy:
    """Generate deterministic DCA buy signals."""

    MIN_ORDER_SIZE_USD = 1.0

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

        rebalance_outcome = self._rebalance_outcome(
            context=context,
            mark_price=features.last_price,
        )
        if rebalance_outcome is not None:
            return rebalance_outcome

        regime_gate = self._regime_gate(context)
        if regime_gate is not None:
            return regime_gate

        allocation_percent = self._btc_allocation_percent(
            snapshot=context.portfolio_snapshot,
            mark_price=features.last_price,
        )
        max_allocation_percent = max(self.config.trading.max_btc_allocation_percent, 0.0)
        if allocation_percent >= max_allocation_percent:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=[
                    "skip:btc_allocation_cap_reached",
                    f"btc_allocation_percent={allocation_percent:.2f}",
                    f"max_btc_allocation_percent={max_allocation_percent:.2f}",
                ],
            )

        order_size_usd = self._target_order_size_usd(
            context=context,
            mark_price=features.last_price,
        )
        if order_size_usd < self.MIN_ORDER_SIZE_USD:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=[
                    "skip:dca_order_below_minimum_size",
                    f"target_order_size_usd={order_size_usd:.2f}",
                ],
            )

        latest_dca_buy_price = context.latest_dca_buy_price
        if latest_dca_buy_price is None:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[
                    Signal(
                        side=TradeSide.BUY,
                        symbol=self.config.trading.symbol,
                        size_usd=order_size_usd,
                        reason="initial_dca_entry",
                        reference_price=features.last_price,
                        strategy_name=self.__class__.__name__,
                    )
                ],
                trace=[
                    "decision:no_prior_buy_fill",
                    f"signal:initial_dca_entry size_usd={order_size_usd:.2f}",
                ],
            )

        drop_threshold = latest_dca_buy_price * (1 - self.config.trading.dca_drop_percent / 100)
        if features.last_price <= drop_threshold:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[
                    Signal(
                        side=TradeSide.BUY,
                        symbol=self.config.trading.symbol,
                        size_usd=order_size_usd,
                        reason="price_drop_dca_entry",
                        reference_price=features.last_price,
                        strategy_name=self.__class__.__name__,
                    )
                ],
                trace=[
                    f"decision:price_below_drop_threshold threshold={drop_threshold:.2f}",
                    f"signal:price_drop_dca_entry size_usd={order_size_usd:.2f}",
                ],
            )

        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[],
            trace=[
                f"skip:price_above_drop_threshold latest_buy_fill_price={latest_dca_buy_price:.2f}",
                f"latest_dca_buy_price={latest_dca_buy_price:.2f}",
                f"threshold:required_price_at_or_below={drop_threshold:.2f}",
                f"observed:last_price={features.last_price:.2f}",
            ],
        )

    def _rebalance_outcome(self, context: AgentContext, mark_price: float) -> StrategyOutcome | None:
        """Return a partial-sell decision when regime targets require lower BTC exposure."""
        snapshot = context.portfolio_snapshot
        if snapshot is None or mark_price <= 0 or snapshot.dca_btc_units <= 0:
            return None

        target_allocation_percent = self._target_allocation_percent(context.market_regime)
        if target_allocation_percent is None:
            return None

        current_allocation_percent = self._btc_allocation_percent(snapshot=snapshot, mark_price=mark_price)
        tolerance_percent = max(self.config.trading.rebalance_tolerance_percent, 0.0)
        if current_allocation_percent <= target_allocation_percent + tolerance_percent:
            return None

        total_equity_usd = snapshot.cash_usd + (snapshot.btc_units * mark_price)
        current_btc_value_usd = snapshot.btc_units * mark_price
        target_btc_value_usd = total_equity_usd * (target_allocation_percent / 100)
        excess_btc_value_usd = max(0.0, current_btc_value_usd - target_btc_value_usd)
        max_cycle_sell_usd = snapshot.dca_btc_units * mark_price * min(
            max(self.config.trading.rebalance_max_sell_fraction, 0.0),
            1.0,
        )
        sell_size_usd = min(excess_btc_value_usd, max_cycle_sell_usd)
        if sell_size_usd < self.MIN_ORDER_SIZE_USD:
            return None

        regime_value = context.market_regime.value if context.market_regime is not None else "unknown"
        return StrategyOutcome(
            strategy_name=self.__class__.__name__,
            signals=[
                Signal(
                    side=TradeSide.SELL,
                    symbol=self.config.trading.symbol,
                    size_usd=sell_size_usd,
                    reason=f"dca_rebalance_sell:{regime_value}",
                    reference_price=mark_price,
                    strategy_name=self.__class__.__name__,
                )
            ],
            trace=[
                "decision:rebalance_reduce_btc_exposure",
                f"regime={regime_value}",
                f"btc_allocation_percent={current_allocation_percent:.2f}",
                f"target_btc_allocation_percent={target_allocation_percent:.2f}",
                f"rebalance_tolerance_percent={tolerance_percent:.2f}",
                f"signal:dca_rebalance_sell size_usd={sell_size_usd:.2f}",
            ],
        )

    def _regime_gate(self, context: AgentContext) -> StrategyOutcome | None:
        """Return a skip outcome when the current regime blocks new DCA entries."""
        regime = context.market_regime
        if regime is MarketRegime.BEARISH and not self.config.trading.dca_enabled_in_bearish:
            return StrategyOutcome(
                strategy_name=self.__class__.__name__,
                signals=[],
                trace=[
                    "skip:dca_regime_blocked",
                    "regime=bearish",
                ],
            )
        return None

    def _target_order_size_usd(self, context: AgentContext, mark_price: float) -> float:
        """Scale and cap the desired DCA order size for the current state."""
        requested_size_usd = self.config.trading.dca_order_size_usd
        if context.market_regime is MarketRegime.WEAKENING_BULL:
            requested_size_usd *= max(self.config.trading.dca_weakening_bull_size_multiplier, 0.0)
        if requested_size_usd <= 0:
            return 0.0

        remaining_capacity_usd = self._remaining_btc_capacity_usd(
            snapshot=context.portfolio_snapshot,
            mark_price=mark_price,
        )
        return min(requested_size_usd, context.available_cash_usd, remaining_capacity_usd)

    def _remaining_btc_capacity_usd(self, snapshot: PortfolioSnapshot | None, mark_price: float) -> float:
        """Return remaining BTC exposure headroom under the allocation cap."""
        if snapshot is None or mark_price <= 0:
            return self.config.trading.dca_order_size_usd
        btc_value_usd = snapshot.btc_units * mark_price
        total_equity_usd = snapshot.cash_usd + btc_value_usd
        if total_equity_usd <= 0:
            return 0.0
        max_btc_value_usd = total_equity_usd * (max(self.config.trading.max_btc_allocation_percent, 0.0) / 100)
        return max(0.0, max_btc_value_usd - btc_value_usd)

    def _target_allocation_percent(self, regime: MarketRegime | None) -> float | None:
        """Return the desired BTC allocation for regimes that should reduce exposure."""
        if regime is MarketRegime.WEAKENING_BULL:
            return max(self.config.trading.weakening_bull_target_allocation_percent, 0.0)
        if regime is MarketRegime.BEARISH:
            return max(self.config.trading.bearish_target_allocation_percent, 0.0)
        return None

    @staticmethod
    def _btc_allocation_percent(snapshot: PortfolioSnapshot | None, mark_price: float) -> float:
        """Compute current BTC exposure as a share of total marked portfolio equity."""
        if snapshot is None or mark_price <= 0:
            return 0.0
        btc_value_usd = snapshot.btc_units * mark_price
        total_equity_usd = snapshot.cash_usd + btc_value_usd
        if total_equity_usd <= 0:
            return 0.0
        return (btc_value_usd / total_equity_usd) * 100
