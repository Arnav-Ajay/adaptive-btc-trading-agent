"""Backtest engine skeleton."""

from __future__ import annotations

from dataclasses import dataclass

from utils.models import Signal


@dataclass(slots=True)
class BacktestResult:
    """Container for backtest results."""

    signals: list[Signal]
    return_percent: float


class BacktestEngine:
    """Replay historical market data against strategy logic."""

    def run(self) -> BacktestResult:
        """Run a placeholder backtest."""
        return BacktestResult(signals=[], return_percent=0.0)

