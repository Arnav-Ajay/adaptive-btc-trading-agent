"""Yahoo Finance market data client."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class YFinanceClient:
    """Fetch BTC market data from Yahoo Finance."""

    def fetch_ohlcv(self, symbol: str, interval: str) -> list[dict[str, Any]]:
        """Fetch OHLCV records from yfinance if the dependency is available."""
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance is not installed; returning empty market data")
            return []

        interval_mapping = {"1h": "60m", "4h": "1h", "1d": "1d"}
        ticker = yf.Ticker(symbol)
        frame = ticker.history(period="10d", interval=interval_mapping.get(interval, "60m"))
        if frame.empty:
            logger.warning("No yfinance data returned for %s", symbol)
            return []

        records: list[dict[str, Any]] = []
        for timestamp, row in frame.iterrows():
            records.append(
                {
                    "timestamp": timestamp.to_pydatetime(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                }
            )
        return records

