"""Basic smoke tests for the project scaffold."""

from __future__ import annotations

from config.settings import load_config
from features.rsi import calculate_rsi


def test_load_config_returns_symbol() -> None:
    """Ensure the config loader returns the default trading symbol."""
    config = load_config()
    assert config.trading.symbol == "BTC-USD"


def test_rsi_default_value_for_short_series() -> None:
    """Ensure RSI returns a neutral default for short input."""
    assert calculate_rsi([1.0, 2.0, 3.0]) == 50.0
