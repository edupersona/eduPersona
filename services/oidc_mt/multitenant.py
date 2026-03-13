# Multi-tenant/multi-IDP OIDC authentication

from .oidc_protocol import (
    complete_oidc_flow,
    load_well_known_config,
    prepare_oidc_login,
)
import logging

from nicegui import ui
from services.settings import get_tenant_config

# Module-level configuration - set by initialize_oidc()
_logger = None
_callback_route = '/oidc_callback'
_error_route = '/oidc_error'
_home_route = '/'
_error_handler = None


def initialize_oidc(
    logger=None,
    callback_route='/oidc_callback',
    error_route='/oidc_error',
    home_route='/',
    error_handler=None
):
    """
    Initialize OIDC with app-specific dependencies.

    Args:
        logger: Logger instance (defaults to module logger)
        callback_route: OAuth callback route (default: '/oidc_callback')
        error_route: Error page route (default: '/oidc_error')
        home_route: Default home route for redirects (default: '/')
        error_handler: Custom error handler function
    """
    global _logger, _callback_route, _error_route, _home_route, _error_handler

    _logger = logger or logging.getLogger(__name__)
    _callback_route = callback_route
    _error_route = error_route
    _home_route = home_route
    _error_handler = error_handler

    _logger.info(f"OIDC initialized with callback_route={callback_route}, home_route={home_route}")


def get_logger():
    if _logger:
        return _logger
    return logging.getLogger(__name__)      # log to /dev/null if not configured


def load_oidc_config(tenant: str, idp: str | None) -> dict:
    """Load OIDC configuration from settings.json."""
    if idp is None:
        idp = "default"

    tenant_config = get_tenant_config(tenant)
    config = dict(tenant_config.oidc[idp])  # Convert DotDict to regular dict

    # load .well-known configuration
    well_known_config = load_well_known_config(config['DOTWELLKNOWN'])
    config.update(well_known_config)

    return config


async def start_oidc_login(
    tenant: str,
    idp: str = "default",
    next_url: str = "",
    callback_handler=None,
    **extra_params
):
    """
    Initiate OIDC login flow and redirect to authorization server.
    Uses app.storage.tab for internal OIDC state management.

    Args:
        tenant: Tenant name
        idp: Identity provider name (defaults to "default")
        next_url: URL to redirect to after successful authentication
        callback_handler: Object with result_handler method (e.g., step card)
        **extra_params: Additional OIDC parameters (acr_values, force_login, etc.)
    """
    logger = get_logger()
    logger.info(f"Starting OIDC login for tenant '{tenant}', IDP '{idp}'")

    try:
        config = load_oidc_config(tenant, idp)
    except Exception as e:
        error_msg = f"Failed to load OIDC config for tenant '{tenant}', IDP '{idp}': {str(e)}"
        logger.error(error_msg)
        ui.notify(f'Configuration Error: {error_msg}', type='negative')
        return

    try:

        # Add any extra parameters to config
        for key, value in extra_params.items():
            if value is not None:
                config[key] = value

        # Generate PKCE and auth URL
        auth_url, code_verifier = prepare_oidc_login(config)

        # Ensure client connection before accessing tab storage
        await ui.context.client.connected()

        # Store OIDC state in tab storage (internal to oidc_mt)
        from nicegui import app
        app.storage.tab['oidc_state'] = {
            'code_verifier': code_verifier,
            'tenant': tenant,
            'idp': idp,
            'idp_label': config.get('label', ''),
            'next_url': next_url,
            'callback_handler': callback_handler
        }

        logger.info(f"Authorization URL generated, redirecting to: {auth_url}")
        # Redirect to OIDC provider
        ui.navigate.to(auth_url, new_tab=False)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to start OIDC login. Error: {error_msg}")
        ui.notify(f'OIDC Error: {error_msg}', type='negative')


async def complete_oidc_login(code: str, oidc_state: dict):
    """
    Complete OIDC login flow and delegate result handling to callback handler.
    State is passed explicitly following NiceGUI storage patterns.

    Args:
        code: authorization code from callback
        oidc_state: OIDC state dict passed from page function

    Returns:
        tuple: (userinfo, id_token_claims, token_data, next_url) for direct use,
               or None if callback handler was used
    """
    logger = get_logger()

    if not oidc_state or 'code_verifier' not in oidc_state:
        raise Exception("No code_verifier found - login session may have expired")

    code_verifier = oidc_state['code_verifier']
    tenant = oidc_state.get('tenant', 'default')
    idp = oidc_state.get('idp', 'default')
    next_url = oidc_state.get('next_url', '')
    callback_handler = oidc_state.get('callback_handler')

    logger.debug(f"Completing OIDC flow for tenant '{tenant}', IDP '{idp}'")

    try:
        # Load configuration for this tenant/IDP
        config = load_oidc_config(tenant, idp)

        # Complete generic OIDC flow
        userinfo, id_token_claims, token_data = complete_oidc_flow(code, code_verifier, config)

        logger.info(f"User info retrieved successfully for user: {userinfo.get('sub', '')}")

        # Delegate to callback handler if provided
        if callback_handler:
            logger.debug("Delegating to callback handler")
            # Callback handler should handle putting results into appropriate storage
            await callback_handler(userinfo, id_token_claims, token_data, next_url=next_url)
            return None  # Callback handler manages the results
        else:
            logger.debug("No callback handler - returning results directly")
            return userinfo, id_token_claims, token_data, next_url

    except Exception as e:
        logger.error(f"OIDC flow completion failed: {str(e)}")
        raise
