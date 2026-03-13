# /accept route: self-service page showing onboarding progress

from nicegui import app, ui

from components.step_cards import Steps
from ng_loba.utils import logger
from services.i18n import _
from services.session_manager import initialize_state
from services.settings import get_tenant_config
from services.storage.storage import get_invitation_with_roles
from services.tenant import store_tenant_in_session, validate_tenant
from services.theme import accept_frame


async def process_invite_code(tenant: str, state: dict, invite_code: str):
    """Check invite code; if valid, add invitation & role details to session state"""
    invitation = await get_invitation_with_roles(tenant, invite_code.strip())

    if invitation:
        role_assignments = invitation.get("role_assignments", [])
        if not role_assignments:
            logger.error(f"No role assignments for invitation code: {invite_code}")
            ui.notify(_('Invalid invite code (no roles assigned)'), type='negative')
            return

        # Build role display info from linked role assignments
        role_names = [ra.get("role", {}).get("name", "") for ra in role_assignments if ra.get("role")]

        # Update state with invitation data
        state['invite_code'] = invite_code
        state['invitation_id'] = invitation['id']
        state['role_assignments'] = role_assignments
        state['role_name'] = ", ".join(role_names) if role_names else ""
        state['steps_completed']['code_matched'] = True
        store_tenant_in_session(tenant)
    else:
        logger.warning(f"Invalid invite_code attempted: {invite_code}")
        ui.notify(_('Invalid invite code'), type='negative')


@ui.page('/{tenant}/accept')
@ui.page('/{tenant}/accept/{invite_code}')
async def accept_invitation(tenant: str, invite_code: str = ""):
    validate_tenant(tenant)

    with accept_frame(tenant):
        # Ensure client connection for tab storage
        await ui.context.client.connected()

        state = initialize_state()
        tc = get_tenant_config(tenant)

        if invite_code:
            await process_invite_code(tenant, state, invite_code)

        # create and render steps
        steps = Steps(tenant, state, tc)
        steps.render()  # type: ignore
