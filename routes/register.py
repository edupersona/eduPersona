"""Public PoC-access registration page.

Submitting creates and sends an invitation for the self-service `admin` persona, so a
prospect onboards with their test eduID and is provisioned as a tenant admin on
completion (see services/admin_onboarding.py). Tenant-agnostic top-level route; the
single configured tenant is resolved via get_default_tenant.
"""

from ng_rdm.components import Button, Col
from ng_rdm.utils import logger
from nicegui import ui

from domain.invitations import create_invitation
from services.i18n import _
from services.postmark.postmark import send_invitation_mail, send_register_notification
from services.tenant import get_default_tenant
from services.theme import frame
from services.ui_errors import ui_guard

ADMIN_PERSONA = "admin"


@ui.page('/register')
async def register_page() -> None:
    """Public form for prospective users to request PoC access."""
    tenant = get_default_tenant()
    state = {"first_name": "", "last_name": "", "email": "", "keep_informed": True, "sent": False}

    with frame('register', tenant):
        with Col(classes='centered-content'):
            ui.label(_('Register for PoC access')).classes('section-heading')

            async def submit() -> None:
                if not all(state[k].strip() for k in ('first_name', 'last_name', 'email')) \
                        or '@' not in state['email']:
                    ui.notify(_('Please fill in all fields with a valid email'), type='negative')
                    return

                email = state['email'].strip()
                name = f"{state['first_name'].strip()} {state['last_name'].strip()}"
                with ui_guard(_('Could not start your registration — please try again later')):
                    inv = await create_invitation(
                        tenant, ADMIN_PERSONA, email, guest_id=email,
                        given_name=state['first_name'].strip(),
                        family_name=state['last_name'].strip(),
                    )
                    if not await send_register_notification(name, email, state['keep_informed']):
                        logger.warning(f"register notification mail failed for {email}")
                    if await send_invitation_mail(tenant, inv):
                        logger.info(f"PoC admin invite created+sent for {email} (newsletter={state['keep_informed']})")
                        state['sent'] = True
                        card.refresh()
                    else:
                        ui.notify(_('Could not send your invitation — please try again later'), type='negative')

            @ui.refreshable
            def card() -> None:
                if state['sent']:
                    with ui.card().tight().classes('register-card'):
                        ui.label(_('Thank you!')).classes('section-heading')
                        ui.label(_(
                            "We've sent you an invitation by e-mail. Open the link to onboard "
                            "with your eduID and get access to this PoC environment."
                        )).classes('text')
                    return

                with ui.card().tight().classes('register-card'):
                    ui.label('Wil je eduPersona.nl zelf proberen? Vul je gegevens in, dan mailen we je (via eduPersona, uiteraard) een uitnodiging om je aan te melden met je eduID.',

                             ).classes('text register-intro')
                    ui.input(_('First name')).bind_value(state, 'first_name').classes('form-input')
                    ui.input(_('Last name')).bind_value(state, 'last_name').classes('form-input')
                    ui.input(_('Email address')).props('type=email') \
                        .bind_value(state, 'email').classes('form-input')
                    ui.checkbox('stuur mij de eduPersona nieuwsbrief (max. eenmaal per maand)') \
                        .bind_value(state, 'keep_informed').classes('form-input-last')
                    Button(_('Send'), on_click=submit)

            card()
