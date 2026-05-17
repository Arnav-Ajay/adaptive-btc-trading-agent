"""Signal review and order execution."""

from __future__ import annotations

import logging

from app.config.schema import AppConfig
from app.execution.paper_broker import PaperBroker
from app.llm.advisor import LLMAdvisor
from app.llm.validator import validate_advice
from app.strategies.capital_allocator import CapitalAllocator
from app.strategies.portfolio_guard import PortfolioGuard
from app.utils.models import FeatureSet, MarketRegime, OrderRequest, OrderResult, Signal


logger = logging.getLogger(__name__)


class OrderManager:
    """Validate signals, apply risk constraints, and execute orders."""

    def __init__(self, config: AppConfig, review_policy=None) -> None:
        """Initialize the order management stack."""
        self.config = config
        self.broker = PaperBroker(config=config)
        self.advisor = LLMAdvisor(config=config)
        self.review_policy = review_policy
        self.guard = PortfolioGuard(config=config)
        self.allocator = CapitalAllocator()
        self.last_review_meta: dict[str, object] = {
            "enabled": bool(config.llm.enabled),
            "used": False,
            "status": "not_run",
            "summary": "",
            "action_count": 0,
            "decision": None,
            "decision_present": False,
            "decision_valid": False,
        }

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
            self.last_review_meta = {
                "enabled": bool(self.config.llm.enabled),
                "used": False,
                "status": "trading_paused",
                "summary": "Trading paused due to drawdown limit",
                "action_count": 0,
                "decision": None,
                "decision_present": False,
                "decision_valid": False,
            }
            return []

        reviewer = self.review_policy or self.advisor
        try:
            advice = reviewer.review(signals=signals, features=features, regime=regime, snapshot=snapshot)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("LLM review failed unexpectedly; proceeding with deterministic signals")
            self.last_review_meta = {
                "enabled": bool(self.config.llm.enabled),
                "used": False,
                "status": f"fallback:{exc.__class__.__name__}",
                "summary": f"LLM review failed unexpectedly: {exc}",
                "action_count": 0,
                "decision": None,
                "decision_present": False,
                "decision_valid": False,
            }
            return self.allocator.allocate(signals, snapshot)
        logger.info(
            "LLM review summary=%s reviewed_signals=%s action_count=%s parameter_suggestions=%s",
            advice.summary,
            len(signals),
            len(advice.signal_actions),
            advice.parameter_suggestions,
        )
        self.last_review_meta = {
            "enabled": bool(advice.enabled),
            "used": bool(advice.used),
            "status": advice.status or ("reviewed" if advice.used else "not_used"),
            "summary": advice.summary,
            "action_count": len(advice.signal_actions),
            "decision": (
                {
                    "action": advice.decision.action,
                    "confidence": advice.decision.confidence,
                    "reason": advice.decision.reason,
                    "reason_code": advice.decision.reason_code,
                    "score": advice.decision.score,
                }
                if advice.decision is not None
                else None
            ),
            "decision_present": bool(advice.decision_present),
            "decision_valid": bool(advice.decision_valid),
        }
        validated = validate_advice(signals=signals, advice=advice)
        return self.allocator.allocate(validated, snapshot)

    def execute(self, signals: list[Signal], decision_timestamp: str = "") -> list[OrderResult]:
        """Execute signals on the configured broker."""
        results: list[OrderResult] = []
        for signal in signals:
            price = signal.reference_price if signal.reference_price > 0 else 1.0
            order = OrderRequest(
                side=signal.side,
                symbol=signal.symbol,
                size_usd=signal.size_usd,
                price=price,
                reason=signal.reason,
                stop_loss=signal.stop_loss,
                decision_timestamp=signal.decision_timestamp or decision_timestamp,
                strategy_name=signal.strategy_name,
            )
            results.append(self.broker.place_order(order))
        return results

    def mark_price(self, price: float) -> None:
        """Update broker mark price before signal review or summary generation."""
        self.broker.mark_price(price)

    def evaluate_stop_losses(self) -> list[OrderResult]:
        """Close swing trades whose ATR stop-loss has been hit."""
        return self.broker.evaluate_stop_losses()
