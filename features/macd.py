"""EMA and MACD calculations."""

from __future__ import annotations


def calculate_ema(values: list[float], period: int) -> float:
    """Calculate an exponential moving average."""
    if not values:
        return 0.0

    multiplier = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
    return ema


def calculate_macd(values: list[float]) -> tuple[float, float, float]:
    """Calculate MACD line, signal line, and histogram."""
    if not values:
        return 0.0, 0.0, 0.0

    ema_fast = calculate_ema(values, period=12)
    ema_slow = calculate_ema(values, period=26)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema([macd_line], period=9)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

