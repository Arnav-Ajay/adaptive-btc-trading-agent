"""Backtest and runtime portfolio metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.utils.models import PortfolioSnapshot


@dataclass(slots=True)
class BacktestMetrics:
    """Summary metrics for a backtest run."""

    initial_equity_usd: float
    final_equity_usd: float
    total_return_percent: float
    buy_and_hold_return_percent: float
    max_drawdown_percent: float
    sharpe_ratio: float
    trade_count: int
    filled_trade_count: int
    closed_trade_count: int
    win_rate_percent: float
    avg_win_usd: float
    avg_loss_usd: float
    profit_factor: float


def summarize_portfolio(snapshot: PortfolioSnapshot) -> str:
    """Build a concise human-readable portfolio summary."""
    return (
        f"equity_usd={snapshot.equity_usd:.2f}, "
        f"cash_usd={snapshot.cash_usd:.2f}, "
        f"btc_units={snapshot.btc_units:.6f}, "
        f"drawdown={snapshot.drawdown_percent:.2f}%"
    )


def compute_max_drawdown_percent(equity_curve: list[float]) -> float:
    """Compute max drawdown from an equity curve."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            continue
        drawdown = ((peak - equity) / peak) * 100
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def compute_sharpe_ratio(equity_curve: list[float], periods_per_year: int) -> float:
    """Compute a simple annualized Sharpe ratio from bar-to-bar equity returns."""
    if len(equity_curve) < 2 or periods_per_year <= 0:
        return 0.0
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous <= 0:
            continue
        returns.append((current - previous) / previous)
    if len(returns) < 2:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return 0.0
    return (mean_return / std_dev) * math.sqrt(periods_per_year)


def compute_buy_and_hold_return_percent(
    initial_price: float,
    final_price: float,
) -> float:
    """Compute the simple buy-and-hold return over the replay window."""
    if initial_price <= 0:
        return 0.0
    return ((final_price - initial_price) / initial_price) * 100


def compute_drawdown_series(equity_curve: list[float]) -> list[float]:
    """Compute point-in-time drawdown percentages from an equity curve."""
    if not equity_curve:
        return []
    peak = equity_curve[0]
    series: list[float] = []
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            series.append(0.0)
            continue
        series.append(((peak - equity) / peak) * 100)
    return series


def compute_profit_factor(realized_pnls: list[float]) -> float:
    """Compute profit factor from realized trade PnLs."""
    gross_profit = sum(value for value in realized_pnls if value > 0)
    gross_loss = abs(sum(value for value in realized_pnls if value < 0))
    if gross_loss == 0:
        return gross_profit if gross_profit > 0 else 0.0
    return gross_profit / gross_loss

