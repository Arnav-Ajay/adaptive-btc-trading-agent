"""Validation for LLM advisory output."""

from __future__ import annotations

from utils.models import LLMAdvice, Signal


def validate_advice(signals: list[Signal], advice: LLMAdvice) -> list[Signal]:
    """Return unchanged signals because the LLM cannot directly control trading."""
    _ = advice
    return signals

