# app/data/data_normalizer.py
"""Local data loading and feature orchestration."""

from __future__ import annotations

from app.config.schema import AppConfig
from app.data.parquet_market_data import ParquetMarketDataClient
from app.features.indicators import compute_indicator_bundle
from app.features.regime_features import detect_market_regime
from app.utils.models import Candle, FeatureSet, MarketRegime


class MarketDataService:
    """Coordinate local market data loading and feature generation."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the market data service."""
        self.config = config
        self.client = ParquetMarketDataClient(config=config)

    def fetch_candles(self) -> list[Candle]:
        """Fetch candles from the local parquet data lake."""
        return self.client.fetch_candles()

    def compute_features(self, candles: list[Candle]) -> FeatureSet:
        """Compute the feature set for the current candles."""
        return compute_indicator_bundle(candles)

    def detect_regime(self, features: FeatureSet) -> MarketRegime:
        """Detect the current market regime."""
        return detect_market_regime(features)
