"""
Admin login page supporting both OIDC and fallback authentication.
"""

from fastapi.responses import RedirectResponse
from nicegui import Client, app, ui

from services.auth.completion import complete_admin_authentication
from services.auth.oidc import create_admin_oidc_handler
from services.auth.users import get_tenant_fallback_admins
from services.logging import logger
from services.oidc_mt.multitenant import start_oidc_login


@ui.page('/m/login')
@ui.page('/m/login/{tenant}')
async def admin_login_page(client: Client, tenant: str = "uva", next_url: str = "/m/groups") -> None:
    """Admin login page supporting both OIDC and fallback authentication."""
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
            ui.notify("Username and password are required", type='negative')
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
                ui.notify("Invalid username or password", type='negative')
                return

            # Use admin authentication completion
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
            ui.notify(f"Authentication failed: {str(e)}", type='negative')

    # Page layout
    ui.page_title("Admin Login - eduPersona")

    with ui.column().classes('mx-auto p-6').style('width: 400px; margin-top: 100px;'):
        with ui.card().classes('w-full p-6'):
            ui.label('eduPersona Admin Login').classes('text-2xl font-bold text-center mb-6')
            ui.label(f'Tenant: {tenant}').classes('text-sm text-gray-600 text-center mb-4')

            # OIDC Login (Primary method) - assume admin OIDC exists
            with ui.column().classes('w-full mb-6'):
                ui.label('SURFconext Login').classes('font-semibold mb-2')
                ui.button(
                    'Login with SURFconext',
                    on_click=try_oidc_login
                ).classes('w-full bg-blue-600 text-white')

            # Separator if fallback method also available
            if ui_state['show_fallback']:
                with ui.row().classes('w-full items-center my-4'):
                    ui.separator().classes('flex-1')
                    ui.label('or').classes('px-3 text-gray-500')
                    ui.separator().classes('flex-1')

            # Fallback Login Form
            if ui_state['show_fallback']:
                with ui.column().classes('w-full'):
                    ui.label('Local Login').classes('font-semibold mb-2')
                    ui.input('Username').bind_value(
                        ui_state, 'username'
                    ).classes('w-full mb-3').on('keydown.enter', try_fallback_login)

                    ui.input('Password', password=True).bind_value(
                        ui_state, 'password'
                    ).classes('w-full mb-4').on('keydown.enter', try_fallback_login)

                    ui.button(
                        'Login',
                        on_click=try_fallback_login
                    ).classes('w-full bg-gray-600 text-white')


@ui.page('/m/oidc_login/{tenant}')
async def admin_oidc_login_redirect(tenant: str = "uva", next_url: str = "/m/groups") -> None:
    """Initiate OIDC login for admin users."""
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


@ui.page('/m/logout')
def admin_logout_page() -> RedirectResponse:
    """Clear admin session and redirect."""
    logger.info("Admin logout")
    app.storage.user.clear()
    return RedirectResponse("/m/login")
