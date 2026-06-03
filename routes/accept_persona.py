# /accept/p route: persona-mode self-service onboarding page.

from nicegui import ui

from domain.invitations_persona import (
    apply_persona_invite_to_state,
    find_persona_invitation_tenant,
)
from domain.models import Invitation
from domain.step_cards import PersonaSteps, StepResult
from services.i18n import _
from services.persona_loader import get_persona_config
from services.session_manager import initialize_state
from services.tenant import get_default_tenant, store_tenant_in_session
from services.theme import frame


def _code_entry_form() -> None:
    """Spartan code-entry form for bare /accept/p or an invalid code (§5.3)."""
    ui.label(_('Accept invitation')).classes('page-title')
    code_input = ui.input(
        _('Enter your invitation code here'),
        placeholder=_('Invitation code'),
    ).classes('form-input')
    ui.button(
        _('Confirm code'),
        on_click=lambda: ui.navigate.to(f"/accept/p/{(code_input.value or '').strip()}"),
    ).style('margin-top: 0.5rem;')


@ui.page('/accept/p')
@ui.page('/accept/p/{invite_code}')
async def accept_persona_page(invite_code: str = ""):
    """Persona-mode invitation entry. Tenant resolves from the invitation code;
    bare /accept/p (or an invalid code) shows a code-entry form."""
    code = invite_code.strip()
    tenant = get_default_tenant()
    if code:
        resolved = await find_persona_invitation_tenant(code)
        if resolved:
            tenant = resolved

    with frame('accept', tenant):
        await ui.context.client.connected()

        inv = await Invitation.get_or_none(tenant=tenant, code=code, persona_key__isnull=False) if code else None
        if inv is None:
            _code_entry_form()
            return

        state = initialize_state()
        cfg = get_persona_config(tenant, inv.persona_key or "")
        steps = PersonaSteps(tenant, state, {"steps": cfg.steps})

        applied = await apply_persona_invite_to_state(tenant, state, code)
        if applied:
            store_tenant_in_session(tenant)
            if steps.step_instances:
                await steps.record(steps.step_instances[0].step_id, StepResult('completed'))

        await steps.startup()
        steps.render()  # type: ignore
