"""
Tenant extraction and validation utilities for multi-tenant application.

Path-based multitenancy: tenant is extracted from URL path (e.g., /uva/accept/...).
"""
from fastapi import HTTPException
from nicegui import app

from ng_loba.utils import logger
from ng_loba.store.multitenancy import valid_tenants


DEFAULT_TENANT = "uva"


def validate_tenant(tenant: str) -> None:
    """Validate that tenant is configured.

    Args:
        tenant: Tenant identifier to validate

    Raises:
        HTTPException: If tenant is not valid
    """
    if tenant not in valid_tenants:
        logger.warning(f"Invalid tenant requested: {tenant}")
        raise HTTPException(status_code=404, detail=f"Unknown tenant: {tenant}")


def get_tenant_from_session() -> str | None:
    """Retrieve tenant from current session.

    Returns:
        Tenant identifier if stored in session, None otherwise
    """
    return app.storage.user.get("tenant")


def store_tenant_in_session(tenant: str) -> None:
    """Store tenant in current session.

    Args:
        tenant: Tenant identifier to store
    """
    app.storage.user["tenant"] = tenant
    logger.debug(f"Stored tenant '{tenant}' in session")


def get_default_tenant() -> str:
    """Get default tenant for redirects and fallbacks.

    Returns:
        Default tenant identifier
    """
    return DEFAULT_TENANT


def get_available_tenants() -> list[str]:
    """Get list of available tenant identifiers.

    Returns:
        List of valid tenant identifiers
    """
    return list(valid_tenants)
