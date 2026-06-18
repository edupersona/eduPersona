"""Public contact / feedback page.

Tenant-agnostic top-level route; submissions are e-mailed to the eduPersona team
(see services/postmark/postmark.py:send_contact_mail). Dutch-only copy.
"""

from ng_rdm.components import Button, Col
from ng_rdm.utils import logger
from nicegui import ui

from services.postmark.postmark import send_contact_mail
from services.tenant import get_default_tenant
from services.theme import frame
from services.ui_errors import ui_guard


@ui.page('/contact')
async def contact_page() -> None:
    """Public contact form; the result is e-mailed to the team."""
    tenant = get_default_tenant()
    state = {"first_name": "", "last_name": "", "email": "", "message": "",
             "keep_informed": True, "sent": False}

    with frame('contact', tenant):
        with Col(classes='centered-content'):
            ui.label('Contact').classes('section-heading')

            async def submit() -> None:
                if not all(state[k].strip() for k in ('first_name', 'last_name', 'email', 'message')) \
                        or '@' not in state['email']:
                    ui.notify('Vul alle velden in met een geldig e-mailadres', type='negative')
                    return

                name = f"{state['first_name'].strip()} {state['last_name'].strip()}"
                with ui_guard('Je bericht kon niet worden verstuurd — probeer het later opnieuw'):
                    if await send_contact_mail(name, state['email'].strip(),
                                               state['message'].strip(), state['keep_informed']):
                        logger.info(f"Contact message sent from {state['email'].strip()}")
                        state['sent'] = True
                        card.refresh()
                    else:
                        ui.notify('Je bericht kon niet worden verstuurd — probeer het later opnieuw',
                                  type='negative')

            @ui.refreshable
            def card() -> None:
                if state['sent']:
                    with ui.card().tight().classes('contact-card'):
                        ui.label('Bedankt!').classes('section-heading')
                        ui.label('We hebben je bericht ontvangen en nemen zo nodig contact met je op.') \
                            .classes('text')
                    return

                with ui.card().tight().classes('contact-card'):
                    ui.label('Vragen of feedback over eduPersona? Laat hier een bericht achter.') \
                        .classes('text contact-intro')
                    ui.input('Voornaam').bind_value(state, 'first_name').classes('form-input')
                    ui.input('Achternaam').bind_value(state, 'last_name').classes('form-input')
                    ui.input('E-mailadres').props('type=email').bind_value(state, 'email').classes('form-input')
                    ui.textarea('Bericht').props('outlined autogrow') \
                        .bind_value(state, 'message').classes('form-input')
                    ui.checkbox('stuur mij de eduPersona nieuwsbrief (max. eenmaal per maand)').bind_value(state, 'keep_informed') \
                        .classes('form-input-last')
                    Button('Versturen', on_click=submit)

            card()
