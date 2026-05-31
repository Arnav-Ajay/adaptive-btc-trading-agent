from __future__ import annotations

from app.strategies.profiles import STRATEGY_PROFILES, normalize_strategy_profile, strategy_profile_label


def test_active_strategy_profiles_exclude_frozen_pullback_profiles() -> None:
    """Frozen pullback profiles should not appear in active UI/runtime selection lists."""
    assert "pullback_only" not in STRATEGY_PROFILES
    assert "pullback_hybrid" not in STRATEGY_PROFILES


def test_legacy_pullback_profiles_still_normalize_for_saved_runs() -> None:
    """Historical artifacts using frozen profiles should still render with stable labels."""
    assert normalize_strategy_profile("pullback_only") == "pullback_only"
    assert normalize_strategy_profile("pullback_hybrid") == "pullback_hybrid"
    assert strategy_profile_label("pullback_only") == "Pullback Only"
    assert strategy_profile_label("pullback_hybrid") == "Pullback + DCA"
