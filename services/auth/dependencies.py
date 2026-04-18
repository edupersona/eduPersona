"""
Authentication and authorization dependencies for route protection.
Based on alarm app patterns adapted for eduIDM.
"""

from datetime import datetime, timedelta
from typing import Callable

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
    """Extract tenant from URL path. Returns empty string if not found."""
    path = str(request.url.path)
    parts = path.strip('/').split('/')
    if parts:
        return parts[0]  # First path segment is tenant
    return ""


def check_valid_tenant(request: Request) -> str:
    """
    Dependency to check if user has valid authenticated session.
    Returns tenant if authenticated, raises HTTPException to redirect if not.
    """
    tenant = auth_tenant()
    if tenant:
        if check_inactivity():
            return tenant
        # Session expired - redirect to login
        logger.info(f"Session expired for tenant {tenant}")
    else:
        logger.info("No authenticated session found")

    # Determine redirect tenant: from path, session, or default
    redirect_tenant = _extract_tenant_from_path(request) or tenant or get_default_tenant()
    login_url = f"/{redirect_tenant}/m/login"

    # Redirect to login page
    raise HTTPException(
        status_code=307,
        detail="Authentication Required",
        headers={"Location": login_url}
    )


def check_authz(scope: str) -> Callable:
    """
    Factory function that creates authorization dependency for specific scope.

    Args:
        scope: Authorization scope required (e.g., 'invitations', 'roles')

    Returns:
        Dependency function that checks authorization
    """
    async def dependency():
        authz_ok = scope in app.storage.user.get("authz", [])
        if not authz_ok:
            logger.warning(f"Authorization denied for scope: {scope}")
            raise HTTPException(
                status_code=403,
                detail=f"Unauthorized: requires '{scope}' permission"
            )
        return authz_ok
    return dependency


# Combined dependencies for common patterns

def require_admin_auth(request: Request) -> str:
    """Dependency requiring any admin authentication."""
    return check_valid_tenant(request)


def require_invite_auth(request: Request) -> str:
    """Dependency requiring 'invitations' authorization."""
    tenant = check_valid_tenant(request)
    # Check authorization
    authz = app.storage.user.get("authz", [])
    if 'invitations' not in authz:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: requires 'invitations' permission"
        )
    return tenant


def require_role_admin_auth(request: Request) -> str:
    """Dependency requiring 'roles' authorization."""
    tenant = check_valid_tenant(request)
    # Check authorization
    authz = app.storage.user.get("authz", [])
    if 'roles' not in authz:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: requires 'roles' permission"
        )
    return tenant


def require_guests_auth(request: Request) -> str:
    """Dependency requiring 'guests' authorization."""
    tenant = check_valid_tenant(request)
    authz = app.storage.user.get("authz", [])
    if 'guests' not in authz:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: requires 'guests' permission"
        )
    return tenant


# API key authentication for REST API endpoints

async def require_api_key(request: Request, _key: str | None = Security(_api_key_header)) -> str:
    """Dependency requiring a valid per-tenant API key via X-API-Key header."""
    tenant = _extract_tenant_from_path(request)
    try:
        tc = get_tenant_config(tenant)
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"Unknown tenant: {tenant}"}})

    expected_key = tc.get("api_key", "")
    if not expected_key:
        raise HTTPException(status_code=403, detail={"error": {"code": "API_DISABLED", "message": "API access not configured for this tenant"}})
    api_key = request.headers.get("x-api-key", "")
    if not api_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing API key"}})
    return tenant
