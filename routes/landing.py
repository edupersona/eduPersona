from nicegui import ui

from ng_rdm.components import Col, Row
from ng_rdm.utils import logger
from services.i18n import _
from services.tenant import get_available_tenants, get_default_tenant


@ui.page('/')
def landing_page():
    """Landing page - tenant-agnostic entry point."""
    logger.debug("Landing page accessed")

    ui.add_css('static/css/base.css')
    ui.page_title('eduPersona')

    default_tenant = get_default_tenant()

    # Main container
    with Col(classes='landing-page'):
        # Layout: logo + cards (responsive via CSS)
        with ui.row().classes('landing-layout'):
            # Logo
            ui.image('/static/img/edupersona.png').classes('landing-logo')

            # Cards container
            with ui.row().classes('landing-cards'):
                # Accept invitation card
                with ui.card().classes('card-clickable') as accept_card:
                    with Col(classes='card-content'):
                        ui.icon('mail_outline', size='3em').classes('icon-success')
                        ui.label(_('Accept invitation')).classes('card-title')
                        ui.label(_('Accept a received invitation')).classes('text-muted')

                # Management card
                with ui.card().classes('card-clickable') as beheer_card:
                    with Col(classes='card-content'):
                        ui.icon('admin_panel_settings', size='3em').classes('icon-primary')
                        ui.label(_('Management')).classes('card-title')
                        ui.label(_('Manage roles and invitations')).classes('text-muted')

        # Make entire cards clickable - redirect to default tenant
        accept_card.on('click', lambda: ui.navigate.to(f'/{default_tenant}/accept'))
        beheer_card.on('click', lambda: ui.navigate.to(f'/{default_tenant}/m/invitations'))
