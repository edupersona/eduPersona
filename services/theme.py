from contextlib import contextmanager

from ng_rdm.components import Col, rdm_init
from nicegui import app, ui

from services.settings import get_tenant_config

pages = {
    # possible menu entries, depending on authz (order: guests - roles - invitations):
    'guests': {'path': 'm/guests', 'label': 'gasten'},
    'roles': {'path': 'm/roles', 'label': 'rollen'},
    'invitations': {'path': 'm/invitations', 'label': 'uitnodigingen'},
    'accept': {'path': 'accept', 'label': 'accepteren'},
    # other pages:
    'apps': {'path': 'apps', 'label': 'mijn diensten'},
    'login': {'path': 'm/login', 'label': 'inloggen'},
    'home': {'path': '/', 'label': 'home'},
}

@ui.refreshable
def main_menu(navtitle: str, tenant: str) -> None:
    """Create main navigation menu with authorization checking."""
    authz = app.storage.user.get("authz", [])
    if app.storage.user.get("user_type") != "guest":
        authz.append('accept')

    for key, page in pages.items():
        if key in authz:
            path = f"/{tenant}/{page['path']}"
            ui.link(page['label'], path).classes(f"main-menu {key}").classes("selected" if navtitle == key else "")


def _apply_theme(page_name: str, tenant: str) -> dict:
    """Apply CSS, colors, and page title. Returns theme config."""
    ui.add_css('static/css/base.css')

    # Get tenant-specific theme configuration
    tenant_config = get_tenant_config(tenant)
    theme = tenant_config.get('theme', {})
    # logger.debug(f'theme found: {theme}')

    # Set Quasar colors (using theme values or defaults)
    # This is the single source of truth for colors
    ui.colors(
        primary=theme.get('primary_color', 'rgb(59, 130, 246)'),
        secondary=theme.get('secondary_color', '#26a69a'),
        accent=theme.get('accent_color', '#9c27b0'),
        positive=theme.get('positive_color', '#21ba45')
    )

    label = pages.get(page_name, {}).get('label', page_name.title())
    ui.page_title(f"eduPersona - {label}")

    return theme

def _user_link(tenant: str):
    username = app.storage.user.get("username", "gast")
    is_guest = app.storage.user.get("user_type") == "guest"

    # User info with dropdown menu
    with ui.label(username).classes("username"):
        ui.icon("person", color="background")

        with ui.menu().props(remove="no-parent-event"):
            if app.storage.user.get("authenticated", False) and not is_guest:
                ui.menu_item("uitloggen", lambda: ui.navigate.to(f"/{tenant}/m/logout"))
            else:
                login_path = f"/{tenant}/m/login"
                ui.menu_item("inloggen", lambda: ui.navigate.to(login_path))


@contextmanager
def frame(page_name: str, tenant: str):
    """
    Provides consistent page structure with navigation, styling, and layout.

    Args:
        page_name: Name of the page (e.g., 'groups', 'invitations', 'login')
        tenant: Tenant identifier for loading tenant-specific configuration

    Usage:
        @ui.page('/{tenant}/m/groups')
        async def groups_page(tenant: str = Depends(...)):
            with frame('groups', tenant):
                # Your page content here
    """

    _apply_theme(page_name, tenant)
    rdm_init()

    # Create header with navigation
    with ui.header():

        with ui.element('div').classes("header-div"):
            with ui.link("", target="/").style('height:60px;'):
                ui.element('div').classes('appname-logo')

            # Navigation menu (only show if user is authenticated)
            if app.storage.user.get("authenticated", False):
                main_menu(page_name, tenant)

            if page_name not in ['login', 'accept'] and app.storage.user.get("user_type") != "guest":
                _user_link(tenant)

    # Main content area
    with Col(classes=f"{page_name}-page page-content"):
        # logger.debug(f"User {username} navigated to {page_name} (tenant: {tenant})")
        yield


# @contextmanager
# def accept_frame(tenant: str):
#     """
#     Provides consistent page structure for /accept page with navigation header
#     but no interactive elements (no username dropdown, no clickable nav items).

#     Args:
#         tenant: Tenant identifier for loading tenant-specific configuration

#     Usage:
#         @ui.page('/{tenant}/accept')
#         async def accept_page(tenant: str):
#             with accept_frame(tenant):
#                 # Your page content here
#     """

#     _apply_theme('accept', tenant)

#     # Create header with navigation (read-only)
#     with ui.header():
#         with ui.element('div').classes("header-div"):
#             ui.element('div').classes('appname-logo')

#             # # Display "accept invitation" as dummy active nav element
#             # ui.label('accept invitation').classes("main-menu selected")

#             _user_link(tenant)

#     # Main content area
#     with Col(classes="accept-page page-content"):
#         # logger.debug(f"Accept page accessed (tenant: {tenant})")
#         yield
