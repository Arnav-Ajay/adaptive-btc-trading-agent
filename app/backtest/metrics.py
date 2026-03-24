"""Backtest and runtime portfolio metrics."""

from __future__ import annotations

from app.utils.models import PortfolioSnapshot


def summarize_portfolio(snapshot: PortfolioSnapshot) -> str:
    """Build a concise human-readable portfolio summary."""
    return (
        f"equity_usd={snapshot.equity_usd:.2f}, "
        f"cash_usd={snapshot.cash_usd:.2f}, "
        f"btc_units={snapshot.btc_units:.6f}, "
        f"drawdown={snapshot.drawdown_percent:.2f}%"
    )
