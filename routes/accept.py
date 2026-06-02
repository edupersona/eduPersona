# /accept route: self-service page showing onboarding progress

from nicegui import ui

from domain.step_cards import Steps, StepResult
from services.session_manager import initialize_state
from services.settings import get_scenario_config
from domain.invitations import find_invitation_by_code, apply_invite_code_to_state
from services.tenant import get_default_tenant, store_tenant_in_session
from services.theme import frame
from services.i18n import _


@ui.page('/accept')
@ui.page('/accept/{invite_code}')
async def accept_invitation(invite_code: str = ""):
    """Guest invitation entry. Tenant is resolved from the invitation code;
    bare /accept renders with the default-tenant theme until a code is entered."""
    tenant = get_default_tenant()
    if invite_code:
        match = await find_invitation_by_code(invite_code.strip())
        if match:
            tenant = match[0]

    with frame('accept', tenant):
        await ui.context.client.connected()

        state = initialize_state()
        scenario_config = get_scenario_config(tenant)

        steps = Steps(tenant, state, scenario_config)

        if invite_code:
            applied = await apply_invite_code_to_state(tenant, state, invite_code)
            if applied:
                store_tenant_in_session(tenant)
                if steps.step_instances:
                    await steps.record(steps.step_instances[0].step_id, StepResult('completed'))
            else:
                ui.notify(_('Invalid invite code'), type='negative')

        await steps.startup()
        steps.render()  # type: ignore
