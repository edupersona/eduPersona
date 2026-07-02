# /accept route: self-service onboarding page.

from ng_rdm.components import Button, Col
from nicegui import ui

from domain.invitations import (
    apply_invite_to_state,
    expire_overdue_invitations,
    find_invitation_tenant,
)
from domain.models import Invitation
from services.i18n import _
from services.persona_loader import get_persona_config
from services.session_manager import clear_session_state, session_state
from services.tenant import get_default_tenant, store_tenant_in_session
from services.theme import frame
from services.ui_errors import ui_guard
from steps import Steps, render_welcome


def _code_entry_form(typed: dict, on_submit) -> None:
    """Code-entry gate for bare /accept or an unknown code.

    Resolving the code resolves the tenant + persona, so code-entry is a gate that
    runs before any step list exists — never a step card. The input binds to `typed`;
    submitting re-renders the page in place (no navigation), and validation happens
    once, in the page's `render` refreshable."""
    with Col(classes='accept-form'):
        ui.label(_('Accept invitation')).classes('page-title')
        ui.input(
            _('Enter your invitation code here'),
            placeholder=_('Invitation code'),
        ).classes('form-input').bind_value(typed, 'code')
        Button(_('Confirm code'), on_click=on_submit)


def _terminal_error(title: str, subtitle: str) -> None:
    """Terminal red-icon screen for an invitation that can't be onboarded
    (expired, or unprocessable due to bad persona/step config)."""
    with Col(classes='accept-terminal'):
        ui.icon('error_outline', size='3em').classes('icon-error')
        ui.label(title).classes('page-title')
        ui.label(subtitle).classes('page-subtitle')


@ui.page('/accept')
@ui.page('/accept/{invite_code}')
async def accept_invitation_page(invite_code: str = ""):
    """Guest invitation entry. Tenant resolves from the invitation code; bare /accept
    (or an unknown code) shows the code-entry gate and re-renders in place on submit."""
    typed = {'code': invite_code.strip()}

    # Frame branding is fixed at load; resolve tenant from the URL code so the common
    # email-link path (/accept/{code}) is branded correctly.
    tenant = get_default_tenant()
    if typed['code']:
        resolved = await find_invitation_tenant(typed['code'])
        if resolved:
            tenant = resolved

    with frame('accept', tenant):
        await ui.context.client.connected()

        @ui.refreshable
        async def render() -> None:
            code = typed['code'].strip()
            t = (await find_invitation_tenant(code) if code else None) or tenant
            if code:
                await expire_overdue_invitations(t)  # claim-time sweep — flips overdue → expired first
            inv = await Invitation.get_or_none(tenant=t, code=code) if code else None
            if inv is None:
                if code:  # supplied but unresolved — notify and let them retry
                    ui.notify(_('Invalid invite code'), type='negative')
                _code_entry_form(typed, render.refresh)
                return

            if inv.status in ('accepted', 'expired'):  # terminal — renders from the DB invitation,
                clear_session_state(code)               # so its scratch state is now dead weight
                if inv.status == 'accepted':  # returning user — same welcome as in-session completion
                    render_welcome(t, inv.persona_key, inv.given_name)
                else:  # expired — nothing to onboard; dead-end, not a fresh flow
                    _terminal_error(_('This invitation has expired.'),
                                    _('Please contact the sender of your invitation.'))
                return

            # Session state lives in app.storage.user (survives the OIDC redirect),
            # namespaced by invite code; resolved now that the code is valid. Apply the
            # invitation BEFORE building Steps: on a first visit apply_invite_to_state resets
            # step_state, and Steps captures each card's state slot at construction — building
            # it first would leave the cards pointing at orphaned slots, so writes via record()
            # (outputs, match_failures) would be invisible to the cards.
            state = session_state(code)
            if await apply_invite_to_state(t, state, code):
                store_tenant_in_session(t)

            steps = None
            with ui_guard(notify=False):  # default catch=ValueError (unknown persona / bad step config)
                cfg = get_persona_config(t, inv.persona_key)
                steps = Steps(t, state, {"steps": cfg.steps})
            if steps is None:
                _terminal_error(_('This invitation cannot be processed right now.'),
                                _('Please contact the sender of your invitation.'))
                return

            await steps.startup()
            steps.render()  # type: ignore

        await render()
