from ng_rdm.components import Col, Icon, Row, rdm_init, set_language
from ng_rdm.utils import logger
from nicegui import ui

from services.tenant import get_default_tenant

GITHUB_URL = 'https://github.com/edupersona/eduPersona'


@ui.page('/')
def landing_page():
    """Landing page - tenant-agnostic entry point.

    The end-user route (/accept) is tenant-less; tenant is derived from the
    invitation code or session. The admin link uses the derived default tenant
    for `/m/{tenant}/invitations`. Copy is Dutch-only (this PoC's audience).
    """
    logger.debug("Landing page accessed")
    rdm_init()
    set_language('nl_nl')

    ui.add_css('static/css/base.css')
    ui.page_title('eduPersona')

    default_tenant = get_default_tenant()

    with Col(classes='landing-page'):
        with Col(classes='landing-layout page-content'):
            with ui.link(target=GITHUB_URL, new_tab=True).classes('github-link'):
                Icon('github')

            # Hero: logo + tagline + one-line intro
            with Col(classes='landing-hero'):
                ui.image('/static/img/edupersona.png').classes('landing-logo')
                ui.label('De brug tussen eduID en instellingsidentiteit').classes('landing-tagline')

            # Primary call-to-action
            with Row().classes('landing-cards'):
                with ui.card().classes('card-clickable') as accept_card:
                    with Col(classes='card-content'):
                        Icon('envelope').classes('icon-success')
                        ui.label('Accepteer een uitnodiging').classes('card-title')
                        ui.label('Klik hier als je een uitnodiging hebt ontvangen').classes('text')

            # What is eduPersona?
            with Col(classes='landing-section'):
                ui.label('Wat is eduPersona?').classes('section-heading')
                ui.html(
                    'Een self-service pagina die de eduID van verschillende soorten gastgebruikers betrouwbaar '
                    'koppelt aan een instellingsidentiteit. '
                    'Je kunt het zien als een <i>flexibele verificatiefabriek</i>.'
                ).classes('text')

            # How does it work? — overview graphic links through to the README
            with Col(classes='landing-section'):
                ui.label('Hoe werkt het?').classes('section-heading')
                ui.label(
                    'Voor elk type gast — de persona — configureer je een stappenplan dat de gast moet doorlopen. '
                    'Bij het accepteren van de uitnodiging wordt de gast stap voor stap begeleid, tot aan alle onboarding-eisen is voldaan. Bij afronding '
                    'koppelt eduPersona de geverifieerde gastgegevens terug naar het IAM- of integratiesysteem van de instelling. '
                ).classes('text')

                with ui.link(target=GITHUB_URL, new_tab=True):
                    ui.image('/static/img/edupersona_overview.png').classes('landing-diagram')

            # Footer: secondary links
            with Row().classes('landing-footer'):
                ui.link('Contact', '/contact')
                ui.link('Broncode en documentatie', GITHUB_URL, new_tab=True)
                ui.link('Toegang als beheerder', f'/m/{default_tenant}/invitations')

        accept_card.on('click', lambda: ui.navigate.to('/accept'))
