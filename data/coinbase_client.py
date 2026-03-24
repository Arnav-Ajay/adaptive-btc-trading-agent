"""Coinbase market data client interface."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class CoinbaseClient:
    """Stub Coinbase data client for future exchange integration."""

    def fetch_ohlcv(self, symbol: str, interval: str) -> list[dict[str, float]]:
        """Fetch OHLCV data from Coinbase."""
        logger.warning("Coinbase client is not implemented yet for %s @ %s", symbol, interval)
        return []

