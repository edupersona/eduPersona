# http/s endpoints for OIDC: callback and error pages
# when OIDC login is completed, calls complete_oidc_login with delegated result handling

from nicegui import ui
from .multitenant import complete_oidc_login, get_logger, _callback_route, _error_route, _home_route


def register_oidc_routes(
    callback_route='/oidc_callback',
    error_route='/oidc_error',
    home_route='/'
):
    """Register OIDC callback routes with configurable paths and handlers."""

    @ui.page(callback_route)
    async def oidc_callback(code: str = "", error: str = ""):
        """Handle OIDC callback from authorization server"""
        logger = get_logger()
        logger.info(f"OIDC callback received - code: {'present' if code else 'missing'}, error: {error}")

        ui.page_title('Processing Authentication...')

        with ui.column().classes('max-w-2xl mx-auto p-6 text-center'):
            if error:
                logger.error(f"OIDC authorization error received: {error}")
                # Handle authorization error
                ui.label('Authentication Error').classes('text-2xl font-bold text-red-600 mb-4')
                ui.label(f'Error: {error}').classes('text-lg mb-4')
                ui.button('Return to Home', on_click=lambda: ui.navigate.to(
                    home_route)).classes('bg-blue-500 text-white')
                return

            if not code:
                logger.error("OIDC callback received without authorization code")
                ui.label('Authentication Error').classes('text-2xl font-bold text-red-600 mb-4')
                ui.label('No authorization code received').classes('text-lg mb-4')
                ui.button('Return to Home', on_click=lambda: ui.navigate.to(
                    home_route)).classes('bg-blue-500 text-white')
                return

            logger.info("Processing OIDC authorization code")
            # Show loading message
            ui.label('Processing Authentication...').classes('text-xl mb-4')
            ui.spinner(size='lg')

            try:
                logger.debug("Completing OIDC login flow")

                # Ensure client connection before accessing tab storage
                await ui.context.client.connected()

                # Read OIDC state from tab storage (following NiceGUI storage patterns)
                from nicegui import app
                oidc_state = app.storage.tab.get('oidc_state', {})

                # Complete login with explicit state passing
                result = await complete_oidc_login(code, oidc_state)

                # Clean up OIDC state from tab storage
                app.storage.tab.pop('oidc_state', None)

                logger.info("OIDC authentication completed successfully")

                # Handle results
                if result is not None:
                    # Direct results returned - extract next_url
                    userinfo, id_token_claims, token_data, next_url = result
                    # For alarm integration, this is where results would be put into app.storage.user
                    logger.debug("Results returned directly for application handling")
                else:
                    # Callback handler was used - use default home route
                    next_url = home_route

                # Success - redirect to next URL or home
                ui.label('Authentication Successful!').classes('text-xl font-bold text-green-600 mb-4')
                ui.label('Redirecting...').classes('text-lg mb-4')

                # Auto-redirect after a short delay
                redirect_url = next_url if next_url else home_route
                ui.timer(2.0, lambda: ui.navigate.to(redirect_url), once=True)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"OIDC authentication failed: {error_msg}")

                ui.label('Authentication Failed').classes('text-xl font-bold text-red-600 mb-4')
                ui.label(f'Error: {error_msg}').classes('text-lg mb-4')
                ui.button('Return to Home', on_click=lambda: ui.navigate.to(
                    home_route)).classes('bg-blue-500 text-white')

    @ui.page(error_route)
    def oidc_error_page():
        logger = get_logger()
        logger.error("OIDC error page accessed")

        ui.page_title('OIDC Authentication Error')

        with ui.column().classes('max-w-2xl mx-auto p-6'):
            ui.label('Authentication Error').classes('text-2xl font-bold text-red-600 mb-4')
            ui.label('An error occurred during authentication.').classes('text-lg mb-4')
            ui.label('Please try again or contact support if the problem persists.').classes('mb-4')

            ui.button('Try Again', on_click=lambda: (logger.info("User clicked 'Try Again' on error page"),
                      ui.navigate.to(home_route))).classes('bg-blue-500 text-white')

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
