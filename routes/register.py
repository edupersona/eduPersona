"""Public PoC-access registration page."""

from nicegui import ui

from ng_rdm.components import Button, Col
from ng_rdm.utils import logger
from services.i18n import _
from services.postmark.postmark import send_postmark_email
from services.tenant import get_default_tenant
from services.theme import frame

POC_NOTIFY_TO = "peter.kleynjan@quantis.nl"
POC_FROM_EMAIL = "info@edupersona.nl"
POC_FROM_NAME = "eduPersona PoC"


@ui.page('/register')
async def register_page() -> None:
    """Public form for prospective users to request PoC access."""
    tenant = get_default_tenant()
    state = {"first_name": "", "last_name": "", "organisation": "", "email": "", "sent": False}

    with frame('register', tenant):
        with Col(classes='centered-content'):
            ui.label(_('Register for PoC access')).classes('section-heading')

            async def submit() -> None:
                if not all(state[k].strip() for k in ('first_name', 'last_name', 'organisation', 'email')) \
                        or '@' not in state['email']:
                    ui.notify(_('Please fill in all fields with a valid email'), type='negative')
                    return

                body = (
                    f"New PoC access request:\n\n"
                    f"Name: {state['first_name']} {state['last_name']}\n"
                    f"Organisation: {state['organisation']}\n"
                    f"Email: {state['email']}\n"
                )
                ok = await send_postmark_email({
                    "from_email": POC_FROM_EMAIL,
                    "from_name": POC_FROM_NAME,
                    "to_email": POC_NOTIFY_TO,
                    "subject": f"PoC access request: {state['first_name']} {state['last_name']} ({state['organisation']})",
                    "html_body": f"<pre>{body}</pre>",
                    "text_body": body,
                })
                if ok:
                    logger.info(f"PoC registration sent for {state['email']}")
                    state['sent'] = True
                    card.refresh()
                else:
                    ui.notify(_('Could not send your request — please try again later'), type='negative')

            @ui.refreshable
            def card() -> None:
                if state['sent']:
                    with ui.card().tight().classes('register-card'):
                        ui.label(_('Thank you!')).classes('section-heading')
                        ui.label(_(
                            "We've received your details and will be in touch shortly with your PoC test login."
                        )).classes('text')
                    return

                with ui.card().tight().classes('register-card'):
                    ui.label(_(
                        'Leave your details if you want to try out eduPersona.nl '
                        'for yourself. We will send you a test login for this PoC environment.'
                    )).classes('text register-intro')
                    ui.input(_('First name')).bind_value(state, 'first_name').classes('form-input')
                    ui.input(_('Last name')).bind_value(state, 'last_name').classes('form-input')
                    ui.input(_('Organisation')).bind_value(state, 'organisation').classes('form-input')
                    ui.input(_('Email address')).props('type=email') \
                        .bind_value(state, 'email').classes('form-input-last')
                    Button(_('Send'), on_click=submit)

            card()
