"""Supported strategy profiles for backtests and simulations."""

from __future__ import annotations

STRATEGY_PROFILES: tuple[str, ...] = (
    "hybrid_current",
    "dca_only",
    "swing_only",
    "buy_and_hold",
)

LEGACY_STRATEGY_PROFILES: tuple[str, ...] = (
    "pullback_only",
    "pullback_hybrid",
)

STRATEGY_PROFILE_LABELS: dict[str, str] = {
    "hybrid_current": "Hybrid (Current)",
    "dca_only": "DCA Only",
    "swing_only": "Swing Only",
    "buy_and_hold": "Buy & Hold",
    "pullback_only": "Pullback Only",
    "pullback_hybrid": "Pullback + DCA",
}


def normalize_strategy_profile(value: str | None) -> str:
    """Return a valid strategy profile, defaulting to the current live stack."""
    if not value:
        return "hybrid_current"
    normalized = value.strip().lower()
    allowed_profiles = {*STRATEGY_PROFILES, *LEGACY_STRATEGY_PROFILES}
    return normalized if normalized in allowed_profiles else "hybrid_current"


def strategy_profile_label(value: str | None) -> str:
    """Return a readable label for a strategy profile."""
    normalized = normalize_strategy_profile(value)
    return STRATEGY_PROFILE_LABELS.get(normalized, STRATEGY_PROFILE_LABELS["hybrid_current"])
