from typing import Any

from services.settings import get_tenant_config

def get_tenant_admins(tenant_id: str) -> list[dict[str, Any]]:
    tc = get_tenant_config(tenant_id)
    return tc.admins

def get_tenant_fallback_admins(tenant_id: str) -> list[dict[str, Any]]:
    tc = get_tenant_config(tenant_id)
    return tc.fallback_admins

def get_all_tenant_users(tenant_id: str) -> dict[str, list[dict[str, Any]]]:
    """Get both admin and fallback admin users for a specific tenant"""
    return {
        'admins': get_tenant_admins(tenant_id),
        'fallback_admins': get_tenant_fallback_admins(tenant_id)
    }
