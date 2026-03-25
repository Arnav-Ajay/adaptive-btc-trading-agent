# app/data/coinbase_client.py
"""Coinbase Advanced Trade market data client."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.models import Candle


logger = logging.getLogger(__name__)

INTERVAL_MAP = {
    "1m": ("ONE_MINUTE", 60),
    "5m": ("FIVE_MINUTE", 300),
    "15m": ("FIFTEEN_MINUTE", 900),
    "30m": ("THIRTY_MINUTE", 1800),
    "1h": ("ONE_HOUR", 3600),
    "1d": ("ONE_DAY", 86400),
}


class CoinbaseClientError(RuntimeError):
    """Raised when the Coinbase client cannot be initialized or queried."""


class CoinbaseClient:
    """Coinbase market data adapter with a normalized candle API."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        """Initialize the Coinbase REST client lazily and validate credentials."""
        if not api_key or not api_secret:
            raise CoinbaseClientError("Coinbase API credentials are required")

        try:
            from coinbase.rest import RESTClient
        except ImportError as exc:
            raise CoinbaseClientError(
                "coinbase-advanced-py is not installed; Coinbase data source is unavailable"
            ) from exc

        self.client = RESTClient(api_key=api_key, api_secret=api_secret)

    def get_user_accounts(self) -> list[dict[str, Any]]:
        """Fetch account information from Coinbase."""
        try:
            accounts = self.client.get_accounts()
            return [account.to_dict() for account in accounts.accounts]
        except Exception as exc:
            logger.error("Failed to fetch user accounts: %s", exc)
            return []

    def get_user_account(self) -> list[dict[str, Any]]:
        """Backward-compatible alias for the original account fetch method."""
        return self.get_user_accounts()

    def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[Candle]:
        """Fetch OHLCV candles from Coinbase in ascending timestamp order."""
        granularity, window_seconds = self._resolve_interval(interval)
        end_at = end.astimezone(timezone.utc) if end else datetime.now(timezone.utc)
        if start is None:
            start_at = end_at - timedelta(seconds=window_seconds * max(limit, 1))
        else:
            start_at = start.astimezone(timezone.utc)

        try:
            response = self.client.get_candles(
                product_id=symbol,
                granularity=granularity,
                start=self._format_timestamp(start_at),
                end=self._format_timestamp(end_at),
            )
        except Exception as exc:
            logger.error("Failed to fetch Coinbase candles for %s: %s", symbol, exc)
            return []

        candles = getattr(response, "candles", [])
        parsed: list[Candle] = []
        for candle in candles:
            parsed.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(candle.start), tz=timezone.utc),
                    open=float(candle.open),
                    high=float(candle.high),
                    low=float(candle.low),
                    close=float(candle.close),
                    volume=float(candle.volume),
                )
            )

        parsed.sort(key=lambda item: item.timestamp)
        return parsed

    @staticmethod
    def _resolve_interval(interval: str) -> tuple[str, int]:
        """Resolve the Coinbase granularity enum and seconds-per-candle."""
        resolved = INTERVAL_MAP.get(interval)
        if resolved is None:
            raise ValueError(f"Unsupported Coinbase interval: {interval}")
        return resolved

    @classmethod
    def interval_seconds(cls, interval: str) -> int:
        """Return the seconds-per-candle for a Coinbase interval."""
        _, seconds = cls._resolve_interval(interval)
        return seconds

    @staticmethod
    def _format_timestamp(value: datetime) -> str:
        """Format timestamps for Coinbase API requests."""
        return str(int(value.astimezone(timezone.utc).timestamp()))
