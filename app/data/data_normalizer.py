# app/data/data_normalizer.py
"""Local data loading and feature orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.schema import AppConfig
from app.data.parquet_market_data import ParquetMarketDataClient
from app.features.indicators import compute_indicator_bundle
from app.features.regime_features import detect_market_regime, detect_regime_score
from app.utils.models import Candle, FeatureSet, MarketRegime, RegimeScore


class MarketDataService:
    """Coordinate local market data loading and feature generation."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the market data service."""
        self.config = config
        self.client = ParquetMarketDataClient(config=config)

    def fetch_candles(self) -> list[Candle]:
        """Fetch candles from the local parquet data lake."""
        return self.client.fetch_candles()

    def validate_candles(self, candles: list[Candle]) -> tuple[bool, str]:
        """Validate market-data readiness for trading."""
        if len(candles) < self.config.data.min_candles_required:
            return False, f"insufficient_history:{len(candles)}"

        latest_candle = candles[-1].timestamp.astimezone(UTC)
        staleness_minutes = (datetime.now(UTC) - latest_candle).total_seconds() / 60
        if staleness_minutes > self.config.data.max_data_staleness_minutes:
            return False, f"stale_data:{staleness_minutes:.1f}m"

        return True, "ok"

    def compute_features(self, candles: list[Candle]) -> FeatureSet:
        """Compute the feature set for the current candles."""
        return compute_indicator_bundle(candles)

    def detect_regime(self, candles: list[Candle], features: FeatureSet) -> MarketRegime:
        """Detect the current market regime."""
        return detect_market_regime(candles, features)

    def detect_regime_score(self, candles: list[Candle], features: FeatureSet) -> RegimeScore:
        """Detect the scored market regime."""
        return detect_regime_score(candles, features)
