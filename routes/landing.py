from ng_rdm.components import Col, Icon, Row, rdm_init, set_language
from ng_rdm.utils import logger
from nicegui import ui

from services.i18n import _
from services.tenant import get_default_tenant


@ui.page('/')
def landing_page():
    """Landing page - tenant-agnostic entry point.

    The end-user route (/accept) is tenant-less; tenant is derived from the
    invitation code or session. The admin link uses the derived default tenant
    for `/m/{tenant}/invitations`.
    """
    logger.debug("Landing page accessed")
    rdm_init()
    set_language('nl_nl')

    ui.add_css('static/css/base.css')
    ui.page_title('eduPersona')

    default_tenant = get_default_tenant()

    # Main container
    with Col(classes='landing-page'):
        # Layout: logo + cards (responsive via CSS)
        with ui.row().classes('landing-layout'):
            with ui.link(target='https://github.com/edupersona/eduPersona', new_tab=True).classes('github-link'):
                Icon('github')

            # Logo
            ui.image('/static/img/edupersona.png').classes('landing-logo')

            ui.label(_('Bridging eduID and institution identity')).classes('landing-tagline')

            # Cards container
            with Row().classes('landing-cards'):
                with ui.card().classes('card-clickable') as accept_card:
                    with Col(classes='card-content'):
                        Icon('envelope').classes('icon-success')
                        ui.label(_('Accept an invitation')).classes('card-title')
                        ui.label(_("Click here if you've received an invitation")).classes('text')

            with Row().classes('admin-link'):
                ui.link(_('Admin access'), f'/m/{default_tenant}/invitations')

        # Make entire card clickable
        accept_card.on('click', lambda: ui.navigate.to('/accept'))
