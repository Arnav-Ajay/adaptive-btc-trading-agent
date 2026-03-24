"""Paper trading broker."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.execution.broker_interface import BrokerInterface
from app.utils.models import OrderRequest, OrderResult, PortfolioSnapshot, TradeSide


class PaperBroker(BrokerInterface):
    """In-memory paper broker for safe development and testing."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the simulated broker state."""
        self.cash_usd = config.execution.initial_cash_usd
        self.btc_units = 0.0
        self.last_price = 0.0
        self.peak_equity = self.cash_usd

    def place_order(self, order: OrderRequest) -> OrderResult:
        """Execute a simulated order and update internal balances."""
        self.last_price = order.price
        btc_units = order.size_usd / order.price if order.price > 0 else 0.0

        if order.side is TradeSide.BUY and order.size_usd <= self.cash_usd:
            self.cash_usd -= order.size_usd
            self.btc_units += btc_units
            return OrderResult(accepted=True, order_id=f"paper-{id(order)}", reason="filled")

        if order.side is TradeSide.SELL and btc_units <= self.btc_units:
            self.cash_usd += order.size_usd
            self.btc_units -= btc_units
            return OrderResult(accepted=True, order_id=f"paper-{id(order)}", reason="filled")

        return OrderResult(accepted=False, order_id="", reason="insufficient_balance")

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Return a point-in-time view of the paper portfolio."""
        equity = self.cash_usd + (self.btc_units * self.last_price)
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 0.0 if self.peak_equity == 0 else ((self.peak_equity - equity) / self.peak_equity) * 100
        return PortfolioSnapshot(
            cash_usd=self.cash_usd,
            btc_units=self.btc_units,
            equity_usd=equity,
            drawdown_percent=drawdown,
        )
