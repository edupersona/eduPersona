"""
Common authentication completion logic for admin users.
Handles user lookup, authorization retrieval, and session setup.
"""

from datetime import datetime

from nicegui import app

from ng_loba.utils import logger
from services.auth.users import get_tenant_admins, get_tenant_fallback_admins


async def complete_admin_authentication(
    tenant: str,
    username: str,
    extra_session_data: dict | None = None,
    auto_provision: bool = False
) -> bool:
    """
    Complete admin authentication by looking up user, getting authorization, and setting up session.

    Args:
        tenant: The tenant the user belongs to
        username: The username/uid to authenticate (e.g., OIDC 'sub' claim or fallback username)
        extra_session_data: Additional data to store in session (e.g., OIDC claims)
        auto_provision: Whether to create user if not found (for OIDC auto-provisioning)

    Returns:
        bool: True if authentication completed successfully, False otherwise

    Raises:
        Exception: If user not found and auto_provision is False
    """
    logger.info(f"Completing admin authentication for user: {tenant}/{username}")

    # Look up user in admins list (OIDC users)
    authz = []
    user_found = False

    for admin in get_tenant_admins(tenant):
        if admin.get('user') == username:
            authz = admin.get('authz', [])
            user_found = True
            logger.info(f"OIDC admin user {username} has authorization: {authz}")
            break

    # If not found in OIDC admins, check fallback admins for local login
    if not user_found:
        for admin in get_tenant_fallback_admins(tenant):
            if admin.get('user') == username:
                authz = admin.get('authz', [])
                user_found = True
                logger.info(f"Fallback admin user {username} has authorization: {authz}")
                break

    if not user_found:
        if auto_provision:
            # Auto-provision with no permissions (can be used for OIDC discovery)
            authz = []
            logger.info(f"Auto-provisioned admin user: {username} (no permissions)")
        else:
            raise Exception(f"Admin user {username} not authorized for tenant {tenant}")

    logger.info(f'authz for {username}: {authz}')

    # Prepare session data
    session_data = {
        "tenant": tenant,
        "username": username,
        "authenticated": True,
        "last_activity_datetime": datetime.now(),
        "expired": False,
        "authz": authz,
        "user_type": "admin",  # Distinguish from guest users
        "language": "nl_nl"    # Default language for i18n
    }

    # Add any extra session data
    if extra_session_data:
        session_data.update(extra_session_data)

    # Update session
    app.storage.user.update(session_data)

    logger.info(f"Admin authentication completed for user: {username} with authz: {authz}")
    return True
