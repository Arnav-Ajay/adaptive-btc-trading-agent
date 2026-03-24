"""Broker abstraction layer."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.utils.models import OrderRequest, OrderResult, PortfolioSnapshot


class BrokerInterface(ABC):
    """Abstract broker contract."""

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult:
        """Place an order with the broker."""

    @abstractmethod
    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Return the current portfolio snapshot."""
