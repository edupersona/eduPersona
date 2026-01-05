"""
Authentication and authorization dependencies for route protection.
Based on alarm app patterns adapted for eduIDM.
"""

from datetime import datetime, timedelta
from typing import Callable

from fastapi import HTTPException
from nicegui import app

from services.logging import logger
from utils.helpers import str_to_datetime

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

def check_valid_tenant() -> str:
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

    # Redirect to login page
    raise HTTPException(
        status_code=307,
        detail="Authentication Required",
        headers={"Location": "/m/login"}
    )

def check_authz(scope: str) -> Callable:
    """
    Factory function that creates authorization dependency for specific scope.

    Args:
        scope: Authorization scope required (e.g., 'invite', 'group_admin')

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

def require_admin_auth() -> str:
    """Dependency requiring any admin authentication."""
    return check_valid_tenant()

def require_invite_auth() -> str:
    """Dependency requiring 'invite' authorization."""
    tenant = check_valid_tenant()
    # Check authorization
    authz = app.storage.user.get("authz", [])
    if 'invite' not in authz:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: requires 'invite' permission"
        )
    return tenant

def require_group_admin_auth() -> str:
    """Dependency requiring 'group_admin' authorization."""
    tenant = check_valid_tenant()
    # Check authorization
    authz = app.storage.user.get("authz", [])
    if 'group_admin' not in authz:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: requires 'group_admin' permission"
        )
    return tenant
