"""Maintenance endpoint for a daily cron — expires overdue invitations across all tenants.

Top-level (non-tenant) route, guarded by the global `cleanup_api_key` via the
`X-Cleanup-Key` header (not the per-tenant API key). The sweep is idempotent, so
repeated cron hits are safe.

    POST /maintenance   (header: X-Cleanup-Key)
"""
from fastapi import Header

from domain.invitations import expire_overdue_invitations
from services.settings import config

from . import api_router
from .common import api_error, api_response


@api_router.post("/maintenance")
async def run_maintenance(x_cleanup_key: str | None = Header(default=None)):
    """Flip overdue pending invitations to 'expired'. Cron-triggered, key-guarded."""
    expected = config.get("cleanup_api_key") or ""
    if not expected:
        raise api_error("DISABLED", "maintenance not configured", status_code=503)
    if x_cleanup_key != expected:
        raise api_error("UNAUTHORIZED", "invalid cleanup key", status_code=401)
    return api_response({"expired_count": await expire_overdue_invitations()})
