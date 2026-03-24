# app/config/sheet_loader.py
"""Google Sheets configuration loader."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GoogleSheetConfigLoader:
    """Placeholder Google Sheets loader with environment-based toggling."""

    enabled: bool
    sheet_id: str | None = None
    service_account_json: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "GoogleSheetConfigLoader":
        """Build a loader from environment variables."""
        enabled = env.get("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
        return cls(
            enabled=enabled,
            sheet_id=env.get("GOOGLE_SHEETS_ID"),
            service_account_json=env.get("GOOGLE_SERVICE_ACCOUNT_JSON"),
        )

    def load(self) -> dict[str, Any]:
        """Load configuration from Google Sheets when enabled."""
        if not self.enabled:
            return {}
        logger.warning(
            "Google Sheets loading is enabled but not implemented yet; using local cache fallback"
        )
        return {}

