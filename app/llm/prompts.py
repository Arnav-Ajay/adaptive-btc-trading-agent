"""Prompt builders for advisory workflows."""

from __future__ import annotations

import json

from app.utils.models import FeatureSet, LLMInput, MarketRegime, PortfolioSnapshot, Signal


def build_llm_input(
    features: FeatureSet,
    regime: MarketRegime,
    snapshot: PortfolioSnapshot,
) -> LLMInput:
    """Build the compact structured input contract for the LLM."""
    position_size = 0.0 if snapshot.equity_usd <= 0 else snapshot.btc_units
    atr_percent = 0.0 if features.last_price <= 0 else (features.atr / features.last_price) * 100
    trend = "bullish" if features.ema_fast >= features.ema_slow else "bearish"
    if abs(features.ema_fast - features.ema_slow) / max(features.last_price, 1.0) < 0.001:
        trend = "sideways"
    volatility = "high" if atr_percent >= 2.5 else "moderate" if atr_percent >= 1.25 else "low"
    recent_return = 0.0
    if snapshot.avg_entry_price > 0 and features.last_price > 0:
        recent_return = ((features.last_price - snapshot.avg_entry_price) / snapshot.avg_entry_price) * 100
    return LLMInput(
        regime=regime.value,
        trend=trend,
        volatility=volatility,
        rsi=round(features.rsi, 2),
        atr_percent=round(atr_percent, 2),
        recent_return=round(recent_return, 2),
        drawdown=round(snapshot.drawdown_percent, 2),
        position_size=round(position_size, 8),
    )


def build_review_prompt(
    signals: list[Signal],
    features: FeatureSet,
    regime: MarketRegime,
    snapshot: PortfolioSnapshot,
) -> str:
    """Build a bounded review prompt for the paper-trading advisory pass."""
    llm_input = build_llm_input(features=features, regime=regime, snapshot=snapshot)
    payload = {
        "input": {
            "regime": llm_input.regime,
            "trend": llm_input.trend,
            "volatility": llm_input.volatility,
            "rsi": llm_input.rsi,
            "atr_percent": llm_input.atr_percent,
            "recent_return": llm_input.recent_return,
            "drawdown": llm_input.drawdown,
            "position_size": llm_input.position_size,
        },
        "portfolio": {
            "cash_usd": round(snapshot.cash_usd, 2),
            "btc_units": round(snapshot.btc_units, 8),
            "equity_usd": round(snapshot.equity_usd, 2),
            "dca_btc_units": round(snapshot.dca_btc_units, 8),
            "swing_btc_units": round(snapshot.swing_btc_units, 8),
        },
        "signals": [
            {
                "signal_index": index,
                "side": signal.side.value,
                "symbol": signal.symbol,
                "size_usd": round(signal.size_usd, 2),
                "reason": signal.reason,
                "reference_price": round(signal.reference_price, 2),
                "stop_loss": round(signal.stop_loss, 2) if signal.stop_loss is not None else None,
                "strategy_name": signal.strategy_name,
            }
            for index, signal in enumerate(signals)
        ],
        "decision_contract": {
            "decision": {
                "action": "allow | reduce | block",
                "confidence": "0.0 to 1.0",
                "reason": "short, direct explanation",
                "reason_code": "stable enum-like label",
                "score": "-1.0 to 1.0, negative means reject, positive means support",
            },
            "action": "allow | reduce | block",
            "confidence": "0.0 to 1.0",
            "reason": "short, direct explanation",
            "score": "-1.0 to 1.0",
        },
        "example_output": {
            "decision": {
                "action": "block",
                "confidence": 0.85,
                "reason": "Setup is noisy and upside is weak relative to volatility.",
                "reason_code": "NOISY_REGIME",
                "score": -0.82,
            },
            "summary": "Block the trade because the setup is weak.",
            "signal_actions": [
                {
                    "signal_index": 0,
                    "action": "block",
                    "size_multiplier": 0.0,
                    "rationale": "Reject this buy because the setup is noisy.",
                }
            ],
            "parameter_suggestions": {},
        },
        "instructions": {
            "goal": "Act as a BTC risk manager and review the deterministic signals.",
            "constraints": [
                "Do not create new signals.",
                "Stay constrained to risk filtering.",
                "Use allow, reduce, or block only.",
                "Return a top-level decision object every time.",
                "If you cannot evaluate the signals, return decision.action=allow with confidence=0.0, score=0.0 and a reason_code of invalid_contract.",
                "If you do not provide score, the response is invalid.",
                "Keep confidence calibrated.",
                "Prefer block when the setup is noisy, weak, or contradictory.",
                "Respond in JSON only.",
            ],
        },
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
