"""Prompt builders for advisory workflows."""

from __future__ import annotations

from app.utils.models import FeatureSet, MarketRegime, Signal


def build_review_prompt(
    signals: list[Signal],
    features: FeatureSet,
    regime: MarketRegime,
) -> str:
    """Build a concise structured prompt for advisory review."""
    return (
        f"Regime={regime.value}; "
        f"last_price={features.last_price:.2f}; "
        f"rsi={features.rsi:.2f}; "
        f"atr={features.atr:.2f}; "
        f"signals={len(signals)}"
    )
