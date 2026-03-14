from typing import Any

from services.settings import get_tenant_config

def get_tenant_admins(tenant_id: str) -> list[dict[str, Any]]:
    tc = get_tenant_config(tenant_id)
    return tc.admins

def get_tenant_fallback_admins(tenant_id: str) -> list[dict[str, Any]]:
    tc = get_tenant_config(tenant_id)
    return tc.fallback_admins

