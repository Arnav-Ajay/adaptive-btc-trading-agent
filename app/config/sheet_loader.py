# app/config/sheet_loader.py
"""Google Sheets configuration loader."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


WORKSHEET_NAME = "config"
ALLOWED_KEYS: dict[str, set[str]] = {
    "trading": {
        "strategy_profile",
        "dca_drop_percent",
        "dca_order_size_usd",
        "dca_enabled_in_bearish",
        "dca_weakening_bull_size_multiplier",
        "max_btc_allocation_percent",
        "weakening_bull_target_allocation_percent",
        "bearish_target_allocation_percent",
        "rebalance_tolerance_percent",
        "rebalance_max_sell_fraction",
        "swing_enabled_in_weakening_bull",
        "swing_enabled_in_sideways",
        "swing_enabled_in_bearish",
        "atr_multiplier",
        "swing_entry_rsi_max",
        "swing_take_profit_percent",
        "swing_no_follow_through_candles",
        "swing_follow_through_buffer_percent",
        "max_drawdown_percent",
    },
    "data": {
        "trading_lookback",
        "dashboard_lookback",
        "min_candles_required",
        "max_data_staleness_minutes",
    },
    "execution": {
        "initial_cash_usd",
        "execution_cost_preset",
        "paper_fee_bps",
        "fee_pct",
        "spread_pct",
        "slippage_pct",
    },
    "llm": {
        "enabled",
    },
}
SUPPORTED_TYPES = {"float", "int", "bool", "str"}
SECRET_KEY_TOKENS = {
    "api_key",
    "api_secret",
    "service_account",
    "bot_token",
    "app_password",
    "username",
    "chat_id",
}


@dataclass(slots=True)
class GoogleSheetConfigLoader:
    """Google Sheets loader with environment-based toggling."""

    enabled: bool
    sheet_id: str | None = None
    service_account_file: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "GoogleSheetConfigLoader":
        """Build a loader from environment variables."""
        enabled = env.get("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
        return cls(
            enabled=enabled,
            sheet_id=env.get("GOOGLE_SHEETS_ID"),
            service_account_file=env.get("GOOGLE_SERVICE_ACCOUNT_FILE"),
        )

    def load(self) -> dict[str, Any]:
        """Load configuration from Google Sheets when enabled."""
        if not self.enabled:
            return {}
        if not self.sheet_id:
            logger.warning("Google Sheets is enabled but GOOGLE_SHEETS_ID is missing; using local cache fallback")
            return {}
        if not self.service_account_file:
            logger.warning(
                "Google Sheets is enabled but GOOGLE_SERVICE_ACCOUNT_FILE is missing; using local cache fallback"
            )
            return {}

        credentials_path = Path(self.service_account_file)
        if not credentials_path.exists():
            logger.warning(
                "Google Sheets credentials file does not exist at %s; using local cache fallback",
                credentials_path,
            )
            return {}

        try:
            import gspread
        except ImportError:
            logger.warning("gspread is not installed; using local cache fallback")
            return {}

        try:
            client = gspread.service_account(filename=str(credentials_path))
            worksheet = client.open_by_key(self.sheet_id).worksheet(WORKSHEET_NAME)
            rows = worksheet.get_all_records()
        except Exception as exc:
            logger.warning("Failed to load Google Sheets config; using local cache fallback: %s", exc)
            return {}

        payload = self._parse_rows(rows)
        if not payload:
            logger.warning("Google Sheets config returned no valid rows; using local cache fallback")
            return {}
        payload["_meta"] = {
            "source": "google_sheets",
            "sheet_id": self.sheet_id,
            "worksheet": WORKSHEET_NAME,
            "fetched_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
        return payload

    @classmethod
    def _parse_rows(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Normalize sheet rows into the nested config mapping expected by load_config."""
        payload: dict[str, Any] = {}
        for raw_row in rows:
            row = {str(key).strip().lower(): value for key, value in raw_row.items()}
            section = str(row.get("section", "")).strip().lower()
            key = str(row.get("key", "")).strip()
            raw_value = row.get("value")
            value_type = str(row.get("type", "")).strip().lower()
            if not section or not key or raw_value in {None, ""} or not value_type:
                logger.warning("Skipping incomplete Google Sheets config row: %s", raw_row)
                continue
            if value_type not in SUPPORTED_TYPES:
                logger.warning("Skipping Google Sheets config row with unsupported type=%s key=%s", value_type, key)
                continue
            normalized_key = key.lower()
            if any(token in normalized_key for token in SECRET_KEY_TOKENS):
                logger.warning("Skipping secret-like Google Sheets config key=%s", key)
                continue
            allowed_section_keys = ALLOWED_KEYS.get(section)
            if allowed_section_keys is None or key not in allowed_section_keys:
                logger.warning("Skipping unsupported Google Sheets config setting %s.%s", section, key)
                continue
            try:
                value = cls._coerce_value(raw_value, value_type)
            except ValueError:
                logger.warning("Skipping Google Sheets config row with invalid value for %s.%s", section, key)
                continue
            section_payload = dict(payload.get(section, {}))
            section_payload[key] = value
            payload[section] = section_payload
        return payload

    @staticmethod
    def _coerce_value(raw_value: Any, value_type: str) -> float | int | bool | str:
        """Convert a Google Sheets cell value into the expected primitive type."""
        if value_type == "float":
            return float(raw_value)
        if value_type == "int":
            return int(raw_value)
        if value_type == "bool":
            normalized = str(raw_value).strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValueError("invalid_bool")
        return str(raw_value).strip()

