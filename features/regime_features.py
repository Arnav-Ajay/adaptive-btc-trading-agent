"""Market regime detection helpers."""

from __future__ import annotations

from utils.models import FeatureSet, MarketRegime


def detect_market_regime(features: FeatureSet) -> MarketRegime:
    """Classify the market regime using deterministic indicator thresholds."""
    if features.ema_fast > features.ema_slow and features.rsi >= 55:
        return MarketRegime.BULLISH
    if features.ema_fast < features.ema_slow and features.rsi <= 45:
        return MarketRegime.BEARISH
    return MarketRegime.SIDEWAYS

