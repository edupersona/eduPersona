"""Unified settings service - single source of truth for all configuration"""

import json
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


def _load_settings() -> DotDict:
    """Load and cache settings.json as DotDict"""
    global _settings_cache
    if _settings_cache is None:
        settings_file = Path(__file__).parent.parent / 'settings.json'
        with open(settings_file, 'r') as f:
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
