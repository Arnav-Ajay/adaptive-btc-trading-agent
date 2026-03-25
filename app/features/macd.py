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


def calculate_ema_series(values: list[float], period: int) -> list[float]:
    """Calculate the full EMA series for a list of values."""
    if not values:
        return []

    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    ema = values[0]
    for value in values[1:]:
        ema = (value - ema) * multiplier + ema
        ema_values.append(ema)
    return ema_values


def calculate_macd(values: list[float]) -> tuple[float, float, float]:
    """Calculate MACD line, signal line, and histogram."""
    if not values:
        return 0.0, 0.0, 0.0

    ema_fast_series = calculate_ema_series(values, period=12)
    ema_slow_series = calculate_ema_series(values, period=26)
    macd_series = [fast - slow for fast, slow in zip(ema_fast_series, ema_slow_series)]
    macd_line = macd_series[-1]
    signal_line = calculate_ema(macd_series, period=9)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
