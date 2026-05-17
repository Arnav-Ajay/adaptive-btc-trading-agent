"""Validation for LLM advisory output."""

from __future__ import annotations

from app.utils.models import LLMAdvice, Signal


def validate_advice(signals: list[Signal], advice: LLMAdvice) -> list[Signal]:
    """Apply bounded LLM review actions to already-generated signals."""
    if not advice.signal_actions:
        return signals

    actions_by_index = {action.signal_index: action for action in advice.signal_actions}
    validated: list[Signal] = []
    for index, signal in enumerate(signals):
        action = actions_by_index.get(index)
        if action is None or action.action == "allow":
            validated.append(signal)
            continue
        if action.action == "block":
            continue
        if action.action == "reduce":
            reduced_size_usd = signal.size_usd * action.size_multiplier
            if reduced_size_usd > 0:
                validated.append(
                    Signal(
                        side=signal.side,
                        symbol=signal.symbol,
                        size_usd=reduced_size_usd,
                        reason=signal.reason,
                        reference_price=signal.reference_price,
                        stop_loss=signal.stop_loss,
                        strategy_name=signal.strategy_name,
                    )
                )
    return validated
