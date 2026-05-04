from nicegui import ui, html

from ng_rdm.components import Col, Row, Icon, rdm_init, set_language
from ng_rdm.utils import logger
from services.i18n import _
from services.tenant import get_default_tenant, validate_tenant


def _render_landing(tenant: str) -> None:
    """Render the landing page with cards and admin link bound to `tenant`."""
    rdm_init()
    set_language('nl_nl')

    ui.add_css('static/css/base.css')
    ui.page_title('eduPersona')

    # Main container
    with Col(classes='landing-page'):
        # Layout: logo + cards (responsive via CSS)
        with ui.row().classes('landing-layout'):
            # Logo
            ui.image('/static/img/edupersona.png').classes('landing-logo')

            # Cards container
            with Row().classes('landing-cards'):
                with ui.card().classes('card-clickable') as accept_card:
                    with Col(classes='card-content'):
                        Icon('envelope').classes('icon-success')
                        ui.label(_('Accept an invitation')).classes('card-title')
                        ui.label(_("Click here if you've received an invitation")).classes('text')

                with ui.card().classes('card-clickable') as apps_card:
                    with Col(classes='card-content'):
                        Icon('mortarboard').classes('icon-primary')
                        ui.label(_('Access your apps')).classes('card-title')
                        ui.label(_("Note: you will need an eduID for this")).classes('text')

            with Row().classes('admin-link'):
                ui.link(_('Admin access'), f'/{tenant}/m/guests')
                # with ui.card().classes('card-clickable') as beheer_card:
                #     with Col(classes='card-content'):
                #         ui.icon('admin_panel_settings', size='3em').classes('icon-primary')
                #         ui.label(_('Management')).classes('card-title')
                #         ui.label(_('Manage roles and invitations')).classes('text-muted')

        # Make entire cards clickable
        accept_card.on('click', lambda: ui.navigate.to(f'/{tenant}/accept'))
        apps_card.on('click', lambda: ui.navigate.to(f'/{tenant}/apps?relogin=1'))


@ui.page('/')
def landing_page():
    """Landing page - tenant-agnostic entry point (uses derived default tenant)."""
    logger.debug("Landing page accessed")
    _render_landing(get_default_tenant())


@ui.page('/{tenant}')
def tenant_landing_page(tenant: str):
    """Landing page bound to an explicit tenant — `/hvh` etc."""
    validate_tenant(tenant)
    logger.debug(f"Tenant landing page accessed: {tenant}")
    _render_landing(tenant)
