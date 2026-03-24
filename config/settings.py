"""Configuration loading helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from config.schema import AppConfig
from config.sheet_loader import GoogleSheetConfigLoader


def _load_env() -> dict[str, Any]:
    """Load dotenv-style environment variables if available."""
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    return dict(os.environ)


def _load_local_cache(path: Path) -> dict[str, Any]:
    """Load the local JSON configuration cache."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config() -> AppConfig:
    """Load application configuration from env, sheet, and local cache."""
    env = _load_env()
    cache_path = Path(env.get("CONFIG_CACHE_PATH", "config/config_cache.json"))
    cache_data = _load_local_cache(cache_path)

    sheet_loader = GoogleSheetConfigLoader.from_env(env)
    sheet_data = sheet_loader.load() if sheet_loader.enabled else {}

    merged = {}
    merged.update(cache_data)
    merged.update(sheet_data)
    merged["env"] = env
    merged["cache_path"] = str(cache_path)

    return AppConfig.from_mapping(merged)

