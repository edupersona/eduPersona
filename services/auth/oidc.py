"""
edupersona-specific OIDC interfacing.
Adapter layer between oidc_mt and edupersona application.
"""

from ng_store.utils import logger
from services.auth.completion import complete_admin_authentication
from services.oidc_mt.multitenant import initialize_oidc, load_oidc_config
from services.oidc_mt.oidc_callback import register_oidc_routes


def init_edupersona_oidc():
    """Initialize OIDC_MT with edupersona's dependencies."""
    initialize_oidc(
        logger=logger,
        callback_route='/oidc_callback',
        error_route='/oidc_error',
        home_route='/accept',
        error_handler=None
    )

    # Register callback routes
    register_oidc_routes(
        callback_route='/oidc_callback',
        error_route='/oidc_error',
        home_route='/accept'
    )

    logger.debug("OIDC_MT initialized for edupersona project")


# Admin OIDC result handling

def create_admin_oidc_handler(tenant: str):
    """Factory function that creates an OIDC result handler for admin authentication."""

    async def admin_result_handler(userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = ""):
        """Integrates OIDC results with the edupersona admin authentication system."""
        logger.info(f"Processing admin OIDC results for tenant: {tenant}")

        username = userinfo.get('sub', '')
        if not username:
            raise Exception("OIDC userinfo missing 'sub' claim for username")

        logger.info(f"Looking up admin user: {tenant}/{username}")

        # Check auto-provisioning configuration for admin idp
        # Admin OIDC config is now in oidc_mt/config.json under "admin" idp
        admin_oidc_config = load_oidc_config(tenant, "admin")
        auto_provision = admin_oidc_config.get('auto_provision_users', False)

        # Prepare OIDC-specific session data
        oidc_session_data = {
            "oidc_userinfo": userinfo,
            "oidc_id_token": id_token_claims,
            "oidc_token_data": token_data
        }

        # Use admin authentication completion logic
        await complete_admin_authentication(
            tenant=tenant,
            username=username,
            extra_session_data=oidc_session_data,
            auto_provision=auto_provision
        )

        logger.info(f"Admin OIDC authentication completed for user: {username}")

        # Admin handler takes responsibility for redirect
        from nicegui import ui
        redirect_url = next_url if next_url else "/m/roles"
        logger.info(f"Admin authentication successful, redirecting to: {redirect_url}")
        ui.navigate.to(redirect_url)

    return admin_result_handler
