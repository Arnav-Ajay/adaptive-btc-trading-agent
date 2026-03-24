"""Coinbase execution stub."""

from __future__ import annotations

import logging

from app.utils.models import OrderRequest, OrderResult


logger = logging.getLogger(__name__)


class CoinbaseExecutor:
    """Placeholder real-execution adapter."""

    def place_order(self, order: OrderRequest) -> OrderResult:
        """Reject live orders until the adapter is implemented."""
        logger.warning("Coinbase execution is not enabled for live trading")
        return OrderResult(accepted=False, order_id="", reason="not_implemented")
