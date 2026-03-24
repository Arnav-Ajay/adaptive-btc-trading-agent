"""Binance market data client interface."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class BinanceClient:
    """Stub Binance client for future exchange integration."""

    def fetch_ohlcv(self, symbol: str, interval: str) -> list[dict[str, float]]:
        """Fetch OHLCV data from Binance."""
        logger.warning("Binance client is not implemented yet for %s @ %s", symbol, interval)
        return []

