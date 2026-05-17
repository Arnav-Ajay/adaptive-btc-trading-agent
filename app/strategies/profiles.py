"""Supported strategy profiles for backtests and simulations."""

from __future__ import annotations

STRATEGY_PROFILES: tuple[str, ...] = (
    "hybrid_current",
    "dca_only",
    "swing_only",
    "pullback_only",
    "pullback_hybrid",
    "buy_and_hold",
)

STRATEGY_PROFILE_LABELS: dict[str, str] = {
    "hybrid_current": "Hybrid (Current)",
    "dca_only": "DCA Only",
    "swing_only": "Swing Only",
    "pullback_only": "Pullback Only",
    "pullback_hybrid": "Pullback + DCA",
    "buy_and_hold": "Buy & Hold",
}


def normalize_strategy_profile(value: str | None) -> str:
    """Return a valid strategy profile, defaulting to the current live stack."""
    if not value:
        return "hybrid_current"
    normalized = value.strip().lower()
    return normalized if normalized in STRATEGY_PROFILES else "hybrid_current"


def strategy_profile_label(value: str | None) -> str:
    """Return a readable label for a strategy profile."""
    normalized = normalize_strategy_profile(value)
    return STRATEGY_PROFILE_LABELS.get(normalized, STRATEGY_PROFILE_LABELS["hybrid_current"])
