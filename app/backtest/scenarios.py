"""Backtest scenario definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Scenario:
    """Historical scenario metadata."""

    name: str
    description: str


DEFAULT_SCENARIOS: list[Scenario] = [
    Scenario(name="baseline", description="Default placeholder backtest scenario"),
]

