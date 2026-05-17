"""Market regime detection helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.models import Candle, FeatureSet, MarketRegime, RegimeDiagnostics, RegimeScore


@dataclass(slots=True)
class SwingPoint:
    """Simple local swing point used for structure classification."""

    kind: str
    price: float
    timestamp: str


def detect_market_regime(candles: list[Candle], features: FeatureSet) -> MarketRegime:
    """Classify the market regime using the scored regime layer."""
    return detect_regime_score(candles=candles, features=features).regime_label


def detect_regime_score(candles: list[Candle], features: FeatureSet) -> RegimeScore:
    """Compute a continuous regime score from swing structure and momentum."""
    swings = extract_swing_points(
        candles,
        lookback=120,
        pivot_span=2,
        min_move_percent=0.2,
        enforce_alternation=True,
    )
    structure_score, deterioration_score, diagnostics = compute_structure_score(swings=swings, features=features)
    momentum_score, momentum_diag = compute_momentum_score(features=features)
    diagnostics.ema_spread_percent = momentum_diag["ema_spread_percent"]
    diagnostics.rsi_centered = momentum_diag["rsi_centered"]
    diagnostics.macd_histogram_percent = momentum_diag["macd_histogram_percent"]
    diagnostics.atr_percent = momentum_diag["atr_percent"]
    strength = swing_strength(swings)
    regime_score = fuse_scores(
        structure_score=structure_score,
        momentum_score=momentum_score,
        deterioration_score=deterioration_score,
        swing_strength=strength,
    )
    confidence = compute_confidence(
        structure_score=structure_score,
        momentum_score=momentum_score,
        deterioration_score=deterioration_score,
        swing_strength=strength,
        swings=swings,
    )
    regime_label = label_regime(
        regime_score=regime_score,
        confidence=confidence,
        deterioration_score=deterioration_score,
        structure_score=structure_score,
    )
    diagnostics.swing_count = len(swings)
    diagnostics.high_count = sum(1 for swing in swings if swing.kind == "high")
    diagnostics.low_count = sum(1 for swing in swings if swing.kind == "low")
    return RegimeScore(
        regime_label=regime_label,
        structure_score=structure_score,
        momentum_score=momentum_score,
        regime_score=regime_score,
        confidence=confidence,
        deterioration_score=deterioration_score,
        diagnostics=diagnostics,
    )


def detect_structure_regime(candles: list[Candle], features: FeatureSet) -> MarketRegime | None:
    """Legacy strict structure classifier retained for compatibility and debugging."""
    swings = extract_swing_points(candles)
    highs = [swing for swing in swings if swing.kind == "high"]
    lows = [swing for swing in swings if swing.kind == "low"]
    if len(highs) < 3 or len(lows) < 3:
        return None

    latest_high, prior_high, previous_high = highs[-1], highs[-2], highs[-3]
    latest_low, prior_low, previous_low = lows[-1], lows[-2], lows[-3]

    if latest_high.price > prior_high.price > previous_high.price and latest_low.price > prior_low.price > previous_low.price:
        return MarketRegime.BULLISH
    if latest_high.price < prior_high.price < previous_high.price and latest_low.price < prior_low.price < previous_low.price:
        return MarketRegime.BEARISH

    prior_leg_bullish = prior_high.price > previous_high.price and prior_low.price > previous_low.price
    if prior_leg_bullish and features.last_price < prior_low.price:
        return MarketRegime.WEAKENING_BULL

    return MarketRegime.SIDEWAYS


def compute_structure_score(swings: list[SwingPoint], features: FeatureSet) -> tuple[float, float, RegimeDiagnostics]:
    """Convert recent swing structure into directional and deterioration scores."""
    highs = [swing for swing in swings if swing.kind == "high"][-4:]
    lows = [swing for swing in swings if swing.kind == "low"][-4:]
    high_prices = [swing.price for swing in highs]
    low_prices = [swing.price for swing in lows]

    if not high_prices or not low_prices:
        structure_score = 0.0
        if features.ema_fast > features.ema_slow:
            structure_score += 0.35
        else:
            structure_score -= 0.35
        if features.macd_histogram > 0:
            structure_score += 0.25
        else:
            structure_score -= 0.25
        if features.rsi >= 55:
            structure_score += 0.15
        elif features.rsi <= 45:
            structure_score -= 0.15
        deterioration_score = 0.0
        if features.macd_histogram <= 0:
            deterioration_score += 0.25
        if features.ema_fast <= features.ema_slow:
            deterioration_score += 0.4
        if features.rsi <= 45:
            deterioration_score += 0.2
        if features.atr > 0 and features.last_price > 0 and (features.atr / features.last_price) >= 0.01:
            deterioration_score += 0.15
        diagnostics = RegimeDiagnostics(
            swing_count=len(swings),
            high_count=len(highs),
            low_count=len(lows),
            last_price_vs_prior_low=0.0,
        )
        return _clamp(structure_score, -1.0, 1.0), _clamp(deterioration_score, 0.0, 1.0), diagnostics

    rising_high_ratio, falling_high_ratio = _pairwise_direction_ratios(high_prices)
    rising_low_ratio, falling_low_ratio = _pairwise_direction_ratios(low_prices)
    high_move = _normalized_move(high_prices[-1], high_prices[0], scale=max(features.atr * 3.0, features.last_price * 0.015, 1.0))
    low_move = _normalized_move(low_prices[-1], low_prices[0], scale=max(features.atr * 3.0, features.last_price * 0.015, 1.0))

    directional_component = (
        0.35 * (rising_high_ratio - falling_high_ratio)
        + 0.35 * (rising_low_ratio - falling_low_ratio)
        + 0.15 * high_move
        + 0.15 * low_move
    )
    structure_score = _clamp(directional_component, -1.0, 1.0)

    deterioration_score = 0.0
    if len(high_prices) >= 2 and high_prices[-1] < high_prices[-2]:
        deterioration_score += 0.25
    if len(high_prices) >= 3 and high_prices[-1] <= high_prices[-2] <= high_prices[-3]:
        deterioration_score += 0.15
    if len(low_prices) >= 2:
        prior_low = low_prices[-2]
        last_low = low_prices[-1]
        if prior_low > 0:
            low_delta = (last_low - prior_low) / prior_low
            if low_delta < 0.002:
                deterioration_score += 0.25
    if len(low_prices) >= 2 and features.last_price < low_prices[-2]:
        deterioration_score += 0.2
    if features.macd_histogram <= 0:
        deterioration_score += 0.2
    if features.ema_fast <= features.ema_slow:
        deterioration_score += 0.3
    deterioration_score = _clamp(deterioration_score, 0.0, 1.0)

    prior_low = low_prices[-2] if len(low_prices) >= 2 else 0.0
    diagnostics = RegimeDiagnostics(
        swing_count=len(swings),
        high_count=len(highs),
        low_count=len(lows),
        rising_high_ratio=rising_high_ratio,
        rising_low_ratio=rising_low_ratio,
        falling_high_ratio=falling_high_ratio,
        falling_low_ratio=falling_low_ratio,
        last_price_vs_prior_low=((features.last_price - prior_low) / prior_low) if prior_low > 0 else 0.0,
    )
    return structure_score, deterioration_score, diagnostics


def compute_momentum_score(features: FeatureSet) -> tuple[float, dict[str, float]]:
    """Convert indicator momentum into a continuous directional score."""
    price = max(features.last_price, 1.0)
    ema_spread_percent = (features.ema_fast - features.ema_slow) / price
    ema_score = _clamp(ema_spread_percent / 0.01, -1.0, 1.0)
    rsi_score = _clamp((features.rsi - 50.0) / 20.0, -1.0, 1.0)
    macd_histogram_percent = features.macd_histogram / price
    macd_score = _clamp(macd_histogram_percent / 0.002, -1.0, 1.0)
    atr_percent = features.atr / price
    volatility_penalty = _clamp((atr_percent - 0.008) / 0.012, 0.0, 1.0)

    momentum_score = 0.5 * ema_score + 0.3 * rsi_score + 0.2 * macd_score
    momentum_score *= 1.0 - 0.25 * volatility_penalty
    momentum_score = _clamp(momentum_score, -1.0, 1.0)
    return momentum_score, {
        "ema_spread_percent": ema_spread_percent,
        "rsi_centered": (features.rsi - 50.0) / 20.0,
        "macd_histogram_percent": macd_histogram_percent,
        "atr_percent": atr_percent,
    }


def fuse_scores(
    structure_score: float,
    momentum_score: float,
    deterioration_score: float,
    *,
    swing_strength: float,
) -> float:
    """Fuse structure and momentum into a single directional score."""
    structure_weight = _clamp(0.55 + 0.25 * swing_strength, 0.55, 0.8)
    momentum_weight = 1.0 - structure_weight
    score = structure_weight * structure_score + momentum_weight * momentum_score
    if score > 0:
        score -= 0.5 * deterioration_score
    return _clamp(score, -1.0, 1.0)


def compute_confidence(
    *,
    structure_score: float,
    momentum_score: float,
    deterioration_score: float,
    swing_strength: float,
    swings: list[SwingPoint],
) -> float:
    """Estimate how trustworthy the score is."""
    evidence_strength = 0.5 * abs(structure_score) + 0.5 * abs(momentum_score)
    agreement = 1.0 - _clamp(abs(structure_score - momentum_score) / 2.0, 0.0, 1.0)
    pivot_strength = _clamp(max(len(swings) / 8.0, swing_strength), 0.0, 1.0)
    stability = 1.0 - _clamp(deterioration_score, 0.0, 1.0) * 0.35
    return _clamp(0.35 * evidence_strength + 0.35 * agreement + 0.2 * pivot_strength + 0.1 * stability, 0.0, 1.0)


def label_regime(
    regime_score: float,
    confidence: float,
    deterioration_score: float,
    *,
    structure_score: float,
) -> MarketRegime:
    """Map the scored regime back to a stable categorical label."""
    if confidence < 0.4:
        return MarketRegime.TRANSITION
    if structure_score > 0.0 and deterioration_score >= 0.4 and regime_score > -0.35:
        return MarketRegime.WEAKENING_BULL
    if regime_score >= 0.4 and confidence >= 0.5:
        return MarketRegime.WEAKENING_BULL if deterioration_score >= 0.4 else MarketRegime.BULLISH
    if regime_score <= -0.4 and confidence >= 0.5:
        return MarketRegime.BEARISH
    if regime_score >= 0.15 and deterioration_score >= 0.4:
        return MarketRegime.WEAKENING_BULL
    if abs(regime_score) <= 0.15:
        return MarketRegime.SIDEWAYS
    return MarketRegime.TRANSITION if confidence < 0.5 else MarketRegime.SIDEWAYS


def swing_strength(swings: list[SwingPoint]) -> float:
    """Return a simple measure of swing evidence density."""
    highs = sum(1 for swing in swings if swing.kind == "high")
    lows = sum(1 for swing in swings if swing.kind == "low")
    return _clamp((min(highs / 4.0, 1.0) * 0.5) + (min(lows / 4.0, 1.0) * 0.5), 0.0, 1.0)


def extract_swing_points(
    candles: list[Candle],
    lookback: int = 120,
    pivot_span: int = 3,
    min_move_percent: float = 0.3,
    enforce_alternation: bool = True,
) -> list[SwingPoint]:
    """Extract simple local swing highs and lows from recent candles."""
    recent = candles[-lookback:]
    swings: list[SwingPoint] = []
    if len(recent) < (pivot_span * 2) + 1:
        return swings

    for index in range(pivot_span, len(recent) - pivot_span):
        window = recent[index - pivot_span : index + pivot_span + 1]
        center = recent[index]
        if center.high == max(candle.high for candle in window):
            if not swings or swings[-1].kind != "high" or center.high != swings[-1].price:
                if swings and enforce_alternation and swings[-1].kind == "high":
                    if center.high > swings[-1].price:
                        swings[-1] = SwingPoint(
                            kind="high",
                            price=center.high,
                            timestamp=center.timestamp.replace(microsecond=0).isoformat(),
                        )
                    continue
                if swings:
                    last_price = swings[-1].price
                    if last_price > 0:
                        move_percent = abs(center.high - last_price) / last_price * 100
                        if move_percent < min_move_percent:
                            continue
                swings.append(
                    SwingPoint(
                        kind="high",
                        price=center.high,
                        timestamp=center.timestamp.replace(microsecond=0).isoformat(),
                    )
                )
        if center.low == min(candle.low for candle in window):
            if not swings or swings[-1].kind != "low" or center.low != swings[-1].price:
                if swings and enforce_alternation and swings[-1].kind == "low":
                    if center.low < swings[-1].price:
                        swings[-1] = SwingPoint(
                            kind="low",
                            price=center.low,
                            timestamp=center.timestamp.replace(microsecond=0).isoformat(),
                        )
                    continue
                if swings:
                    last_price = swings[-1].price
                    if last_price > 0:
                        move_percent = abs(center.low - last_price) / last_price * 100
                        if move_percent < min_move_percent:
                            continue
                swings.append(
                    SwingPoint(
                        kind="low",
                        price=center.low,
                        timestamp=center.timestamp.replace(microsecond=0).isoformat(),
                    )
                )
    swings.sort(key=lambda swing: swing.timestamp)
    return swings


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_ratio(num: int, den: int) -> float:
    return 0.0 if den <= 0 else num / den


def _pairwise_direction_ratios(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return 0.0, 0.0
    rises = sum(1 for left, right in zip(values[:-1], values[1:], strict=False) if right > left)
    falls = sum(1 for left, right in zip(values[:-1], values[1:], strict=False) if right < left)
    total = len(values) - 1
    return _safe_ratio(rises, total), _safe_ratio(falls, total)


def _normalized_move(latest: float, earliest: float, scale: float) -> float:
    if earliest <= 0 or scale <= 0:
        return 0.0
    raw = (latest - earliest) / earliest
    return _clamp(raw / scale, -1.0, 1.0)
