"""Average true range indicator."""

from __future__ import annotations

from app.utils.models import Candle


def calculate_atr(candles: list[Candle], period: int = 14) -> float:
    """Calculate the average true range from candle data."""
    if len(candles) < 2:
        return 0.0

    true_ranges: list[float] = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        true_range = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        true_ranges.append(true_range)

    window = true_ranges[-period:]
    return sum(window) / len(window) if window else 0.0
