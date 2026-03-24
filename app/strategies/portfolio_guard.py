"""Portfolio safeguard logic."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.utils.models import PortfolioSnapshot


class PortfolioGuard:
    """Block new trades when portfolio risk exceeds configured thresholds."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the portfolio guard."""
        self.config = config

    def trading_paused(self, snapshot: PortfolioSnapshot) -> bool:
        """Return whether trading should pause due to drawdown."""
        return snapshot.drawdown_percent >= self.config.trading.max_drawdown_percent
