"""Unified settings service - single source of truth for all configuration"""

import json
import os
from pathlib import Path
from typing import Any


class DotDict(dict):
    """Dictionary with dot notation access and nested conversion"""

    def __init__(self, data: dict):
        super().__init__(data)
        for key, value in data.items():
            if isinstance(value, dict):
                self[key] = DotDict(value)
            elif isinstance(value, list):
                self[key] = [DotDict(item) if isinstance(item, dict) else item for item in value]

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"No attribute '{key}'")

    def __setattr__(self, key: str, value: Any):
        self[key] = value


_settings_cache: DotDict | None = None


def _settings_path() -> Path:
    """Resolve the settings file: $EDUPERSONA_SETTINGS_FILE override, else settings.json.

    The override lets tests (and alternate deployments) point at a frozen config
    without touching the developer's working settings.json.
    """
    override = os.environ.get("EDUPERSONA_SETTINGS_FILE")
    return Path(override) if override else Path(__file__).parent.parent / 'settings.json'


def _load_settings() -> DotDict:
    """Load and cache the settings file as DotDict"""
    global _settings_cache
    if _settings_cache is None:
        with open(_settings_path(), 'r') as f:
            _settings_cache = DotDict(json.load(f))
    return _settings_cache


# Global config object
config = _load_settings()


def get_tenant_config(tenant: str) -> DotDict:
    """Get configuration for a specific tenant as DotDict"""
    settings = _load_settings()
    if tenant not in settings['tenants']:
        raise ValueError(f"Unknown tenant: {tenant}")
    return settings['tenants'][tenant]


def reload_settings():
    """Force reload of settings (useful for testing)"""
    global _settings_cache, config
    _settings_cache = None
    config = _load_settings()


def upsert_tenant_admin(tenant: str, user: str, display_name: str, authz: list[str]) -> None:
    """Add or update an admin entry for `tenant` in settings.json, then reload.

    Idempotent on `user` (the OIDC `sub`): an existing entry is updated in place,
    otherwise a new one is appended. Writes the file and refreshes the in-memory cache
    so the auth lookup (get_tenant_config → _load_settings) sees the change at once.
    """
    settings = _load_settings()
    if tenant not in settings['tenants']:
        raise ValueError(f"Unknown tenant: {tenant}")
    admins = settings['tenants'][tenant].setdefault('admins', [])
    entry = {"display_name": display_name, "user": user, "authz": list(authz)}
    for existing in admins:
        if existing.get('user') == user:
            existing.update(entry)
            break
    else:
        admins.append(entry)
    with open(_settings_path(), 'w') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write('\n')
    reload_settings()
