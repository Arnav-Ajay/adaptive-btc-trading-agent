"""Composite indicator calculations."""

from __future__ import annotations

from app.features.atr import calculate_atr
from app.features.macd import calculate_ema, calculate_macd
from app.features.rsi import calculate_rsi
from app.utils.models import Candle, FeatureSet


def compute_indicator_bundle(candles: list[Candle]) -> FeatureSet:
    """Compute the main feature bundle for strategy consumption."""
    closes = [candle.close for candle in candles]
    atr = calculate_atr(candles)
    rsi = calculate_rsi(closes)
    ema_fast = calculate_ema(closes, period=12)
    ema_slow = calculate_ema(closes, period=26)
    macd_line, signal_line, histogram = calculate_macd(closes)
    last_price = closes[-1] if closes else 0.0
    return FeatureSet(
        last_price=last_price,
        atr=atr,
        rsi=rsi,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        macd=macd_line,
        macd_signal=signal_line,
        macd_histogram=histogram,
    )
