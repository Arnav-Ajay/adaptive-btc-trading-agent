"""Capital allocation helpers."""

from __future__ import annotations

from app.utils.models import PortfolioSnapshot, Signal


class CapitalAllocator:
    """Adjust signal sizing based on portfolio constraints."""

    def allocate(self, signals: list[Signal], snapshot: PortfolioSnapshot) -> list[Signal]:
        """Clamp orders so they do not exceed available cash."""
        remaining_cash = snapshot.cash_usd
        allocated: list[Signal] = []
        for signal in signals:
            if signal.size_usd <= 0:
                continue
            size = min(signal.size_usd, remaining_cash)
            if size <= 0:
                continue
            signal.size_usd = size
            allocated.append(signal)
            remaining_cash -= size
        return allocated
