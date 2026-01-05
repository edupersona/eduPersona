# /accept route: self-service page showing onboarding progress

from nicegui import app, ui

from components.step_cards import Steps
from services.settings import get_tenant_config
from services.logging import logger
from services.session_manager import initialize_state
from services.storage import find


def process_invite_code(state: dict, invite_code: str):
    """Check invite code; if valid, add invite code & group details to session state"""
    membership_details = find("memberships", with_relations=["guest", "group"], membership_id=invite_code.strip())
    if membership_details:
        membership_with_details = membership_details[0]
        group = membership_with_details["group"]

        if group:
            # Update state with all relevant data
            state['invite_code'] = invite_code      # needed for marking accepted
            state['group_name'] = group['name']
            state['redirect_url'] = group.get('redirect_url', '')
            state['redirect_text'] = group.get('redirect_text', '')
            state['steps_completed']['code_matched'] = True
        else:
            logger.error(f"Group not found for membership_id: {invite_code}")
            ui.notify('Ongeldige uitnodigingscode (groep niet gevonden)', type='negative')
    else:
        logger.warning(f"Invalid invite_code attempted: {invite_code}")
        ui.notify('Ongeldige uitnodigingscode', type='negative')


@ui.page('/accept')
@ui.page('/accept/{invite_code}')
async def accept_invitation(invite_code: str = ""):
    # Ensure client connection for tab storage
    await ui.context.client.connected()

    state = initialize_state()
    logger.debug(f"Accept page, current tab state: {dict(state)}")

    # Update state from invite_code parameter using consolidated logic
    if invite_code:
        process_invite_code(state, invite_code)

    suffix = f"{state['group_name']}" if state['group_name'] else ""
    title = f"Uitnodiging - {suffix}" if suffix else "Uitnodiging"
    ui.page_title(title)

    with ui.column().classes('max-w-4xl mx-auto p-6').style('width: 800px;'):
        ui.label(f"Welkom als {suffix}" if suffix else "Welkom").classes('text-3xl font-bold mb-2')
        ui.label('Volg het stappenplan hieronder om uw uitnodiging te accepteren.').classes('text-lg mb-6')

        # Get tenant config (for now hardcoded to 'uva')
        tenant = 'uva'
        tc = get_tenant_config(tenant)

        # Create and render steps
        steps = Steps(state, tc)
        steps.render()  # type: ignore
