from nicegui import ui, html

from ng_rdm.components import Col, Row, Icon, rdm_init
from ng_rdm.utils import logger
from services.i18n import _
from services.tenant import get_default_tenant


@ui.page('/')
def landing_page():
    """Landing page - tenant-agnostic entry point."""
    logger.debug("Landing page accessed")
    rdm_init()

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
            with Row().classes('landing-cards'):
                with ui.card().classes('card-clickable') as accept_card:
                    with Col(classes='card-content'):
                        Icon('envelope').classes('icon-success')
                        ui.label(_('Accept an invitation')).classes('card-title')
                        ui.label(_("Click here if you've received an invitation")).classes('text-muted')

                with ui.card().classes('card-clickable') as apps_card:
                    with Col(classes='card-content'):
                        Icon('mortarboard').classes('icon-primary')
                        ui.label(_('Access your apps')).classes('card-title')
                        ui.label(_("Note: you will need an eduID for this")).classes('text-muted')

            with Row().classes('admin-link'):
                ui.link(_('Admin login'), f'/{default_tenant}/m/invitations')
                # with ui.card().classes('card-clickable') as beheer_card:
                #     with Col(classes='card-content'):
                #         ui.icon('admin_panel_settings', size='3em').classes('icon-primary')
                #         ui.label(_('Management')).classes('card-title')
                #         ui.label(_('Manage roles and invitations')).classes('text-muted')

        # Make entire cards clickable - redirect to default tenant
        accept_card.on('click', lambda: ui.navigate.to(f'/{default_tenant}/accept'))
        apps_card.on('click', lambda: ui.navigate.to(f'/{default_tenant}/apps'))
