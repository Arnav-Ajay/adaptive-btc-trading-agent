from __future__ import annotations

from app.backtest.metrics import (
    compute_buy_and_hold_return_percent,
    compute_max_drawdown_percent,
    compute_sharpe_ratio,
)


def test_compute_max_drawdown_percent() -> None:
    equity_curve = [100.0, 120.0, 90.0, 95.0]
    assert round(compute_max_drawdown_percent(equity_curve), 2) == 25.0


def test_compute_buy_and_hold_return_percent() -> None:
    assert round(compute_buy_and_hold_return_percent(100.0, 110.0), 2) == 10.0


def test_compute_sharpe_ratio_handles_flat_curve() -> None:
    assert compute_sharpe_ratio([100.0, 100.0, 100.0], periods_per_year=365) == 0.0

