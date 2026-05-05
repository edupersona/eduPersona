"""
Authentication and authorization dependencies for route protection.
Based on alarm app patterns adapted for eduIDM.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from nicegui import app

from ng_rdm.utils import logger
from ng_rdm.utils.helpers import str_to_datetime
from services.settings import get_tenant_config
from services.tenant import get_default_tenant

# Declares X-API-Key in OpenAPI schema so Swagger UI shows "Authorize" button
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Configuration
INACTIVITY_TIMEOUT = timedelta(hours=2)  # Admin session timeout

# Session management functions


def auth_tenant() -> str:
    """Get authenticated tenant from session, or empty string if not authenticated."""
    if app.storage.user.get("authenticated", False):
        return app.storage.user.get("tenant", "")
    return ""


def check_inactivity() -> bool:
    """Check if session is still active, update activity timestamp if so."""
    last_activity_datetime = app.storage.user.get("last_activity_datetime", datetime.min)
    if isinstance(last_activity_datetime, str):
        last_activity_datetime = str_to_datetime(last_activity_datetime)

    now = datetime.now()
    if now < last_activity_datetime + INACTIVITY_TIMEOUT:
        app.storage.user["last_activity_datetime"] = now
        app.storage.user["expired"] = False
        return True

    app.storage.user["expired"] = True
    return False


def _extract_tenant_from_path(request: Request) -> str:
    """Extract tenant from URL path under namespace-first scheme.

    `/m/{tenant}/...`        → parts[1]
    `/api/v1/{tenant}/...`   → parts[2]
    Other paths              → empty string
    """
    parts = str(request.url.path).strip('/').split('/')
    if len(parts) >= 2 and parts[0] == 'm':
        return parts[1]
    if len(parts) >= 3 and parts[0] == 'api' and parts[1] == 'v1':
        return parts[2]
    return ""


def _redirect_to_login(request: Request, tenant_hint: str, reason: str) -> None:
    """Raise 307 redirect to the tenant login. Single funnel for any auth failure."""
    redirect_tenant = _extract_tenant_from_path(request) or tenant_hint or get_default_tenant()
    logger.info(f"Auth redirect → /m/{redirect_tenant}/login ({reason})")
    raise HTTPException(
        status_code=307,
        detail="Authentication Required",
        headers={"Location": f"/m/{redirect_tenant}/login"},
    )


def check_valid_tenant(request: Request) -> str:
    """Return tenant for an authenticated session; otherwise redirect to login."""
    tenant = auth_tenant()
    if tenant and check_inactivity():
        return tenant
    _redirect_to_login(request, tenant, "no session" if not tenant else "session expired")
    return ""  # unreachable; satisfies type checker


def _require_scope(request: Request, scope: str) -> str:
    """Auth + scope check. Any failure (no session, expired, missing scope) redirects."""
    tenant = check_valid_tenant(request)
    if scope not in app.storage.user.get("authz", []):
        _redirect_to_login(request, tenant, f"missing scope '{scope}'")
    return tenant


def require_admin_auth(request: Request) -> str:
    """Any authenticated admin."""
    return check_valid_tenant(request)


def require_invite_auth(request: Request) -> str:
    return _require_scope(request, 'invitations')


def require_role_admin_auth(request: Request) -> str:
    return _require_scope(request, 'roles')


def require_guests_auth(request: Request) -> str:
    return _require_scope(request, 'guests')


# API key authentication for REST API endpoints

async def require_api_key(request: Request, _key: str | None = Security(_api_key_header)) -> str:
    """Dependency requiring a valid per-tenant API key via X-API-Key header."""
    tenant = _extract_tenant_from_path(request)
    try:
        tc = get_tenant_config(tenant)
    except ValueError:
        raise HTTPException(status_code=404, detail={
                            "error": {"code": "NOT_FOUND", "message": f"Unknown tenant: {tenant}"}})

    expected_key = tc.get("api_key", "")
    if not expected_key:
        raise HTTPException(status_code=403, detail={
                            "error": {"code": "API_DISABLED", "message": "API access not configured for this tenant"}})
    api_key = request.headers.get("x-api-key", "")
    if not api_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail={
                            "error": {"code": "UNAUTHORIZED", "message": "Invalid or missing API key"}})
    return tenant
