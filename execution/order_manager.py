"""Signal review and order execution."""

from __future__ import annotations

import logging

from config.schema import AppConfig
from execution.paper_broker import PaperBroker
from llm.advisor import LLMAdvisor
from llm.validator import validate_advice
from strategies.capital_allocator import CapitalAllocator
from strategies.portfolio_guard import PortfolioGuard
from utils.models import FeatureSet, MarketRegime, OrderRequest, OrderResult, Signal


logger = logging.getLogger(__name__)


class OrderManager:
    """Validate signals, apply risk constraints, and execute orders."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the order management stack."""
        self.config = config
        self.broker = PaperBroker(config=config)
        self.advisor = LLMAdvisor(config=config)
        self.guard = PortfolioGuard(config=config)
        self.allocator = CapitalAllocator()

    def review_signals(
        self,
        signals: list[Signal],
        features: FeatureSet,
        regime: MarketRegime,
    ) -> list[Signal]:
        """Apply guardrails, optional LLM advice, and capital sizing."""
        snapshot = self.broker.get_portfolio_snapshot()
        if self.guard.trading_paused(snapshot):
            logger.warning("Trading paused due to drawdown limit")
            return []

        advice = self.advisor.review(signals=signals, features=features, regime=regime)
        validated = validate_advice(signals=signals, advice=advice)
        return self.allocator.allocate(validated, snapshot)

    def execute(self, signals: list[Signal]) -> list[OrderResult]:
        """Execute signals on the configured broker."""
        results: list[OrderResult] = []
        for signal in signals:
            price = signal.reference_price if signal.reference_price > 0 else 1.0
            order = OrderRequest(
                side=signal.side,
                symbol=signal.symbol,
                size_usd=signal.size_usd,
                price=price,
            )
            results.append(self.broker.place_order(order))
        return results

