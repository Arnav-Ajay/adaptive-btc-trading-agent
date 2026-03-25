"""Tests for MACD calculations."""

from __future__ import annotations

from app.features.macd import calculate_macd


def test_calculate_macd_produces_non_zero_histogram_for_trending_series() -> None:
    """MACD histogram should reflect separation between MACD and signal on a trend."""
    values = [float(index) for index in range(1, 61)]
    macd_line, signal_line, histogram = calculate_macd(values)
    assert macd_line > 0
    assert signal_line > 0
    assert histogram != 0
