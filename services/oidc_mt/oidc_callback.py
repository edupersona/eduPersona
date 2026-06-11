# http/s endpoints for OIDC: callback and error pages
# when OIDC login is completed, calls complete_oidc_login with delegated result handling

from nicegui import ui
from .multitenant import complete_oidc_login, get_logger, _callback_route, _error_route, _home_route
from .oidc_protocol import consume_pending_state

PRIMARY_COLOR = 'rgb(59, 130, 246)'

def register_oidc_routes(
    callback_route='/oidc_callback',
    error_route='/oidc_error',
    home_route='/'
):
    """Register OIDC callback routes with configurable paths and handlers."""

    @ui.page(callback_route)
    async def oidc_callback(code: str = "", error: str = "", state: str = ""):
        """Handle OIDC callback from authorization server"""
        logger = get_logger()
        logger.info(f"OIDC callback received - code: {'present' if code else 'missing'}, error: {error}")

        ui.add_css('static/css/base.css')
        ui.colors(primary=PRIMARY_COLOR)
        ui.page_title('Processing Authentication...')

        with ui.column().classes('status-page'):
            if error:
                logger.error(f"OIDC authorization error received: {error}")
                ui.label('Authentication Error').classes('section-heading text-error')
                ui.label(f'Error: {error}').classes('page-subtitle')
                ui.button('Return to Home', on_click=lambda: ui.navigate.to(
                    home_route)).classes('btn-primary')
                return

            if not code:
                logger.error("OIDC callback received without authorization code")
                ui.label('Authentication Error').classes('section-heading text-error')
                ui.label('No authorization code received').classes('page-subtitle')
                ui.button('Return to Home', on_click=lambda: ui.navigate.to(
                    home_route)).classes('btn-primary')
                return

            logger.info("Processing OIDC authorization code")
            ui.label('Processing Authentication...').classes('section-heading')
            ui.spinner(size='lg')

            try:
                logger.debug("Completing OIDC login flow")

                # Ensure client connection before accessing user storage
                await ui.context.client.connected()

                # CSRF binding: `state` must be bound to THIS browser (app.storage.user,
                # cookie-keyed, survives the redirect) AND still live server-side.
                # consume_pending_state checks + removes it from the list in place and pops
                # the registry; None ⇒ forged/expired/replayed → reject before any exchange.
                from nicegui import app
                oidc_state = consume_pending_state(app.storage.user.get('oidc_pending_states', []), state)
                if oidc_state is None:
                    raise Exception("No matching login state - session may have expired or is invalid")

                next_url = oidc_state.get('next_url', '') or home_route

                # Complete login - delegates to callback handler if provided
                await complete_oidc_login(code, oidc_state)

                idp_label = oidc_state.get('idp_label', '')

                # Success - redirect to next URL
                ui.label(f'Inloggen via {idp_label} met succes afgerond').classes('section-heading text-success')
                ui.label('Je wordt doorgestuurd...').classes('page-subtitle')
                ui.timer(2.0, lambda: ui.navigate.to(next_url), once=True)

                logger.info("OIDC authentication completed successfully")

            except Exception as e:
                error_msg = str(e)
                logger.error(f"OIDC authentication failed: {error_msg}")

                ui.label('Authentication Failed').classes('section-heading text-error')
                ui.label(f'Error: {error_msg}').classes('page-subtitle')
                ui.button('Return to Home', on_click=lambda: ui.navigate.to(
                    home_route)).classes('btn-primary')

    @ui.page(error_route)
    def oidc_error_page():
        logger = get_logger()
        logger.error("OIDC error page accessed")

        ui.add_css('static/css/base.css')
        ui.colors(primary='rgb(59, 130, 246)')
        ui.page_title('OIDC Authentication Error')

        with ui.column().classes('status-page'):
            ui.label('Authentication Error').classes('section-heading text-error')
            ui.label('An error occurred during authentication.').classes('page-subtitle')
            ui.label('Please try again or contact support if the problem persists.')

            ui.button('Try Again', on_click=lambda: (logger.info("User clicked 'Try Again' on error page"),
                      ui.navigate.to(home_route))).classes('btn-primary')

    return oidc_callback, oidc_error_page


# For backward compatibility - register default routes
def _register_default_routes():
    """Register default OIDC routes using global configuration."""
    return register_oidc_routes(
        callback_route=_callback_route or '/oidc_callback',
        error_route=_error_route or '/oidc_error',
        home_route=_home_route or '/'
    )


# Note: Auto-registration removed to prevent duplicate routes
# Applications should explicitly call register_oidc_routes() or use initialize_oidc()
