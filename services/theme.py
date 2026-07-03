from contextlib import contextmanager

from collections.abc import Iterator

from ng_rdm.components import Col, IconButton, rdm_init, set_language
from nicegui import app, ui

from services.settings import get_tenant_config

pages = {
    # possible menu entries, depending on authz.
    # `tenanted=True` → URL becomes /m/{tenant}/<path>; otherwise <path> is used as-is.
    'invitations': {'path': 'invitations', 'label': 'uitnodigingen', 'tenanted': True},
    'simulator': {'path': 'simulator', 'label': 'simulator', 'tenanted': True},
    'accept': {'path': '/accept', 'label': 'accepteren', 'tenanted': False},
    'login': {'path': 'login', 'label': 'inloggen', 'tenanted': True},
    'register': {'path': '/register', 'label': 'aanmelden', 'tenanted': False},
    'contact': {'path': '/contact', 'label': 'contact', 'tenanted': False},
    'home': {'path': '/', 'label': 'home', 'tenanted': False},
}

def _nav_entries(tenant: str) -> Iterator[tuple[str, str, str]]:
    """Yield (key, label, path) for each nav page the current user may see."""
    authz = app.storage.user.get("authz", [])
    if app.storage.user.get("user_type") != "guest":
        authz = [*authz, 'accept']

    for key, page in pages.items():
        if key in authz:
            path = f"/m/{tenant}/{page['path']}" if page['tenanted'] else page['path']
            yield key, page['label'], path


@ui.refreshable
def main_menu(navtitle: str, tenant: str) -> None:
    """Create main navigation menu with authorization checking."""
    for key, label, path in _nav_entries(tenant):
        ui.link(label, path).classes(f"main-menu {key}").classes("selected" if navtitle == key else "")


_FAVICON_HEAD = (
    '<link rel="icon" href="/static/img/favicons/favicon.ico" sizes="any">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/static/img/favicons/favicon-32x32.png">'
    '<link rel="icon" type="image/png" sizes="16x16" href="/static/img/favicons/favicon-16x16.png">'
    '<link rel="apple-touch-icon" sizes="180x180" href="/static/img/favicons/apple-touch-icon.png">'
    '<link rel="manifest" href="/static/img/favicons/site.webmanifest">'
)


def _apply_theme(page_name: str, tenant: str) -> dict:
    """Apply CSS, colors, and page title. Returns theme config."""
    ui.add_css('static/css/base.css')
    ui.add_head_html(_FAVICON_HEAD)

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

def _auth_menu_item(tenant: str) -> None:
    """The login/logout menu entry, shared by the user dropdown and the hamburger."""
    is_guest = app.storage.user.get("user_type") == "guest"
    if app.storage.user.get("authenticated", False) and not is_guest:
        ui.menu_item("uitloggen", lambda: ui.navigate.to(f"/m/{tenant}/logout"))
    else:
        ui.menu_item("inloggen", lambda: ui.navigate.to(f"/m/{tenant}/login"))


def _user_link(tenant: str):
    display_name = app.storage.user.get("display_name") or app.storage.user.get("username", "gast")

    # User info with dropdown menu
    with ui.label(display_name).classes("username"):
        ui.icon("person", color="background")
        with ui.menu().props(remove="no-parent-event"):
            _auth_menu_item(tenant)


def _hamburger_menu(tenant: str, authenticated: bool, show_user: bool) -> None:
    """Mobile-only nav: a hamburger button anchoring a dropdown of the same
    entries as the desktop nav + the login/logout item (CSS-hidden on desktop)."""
    with IconButton('list', tooltip='menu').classes('header-hamburger'):
        with ui.menu().props(remove="no-parent-event"):
            if authenticated:
                for _key, label, path in _nav_entries(tenant):
                    # default-arg captures the loop value; NiceGUI calls it with no args
                    ui.menu_item(label, lambda p=path: ui.navigate.to(p))  # type: ignore
            if show_user:
                _auth_menu_item(tenant)


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

    # rdm_init() first so ng_rdm.css is injected before base.css — app CSS then wins
    # ties (both are inlined into the head in call order). It also lets _apply_theme's
    # tenant `ui.colors(...)` run last, so a tenant's primary colour isn't clobbered by
    # rdm_init's own `ui.colors(primary=...)`.
    rdm_init()
    _apply_theme(page_name, tenant)
    set_language('nl_nl')

    # Create header with navigation
    with ui.header():

        with ui.element('div').classes("header-div"):
            with ui.link("", target="/").style('height:60px;'):
                ui.element('div').classes('appname-logo')

            authenticated = app.storage.user.get("authenticated", False)
            show_user = page_name not in ['login', 'accept'] and app.storage.user.get("user_type") != "guest"

            # Desktop nav — `display:contents` so links + user dropdown lay out
            # directly in .header-div; the wrapper only exists to hide them on mobile.
            with ui.element('div').classes('header-nav-desktop'):
                if authenticated:
                    main_menu(page_name, tenant)
                if show_user:
                    _user_link(tenant)

            # Mobile-only collapsed nav
            if authenticated or show_user:
                _hamburger_menu(tenant, authenticated, show_user)

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
