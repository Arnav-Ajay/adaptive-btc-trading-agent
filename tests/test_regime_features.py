from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.features.indicators import compute_indicator_bundle
from app.features.regime_features import detect_market_regime, detect_regime_score, extract_swing_points
from app.utils.models import Candle, MarketRegime


def _make_candles(closes: list[float]) -> list[Candle]:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    candles: list[Candle] = []
    for index, close in enumerate(closes):
        candles.append(
            Candle(
                timestamp=start + timedelta(minutes=index),
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1.0,
            )
        )
    return candles


def test_extract_swing_points_detects_recent_structure() -> None:
    candles = _make_candles([100, 105, 101, 108, 103, 111, 106, 109, 104, 107])
    swings = extract_swing_points(candles, lookback=20, pivot_span=1, min_move_percent=0.0)
    assert len(swings) >= 4
    assert any(swing.kind == "high" for swing in swings)
    assert any(swing.kind == "low" for swing in swings)


def test_detect_market_regime_returns_bullish_from_structure() -> None:
    candles = _make_candles(
        [
            100, 102, 104, 108, 112, 108, 104,
            105, 108, 112, 118, 112, 108,
            109, 112, 116, 124, 116, 112,
            113, 116, 120, 128, 120, 116,
        ]
    )
    features = compute_indicator_bundle(candles)
    assert detect_market_regime(candles, features) is MarketRegime.BULLISH


def test_detect_market_regime_returns_bearish_from_structure() -> None:
    candles = _make_candles(
        [
            140, 136, 132, 128, 124, 128, 132,
            130, 126, 122, 116, 122, 126,
            124, 120, 116, 108, 116, 120,
            118, 114, 110, 102, 110, 114,
        ]
    )
    features = compute_indicator_bundle(candles)
    assert detect_market_regime(candles, features) is MarketRegime.BEARISH


def test_detect_market_regime_returns_weakening_bull_after_hl_break() -> None:
    candles = _make_candles(
        [
            100, 103, 106, 110, 114, 110, 106,
            108, 112, 116, 122, 116, 112,
            114, 118, 124, 130, 124, 120,
            122, 140, 132, 120, 110, 100, 90, 94, 92, 93,
        ]
    )
    features = compute_indicator_bundle(candles)
    assert detect_market_regime(candles, features) is MarketRegime.WEAKENING_BULL


def test_detect_regime_score_returns_continuous_regime_payload() -> None:
    candles = _make_candles(
        [
            100, 102, 104, 108, 112, 108, 104,
            105, 108, 112, 118, 112, 108,
            109, 112, 116, 124, 116, 112,
            113, 116, 120, 128, 120, 116,
        ]
    )
    features = compute_indicator_bundle(candles)
    score = detect_regime_score(candles, features)

    assert score.regime_label in {
        MarketRegime.BULLISH,
        MarketRegime.WEAKENING_BULL,
        MarketRegime.SIDEWAYS,
        MarketRegime.TRANSITION,
    }
    assert -1.0 <= score.structure_score <= 1.0
    assert -1.0 <= score.momentum_score <= 1.0
    assert -1.0 <= score.regime_score <= 1.0
    assert 0.0 <= score.confidence <= 1.0
