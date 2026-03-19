"""
Admin login page supporting both OIDC and fallback authentication.
"""

from fastapi.responses import RedirectResponse
from nicegui import Client, app, ui

from ng_store.utils import logger
from services.auth.completion import complete_admin_authentication
from services.auth.oidc import create_admin_oidc_handler
from services.auth.users import get_tenant_fallback_admins
from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login
from services.tenant import get_default_tenant, validate_tenant
from services.theme import simple_frame
from services.settings import config

@ui.page('/{tenant}/m/login')
async def admin_login_page(client: Client, tenant: str, next_url: str | None = None) -> None:
    """Admin login page supporting both OIDC and fallback authentication."""
    # Validate tenant from path parameter
    validate_tenant(tenant)

    # Default next_url to tenant-scoped roles page
    if not next_url:
        next_url = f"/{tenant}/m/guests"

    # Clear any existing admin session
    if app.storage.user.get("user_type") == "admin":
        app.storage.user.clear()

    # Get tenant fallback admins
    fallback_admins = get_tenant_fallback_admins(tenant)

    # UI state for form
    ui_state = {
        "username": "",
        "password": "",
        "show_fallback": len(fallback_admins) > 0,
        "tenant": tenant
    }

    async def try_oidc_login():
        """Initiate OIDC login using admin idp configuration."""
        try:
            logger.info(f"Starting admin OIDC login for tenant: {tenant}")

            # Create admin-specific OIDC handler
            handler = create_admin_oidc_handler(tenant)

            # Use existing oidc_mt infrastructure
            await start_oidc_login(
                tenant=tenant,
                idp="admin",  # Use admin idp configuration
                next_url=next_url,
                callback_handler=handler
            )

        except Exception as e:
            logger.error(f"OIDC login failed: {e}")
            ui.notify(f"OIDC login failed: {str(e)}", type='negative')

    async def try_fallback_login():
        """Try fallback username/password authentication."""
        username = ui_state['username'].strip()
        password = ui_state['password'].strip()

        if not username or not password:
            ui.notify(_('Username and password are required'), type='negative')
            return

        try:
            logger.info(f"Attempting fallback login for: {tenant}/{username}")

            # Find matching fallback admin
            user_found = False
            for admin in fallback_admins:
                if admin.get('user') == username and admin.get('password') == password:
                    user_found = True
                    break

            if not user_found:
                logger.info(f"Invalid fallback credentials for: {tenant}/{username}")
                ui.notify(_('Invalid username or password'), type='negative')
                return

            # Use admin authentication completion (stores tenant in session)
            await complete_admin_authentication(
                tenant=tenant,
                username=username,
                extra_session_data={"auth_method": "fallback"},
                auto_provision=False
            )

            logger.info(f"Fallback admin login successful: {username}")
            ui.navigate.to(next_url)

        except Exception as e:
            logger.error(f"Fallback authentication failed: {e}")
            ui.notify(_('Authentication failed'), type='negative')

    # if config.get('DTAP') == 'dev':
    #     ui_state['username'] = 'peter'
    #     ui_state['password'] = '12345'
    #     logger.info('Auto-login peter/12345 in dev')
    #     await try_fallback_login()

    with simple_frame('login', tenant):
        with ui.column().classes('centered-content'):
            ui.label(_('eduPersona management: login')).classes('section-heading')

            with ui.column().style('gap: 2rem;'):
                # OIDC Login Card
                with ui.card().tight().classes('login-card'):
                    ui.label('SURFconext').classes('label-heading')
                    ui.button(
                        _('Login with SURFconext'),
                        on_click=try_oidc_login
                    ).classes('btn-primary').style('width: 100%; margin-top: 20px;')

                # Fallback Login Card
                if ui_state['show_fallback']:
                    with ui.card().tight().classes('login-card'):
                        ui.label(_('Local account')).classes('label-heading')
                        ui.input(_('username')).bind_value(
                            ui_state, 'username'
                        ).classes('form-input').on('keydown.enter', try_fallback_login)

                        ui.input(_('password'), password=True).bind_value(
                            ui_state, 'password'
                        ).classes('form-input-last').on('keydown.enter', try_fallback_login)

                        ui.button(
                            _('Login'),
                            on_click=try_fallback_login
                        ).classes('btn-primary').style('width: 100%;')


@ui.page('/{tenant}/m/oidc_login')
async def admin_oidc_login_redirect(tenant: str, next_url: str | None = None) -> None:
    """Initiate OIDC login for admin users."""
    # Validate tenant from path parameter
    validate_tenant(tenant)

    # Default next_url to tenant-scoped roles page
    if not next_url:
        next_url = f"/{tenant}/m/roles"

    logger.info(f"Starting admin OIDC login for tenant: {tenant}, next: {next_url}")

    # Create admin-specific handler to process OIDC results
    handler = create_admin_oidc_handler(tenant)

    # Use oidc_mt with admin-specific callback handler
    await start_oidc_login(
        tenant=tenant,
        idp="admin",
        next_url=next_url,
        callback_handler=handler
    )


@ui.page('/{tenant}/m/logout')
def admin_logout_page(tenant: str) -> RedirectResponse:
    """Clear admin session and redirect to tenant login."""
    logger.info(f"Admin logout for tenant: {tenant}")
    app.storage.user.clear()
    return RedirectResponse(f"/{tenant}/m/login")


# Backward compatibility: redirect old /m/logout to default tenant
@ui.page('/m/logout')
def admin_logout_page_legacy() -> RedirectResponse:
    """Legacy logout route - redirect to default tenant."""
    default_tenant = get_default_tenant()
    app.storage.user.clear()
    return RedirectResponse(f"/{default_tenant}/m/login")
