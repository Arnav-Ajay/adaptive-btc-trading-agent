from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.config.settings import load_config
from app.config.sheet_loader import GoogleSheetConfigLoader


def test_google_sheet_loader_parses_valid_rows_and_skips_invalid() -> None:
    """Google Sheets rows should normalize into the nested runtime config mapping."""
    rows = [
        {"section": "trading", "key": "strategy_profile", "value": "swing_only", "type": "str"},
        {"section": "trading", "key": "dca_drop_percent", "value": "2.5", "type": "float"},
        {"section": "execution", "key": "initial_cash_usd", "value": "15000", "type": "float"},
        {"section": "trading", "key": "dca_enabled_in_bearish", "value": "true", "type": "bool"},
        {"section": "llm", "key": "enabled", "value": "false", "type": "bool"},
        {"section": "runtime", "key": "schedule_minutes", "value": "30", "type": "int"},
        {"section": "trading", "key": "OPENAI_API_KEY", "value": "secret", "type": "str"},
        {"section": "trading", "key": "atr_multiplier", "value": "oops", "type": "float"},
    ]

    payload = GoogleSheetConfigLoader._parse_rows(rows)

    assert payload["trading"]["strategy_profile"] == "swing_only"
    assert payload["trading"]["dca_drop_percent"] == 2.5
    assert payload["trading"]["dca_enabled_in_bearish"] is True
    assert payload["execution"]["initial_cash_usd"] == 15000.0
    assert payload["llm"]["enabled"] is False
    assert "runtime" not in payload
    assert "OPENAI_API_KEY" not in payload.get("trading", {})
    assert "atr_multiplier" not in payload.get("trading", {})


def test_google_sheet_loader_returns_empty_when_credentials_file_missing(tmp_path) -> None:
    """Missing service-account files should degrade cleanly to local cache fallback."""
    loader = GoogleSheetConfigLoader(
        enabled=True,
        sheet_id="sheet-123",
        service_account_file=str(tmp_path / "missing-service-account.json"),
    )

    assert loader.load() == {}


def test_google_sheet_loader_uses_service_account_file(monkeypatch, tmp_path) -> None:
    """The loader should authenticate with gspread.service_account(filename=...)."""
    credentials_path = tmp_path / "service-account.json"
    credentials_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeWorksheet:
        def get_all_records(self):
            return [{"section": "trading", "key": "dca_drop_percent", "value": "2.0", "type": "float"}]

    class FakeSheet:
        def worksheet(self, name: str):
            captured["worksheet"] = name
            return FakeWorksheet()

    class FakeClient:
        def open_by_key(self, key: str):
            captured["sheet_id"] = key
            return FakeSheet()

    def fake_service_account(*, filename: str):
        captured["filename"] = filename
        return FakeClient()

    monkeypatch.setitem(sys.modules, "gspread", SimpleNamespace(service_account=fake_service_account))
    loader = GoogleSheetConfigLoader(
        enabled=True,
        sheet_id="sheet-123",
        service_account_file=str(credentials_path),
    )

    payload = loader.load()

    assert captured["filename"] == str(credentials_path)
    assert captured["sheet_id"] == "sheet-123"
    assert captured["worksheet"] == "config"
    assert payload["trading"]["dca_drop_percent"] == 2.0
    assert payload["_meta"]["source"] == "google_sheets"


def test_load_config_uses_fresh_cache_without_calling_sheets(monkeypatch, tmp_path) -> None:
    """Fresh sheet-backed cache should satisfy config loads without a network fetch."""
    cache_path = tmp_path / "config_cache.json"
    cache_payload = {
        "_meta": {
            "source": "google_sheets",
            "sheet_id": "sheet-123",
            "worksheet": "config",
            "fetched_at": (datetime.now(UTC) - timedelta(minutes=15)).replace(microsecond=0).isoformat(),
        },
        "trading": {"dca_drop_percent": 2.25},
    }
    cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")
    runtime_path = tmp_path / "runtime_settings.json"
    runtime_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CONFIG_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(runtime_path))
    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "service-account.json"))

    def fail_load(self):
        raise AssertionError("Fresh cache should skip Google Sheets fetch")

    monkeypatch.setattr(GoogleSheetConfigLoader, "load", fail_load)

    config = load_config()

    assert config.trading.dca_drop_percent == 2.25


def test_load_config_refreshes_stale_cache_and_keeps_precedence(monkeypatch, tmp_path) -> None:
    """Stale cache should refresh from Sheets, then still yield to env and runtime overrides."""
    cache_path = tmp_path / "config_cache.json"
    cache_payload = {
        "_meta": {
            "source": "google_sheets",
            "sheet_id": "sheet-123",
            "worksheet": "config",
            "fetched_at": (datetime.now(UTC) - timedelta(hours=3)).replace(microsecond=0).isoformat(),
        },
        "trading": {"dca_drop_percent": 1.5},
    }
    cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")
    runtime_path = tmp_path / "runtime_settings.json"
    runtime_payload = {"trading": {"dca_drop_percent": 4.5}}
    runtime_path.write_text(json.dumps(runtime_payload), encoding="utf-8")
    monkeypatch.setenv("CONFIG_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(runtime_path))
    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "service-account.json"))
    monkeypatch.setenv("DCA_DROP_PERCENT", "3.5")

    def fake_load(self):
        return {
            "_meta": {
                "source": "google_sheets",
                "sheet_id": "sheet-123",
                "worksheet": "config",
                "fetched_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            },
            "trading": {"dca_drop_percent": 2.5, "strategy_profile": "swing_only"},
            "execution": {"initial_cash_usd": 15000.0},
            "llm": {"enabled": True},
        }

    monkeypatch.setattr(GoogleSheetConfigLoader, "load", fake_load)

    config = load_config()
    refreshed_cache = json.loads(cache_path.read_text(encoding="utf-8"))

    assert config.trading.dca_drop_percent == 4.5
    assert config.trading.strategy_profile == "swing_only"
    assert config.execution.initial_cash_usd == 15000.0
    assert config.llm.enabled is True
    assert refreshed_cache["trading"]["dca_drop_percent"] == 2.5
    assert refreshed_cache["trading"]["strategy_profile"] == "swing_only"
    assert refreshed_cache["execution"]["initial_cash_usd"] == 15000.0


def test_load_config_uses_stale_cache_when_sheet_refresh_fails(monkeypatch, tmp_path) -> None:
    """Failed stale-cache refreshes should keep the last local cache values alive."""
    cache_path = tmp_path / "config_cache.json"
    cache_payload = {
        "_meta": {
            "source": "google_sheets",
            "sheet_id": "sheet-123",
            "worksheet": "config",
            "fetched_at": (datetime.now(UTC) - timedelta(hours=2)).replace(microsecond=0).isoformat(),
        },
        "trading": {"dca_drop_percent": 1.75},
    }
    cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")
    runtime_path = tmp_path / "runtime_settings.json"
    runtime_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CONFIG_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(runtime_path))
    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_SHEETS_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "service-account.json"))

    monkeypatch.setattr(GoogleSheetConfigLoader, "load", lambda self: {})

    config = load_config()

    assert config.trading.dca_drop_percent == 1.75
