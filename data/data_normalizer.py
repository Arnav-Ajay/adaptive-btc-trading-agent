"""Data normalization and feature orchestration."""

from __future__ import annotations

from config.schema import AppConfig
from data.yfinance_client import YFinanceClient
from features.indicators import compute_indicator_bundle
from features.regime_features import detect_market_regime
from utils.models import Candle, FeatureSet, MarketRegime


class MarketDataService:
    """Coordinate market data fetching and feature generation."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the market data service."""
        self.config = config
        self.primary_client = YFinanceClient()

    def fetch_candles(self) -> list[Candle]:
        """Fetch and normalize candles from the primary market data source."""
        raw_records = self.primary_client.fetch_ohlcv(
            symbol=self.config.trading.symbol,
            interval=self.config.trading.interval,
        )
        return [
            Candle(
                timestamp=record["timestamp"],
                open=record["open"],
                high=record["high"],
                low=record["low"],
                close=record["close"],
                volume=record["volume"],
            )
            for record in raw_records
        ]

    def compute_features(self, candles: list[Candle]) -> FeatureSet:
        """Compute the feature set for the current candles."""
        return compute_indicator_bundle(candles)

    def detect_regime(self, features: FeatureSet) -> MarketRegime:
        """Detect the current market regime."""
        return detect_market_regime(features)
