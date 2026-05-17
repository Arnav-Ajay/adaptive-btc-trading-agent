"""Deterministic selector for the pullback + DCA hybrid profile."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import AgentContext, MarketRegime, StrategyOutcome, StrategySelection


class PullbackHybridSelector:
    """Choose whether DCA, pullback, or both are allowed in the current cycle."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def select(self, context: AgentContext, pullback_outcome: StrategyOutcome) -> StrategySelection:
        regime = context.market_regime
        regime_value = regime.value if regime is not None else "unknown"
        open_pullback_position = any(
            position.strategy_name == "PullbackTrendStrategy" for position in context.active_swing_positions
        )
        has_pullback_buy_signal = any(
            signal.strategy_name == "PullbackTrendStrategy" and signal.reason == "pullback_trend_entry"
            for signal in pullback_outcome.signals
        )

        trace = [
            "selector:pullback_hybrid",
            f"selector:regime={regime_value}",
            f"selector:open_pullback_position={open_pullback_position}",
            f"selector:pullback_entry_signal={has_pullback_buy_signal}",
        ]
        btc_allocation_percent = self._btc_allocation_percent(context)
        trace.append(f"selector:btc_allocation_percent={btc_allocation_percent:.2f}")

        if open_pullback_position and self.config.trading.hybrid_dca_suppressed_with_open_pullback_position:
            trace.append("selector:mode=pullback_priority_open_position")
            trace.append("selector:dca=suppressed_open_pullback_position")
            return StrategySelection(
                mode="pullback_priority_open_position",
                allow_dca=False,
                allow_pullback=True,
                trace=trace,
            )

        if has_pullback_buy_signal and self.config.trading.hybrid_dca_suppressed_by_pullback_signal:
            trace.append("selector:mode=pullback_priority_signal")
            trace.append("selector:dca=suppressed_pullback_signal")
            return StrategySelection(
                mode="pullback_priority_signal",
                allow_dca=False,
                allow_pullback=True,
                trace=trace,
            )

        allow_dca = self._dca_allowed_for_regime(regime, btc_allocation_percent=btc_allocation_percent)
        mode = "hybrid_parallel" if allow_dca else "pullback_only_risk_filter"
        trace.append(f"selector:mode={mode}")
        trace.append(f"selector:dca={'allowed' if allow_dca else 'blocked'}")
        return StrategySelection(mode=mode, allow_dca=allow_dca, allow_pullback=True, trace=trace)

    def _dca_allowed_for_regime(self, regime: MarketRegime | None, *, btc_allocation_percent: float) -> bool:
        if regime is MarketRegime.BULLISH:
            if not self.config.trading.hybrid_dca_enabled_in_bullish:
                return False
            return btc_allocation_percent < max(self.config.trading.hybrid_bullish_dca_max_allocation_percent, 0.0)
        if regime is MarketRegime.SIDEWAYS:
            return self.config.trading.hybrid_dca_enabled_in_sideways
        if regime is MarketRegime.WEAKENING_BULL:
            return self.config.trading.hybrid_dca_enabled_in_weakening_bull
        if regime is MarketRegime.BEARISH:
            return self.config.trading.hybrid_dca_enabled_in_bearish
        return False

    @staticmethod
    def _btc_allocation_percent(context: AgentContext) -> float:
        snapshot = context.portfolio_snapshot
        if snapshot is None or snapshot.equity_usd <= 0 or snapshot.last_mark_price <= 0:
            return 0.0
        btc_value_usd = snapshot.btc_units * snapshot.last_mark_price
        return (btc_value_usd / snapshot.equity_usd) * 100
