"""Step card components for the onboarding flow (persona-mode).

See cline_docs/step_cards.md for the full contract — lifecycle, StepResult,
the MAY / MAY NOT rules, and the single-session invariant.

Shape B (§2.7): OIDC steps write verified userinfo to state['outputs'][idp] (keyed
by IdP name, gotcha 10); non-OIDC steps write to state['outputs'][step_id].
Finalization is a built-in orchestrator side effect (Steps._finalize): once every
step is completed/skipped it persists state['outputs'] to Invitation.step_outputs and
accepts (firing the webhook). Completion then renders a persona welcome screen
(render_welcome) instead of any step card. No Guest entity.
"""
import re
from dataclasses import dataclass
from typing import Literal

from nicegui import ui

from ng_rdm.components import Col, Row, Button
from ng_rdm.utils import logger

from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login
from services.persona_loader import get_persona_config
from domain.invitations import accept_invitation
from domain.models import Invitation


Outcome = Literal['pending', 'in_progress', 'completed', 'failed', 'skipped']


@dataclass
class StepResult:
    """Outcome of a step's action. Returned from StepCard.act() and result handlers."""
    outcome: Outcome
    output: dict | None = None
    error: str | None = None
    fatal: bool = False


def expandable_info(valdict: dict) -> None:
    if valdict:
        with ui.expansion(_('View attributes'), icon='info').style('margin-top: 0.5rem;'):
            with Col(style='gap: 0.25rem;'):
                for key, value in valdict.items():
                    if value:
                        ui.label(f'{key}: {value}').style('font-size: 0.875rem;')


# ──────────────────────────── base class ────────────────────────────


class StepCard:
    """Base class for all step cards.

    Steps signal completion exclusively via the orchestrator's `record(step_id, result)`
    funnel — never by mutating state directly.
    """

    def __init__(self, config: dict):
        self.config = config
        self.title = config['title']
        self.completed_text = config['completed_text']
        self.disabled_text = config.get('disabled_text') or ''
        # Assigned by Steps._create_steps:
        self.step_id: str = ''
        self.steps: 'Steps | None' = None
        self.state: dict = {}
        self.tenant: str | None = None

    # ── overridable hooks ──────────────────────────────────────────────

    async def is_already_done(self) -> bool:
        """Override on verification-style steps that have a durable DB marker.
        Returning True at scenario startup → step is recorded as 'skipped'.
        Default: never auto-skip. No cross-persona auto-skip (§2.1)."""
        return False

    async def act(self) -> StepResult | None:
        """User-triggered action. Override in subclasses.

        Return a StepResult to record immediately, or None when completion is
        signaled asynchronously (e.g., via an OIDC callback's `result_handler`).
        """
        return None

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """OIDC callback. Override on OIDC-bound steps."""
        pass

    # ── rendering ─────────────────────────────────────────────────────

    def render(self, state: dict, outcome: str, is_enabled: bool) -> None:
        is_completed = outcome in ('completed', 'skipped')
        status_color = 'positive' if is_completed else 'grey'
        status_icon = 'check_circle' if is_completed else 'radio_button_unchecked'

        with ui.card().classes('step-card'):
            with Row().classes('step-card-row'):
                icon = ui.icon(status_icon, color=status_color).classes('step-icon')
                if is_enabled and not is_completed:
                    icon.on('click', self._handle_click)

                with Col(classes='step-content'):
                    ui.label(self.title).classes('step-title')
                    if is_completed:
                        self.render_completed(state)
                    elif is_enabled:
                        self.render_enabled(state)
                    else:
                        self.render_disabled(state)

    async def _handle_click(self):
        """Default click handler: run `act()`, record the result via the orchestrator."""
        if self.steps is None:
            return
        result = await self.act()
        if result is not None:
            await self.steps.record(self.step_id, result)

    def render_enabled(self, state: dict) -> None:
        raise NotImplementedError

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success').style('margin-top: 0.5rem;')

    def render_disabled(self, state: dict) -> None:
        ui.label(self.disabled_text).classes('text').style('margin-top: 0.5rem;')


# ──────────────────────────── concrete cards ────────────────────────────


class OIDCLoginStep(StepCard):
    """Generic OIDC login step. Writes verified userinfo to state['outputs'][idp]
    (keyed by IdP name, gotcha 10) — no GuestAttribute."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.idp: str = config['idp']
        self.primary_button_label: str = config['primary_button_label']
        self.secondary_button: dict | None = config.get('secondary_button')
        self.help_text: str | None = config.get('help_text')

    async def act(self) -> StepResult | None:
        if not self.tenant:
            logger.error("Tenant not set in step card")
            return StepResult('failed', error='tenant not set')
        await start_oidc_login(
            tenant=self.tenant,
            idp=self.idp,
            callback_handler=self.result_handler,
            next_url=f"/accept/{self.state.get('invite_code', '')}",
            force_login=True,
        )
        # Completion arrives asynchronously via result_handler; no immediate result.
        return None

    def _secondary_button_handler(self):
        if self.secondary_button:
            ui.navigate.to(self.secondary_button['url'], new_tab=True)

    def render_enabled(self, state: dict) -> None:
        if self.help_text:
            ui.label(_(self.help_text)).classes('text')
        with Row().classes('button-row'):
            with Col():
                Button(_(self.primary_button_label), on_click=self._handle_click).style('margin-right: 1rem;')
            if self.secondary_button:
                with Col(style='align-items: center; gap: 8px;'):
                    Button(_(self.secondary_button['label']), on_click=self._secondary_button_handler)
                    if self.secondary_button.get('hint'):
                        ui.label(_(self.secondary_button['hint'])).style('font-size: 0.95rem;')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success').style('margin-top: 0.5rem;')
        expandable_info(state.get('outputs', {}).get(self.idp, {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        logger.debug(f"{self.idp} login completed with userinfo: {userinfo}")
        self.state.setdefault('outputs', {})[self.idp] = userinfo
        if self.steps:
            await self.steps.record(self.step_id, StepResult('completed'))


class VerifyAlumniDb(StepCard):
    """Verify alumni status against a (simulated) records lookup.

    Generic enough to be reused for any "two-field lookup with format + range
    constraints" pattern. Writes its payload to state['outputs'][step_id]."""

    def __init__(self, config: dict):
        super().__init__(config)
        # Exclusive year bounds (year-of-birth must be strictly between min and max).
        self.dob_min_year: int = config.get('dob_min_year', 1960)
        self.dob_max_year: int = config.get('dob_max_year', 1990)
        self.student_number_pattern: str = config.get('student_number_pattern', r'^\d{5}$')
        self.dob_label: str = config.get('dob_label', 'Date of birth')
        self.student_number_label: str = config.get('student_number_label', 'Student number')
        self.primary_button_label: str = config.get('primary_button_label', 'Verify alumni status')
        self.help_text: str | None = config.get('help_text')

    def _dob_year(self, value: str) -> int | None:
        try:
            return int((value or '').split('-')[0])
        except ValueError:
            return None

    def _student_number_valid(self, value: str) -> bool:
        return bool(re.match(self.student_number_pattern, value or ''))

    async def act(self) -> StepResult | None:
        dob = (self.state.get('alumni_dob') or '').strip()
        student_number = (self.state.get('alumni_student_number') or '').strip()
        year = self._dob_year(dob)
        if (
            year is None
            or not (self.dob_min_year < year < self.dob_max_year)
            or not self._student_number_valid(student_number)
        ):
            ui.notify(
                _('No matching alumni record found — check your details and try again.'),
                type='negative',
            )
            return StepResult('failed', error='alumni lookup miss')
        return StepResult(
            'completed',
            output={'dob': dob, 'student_number': student_number},
        )

    def render_enabled(self, state: dict) -> None:
        with Col(style='gap: 0.75rem; max-width: 24rem;'):
            if self.help_text:
                ui.label(_(self.help_text)).classes('text')
            ui.input(label=_(self.dob_label), placeholder='YYYY-MM-DD') \
                .bind_value(self.state, 'alumni_dob').props('type=date').classes('form-input')
            ui.input(
                label=_(self.student_number_label),
                placeholder='12345',
                validation={
                    _('Five digits required'): lambda v: self._student_number_valid(v),
                },
            ).bind_value(self.state, 'alumni_student_number') \
             .props('type=text inputmode=numeric maxlength=5').classes('form-input')
            Button(_(self.primary_button_label), on_click=self._handle_click).style('margin-top: 0.5rem;')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success').style('margin-top: 0.5rem;')
        out = state.get('outputs', {}).get(self.step_id, {})
        if out:
            expandable_info({
                _(self.dob_label): out.get('dob', ''),
                _(self.student_number_label): out.get('student_number', ''),
            })


# ──────────────────────────── completion screen ────────────────────────────


def render_welcome(tenant: str | None, persona_key: str | None, given_name: str | None = None) -> None:
    """Terminal success screen shown once onboarding is complete.

    Shared by the in-session path (`Steps.render`) and the returning-user path
    (`routes/accept` on status=='accepted'), so both render identically. Message and
    CTA label are per-persona (localized); the CTA links to `success_redirect_url`.
    All persona lookups are guarded so a vanished persona still degrades to defaults.
    """
    message = cta_label = redirect_url = None
    if tenant and persona_key:
        try:
            cfg = get_persona_config(tenant, persona_key)
            message = cfg.completion_text('nl')
            cta_label = cfg.cta('nl')
            redirect_url = cfg.success_redirect_url
        except Exception:
            pass
    with Col(classes='accept-terminal'):
        ui.icon('check_circle', color='positive', size='3em')
        heading = f"{_('Welcome')}, {given_name}!" if given_name else _('Welcome')
        ui.label(heading).classes('page-title')
        ui.label(message or _('Your onboarding has been completed successfully.')).classes('page-subtitle')
        if redirect_url:
            Button(cta_label or _('Continue'), on_click=lambda: ui.navigate.to(redirect_url))


# ──────────────────────────── registry + orchestrator ────────────────────────────


STEP_CARD_CLASSES = {
    'OIDCLoginStep': OIDCLoginStep,
    'VerifyAlumniDb': VerifyAlumniDb,
}


class Steps:
    """Onboarding orchestrator.

    Owns: scenario instantiation, completion bookkeeping (`state['outcomes']`),
    output storage (`state['outputs']`), prerequisite evaluation (positional),
    and the built-in finalize side effect that runs once every step is done.
    """

    def __init__(self, tenant: str, state: dict, persona_config: dict):
        self.tenant = tenant
        self.state = state
        self.scenario_config = persona_config
        self.state.setdefault('outcomes', {})
        self.state.setdefault('outputs', {})
        self.step_instances = self._create_steps()

    @property
    def outcomes(self) -> dict[str, str]:
        return self.state['outcomes']

    @property
    def is_complete(self) -> bool:
        """True once every step is done and the finalize side effect has succeeded."""
        return self.state.get('completed') is True

    @property
    def context(self) -> dict:
        """Read-only scenario context exposed to `is_already_done`."""
        return {
            'tenant': self.tenant,
            'invite_code': self.state.get('invite_code', ''),
            'invitation_id': self.state.get('invitation_id'),
            'persona_key': self.state.get('persona_key'),
        }

    def _create_steps(self) -> list[StepCard]:
        instances: list[StepCard] = []
        for i, step_config in enumerate(self.scenario_config['steps']):
            step_class_name = step_config['class']
            if step_class_name not in STEP_CARD_CLASSES:
                raise ValueError(f"Unknown step card class: {step_class_name}")
            step_class = STEP_CARD_CLASSES[step_class_name]
            step_id = step_config.get('id', str(i))
            try:
                step_instance = step_class(step_config['config'])
            except KeyError as e:
                raise ValueError(
                    f"step '{step_id}' ({step_class_name}) is missing required config key {e}"
                ) from e
            step_instance.step_id = step_id
            step_instance.steps = self
            step_instance.state = self.state
            step_instance.tenant = self.tenant
            instances.append(step_instance)
        return instances

    async def startup(self) -> None:
        """Replay durable markers, then consult the finalize hook."""
        for step in self.step_instances:
            if self.outcomes.get(step.step_id) in ('completed', 'skipped'):
                continue
            if await step.is_already_done():
                self.outcomes[step.step_id] = 'skipped'
        await self._maybe_finalize()

    async def record(self, step_id: str, result: StepResult) -> None:
        """The single state-mutation funnel."""
        self.outcomes[step_id] = result.outcome
        if result.output is not None:
            self.state['outputs'][step_id] = result.output
        if result.outcome == 'completed':
            await self._maybe_finalize()
        # Refresh if a live render exists; OIDC callback context has no live render.
        try:
            self.render.refresh()
        except Exception:
            pass

    async def _maybe_finalize(self) -> None:
        """Run the terminal side effect once every step is completed/skipped.

        Replaces the old FinalizeStep: no longer a card, just the scenario-wide
        accept + webhook. Idempotent — guarded by the `completed`/`finalize_failed`
        flags within the session and by the invitation's own status across sessions.
        """
        if self.state.get('completed') or self.state.get('finalize_failed'):
            return
        if not all(o in ('completed', 'skipped') for o in
                   (self.outcomes.get(s.step_id) for s in self.step_instances)):
            return
        try:
            ok = await self._finalize()
        except Exception as e:
            logger.error(f"finalize raised: {e}")
            self.state['finalize_failed'] = True
            return
        self.state['completed' if ok else 'finalize_failed'] = True

    async def _finalize(self) -> bool:
        """Persist state['outputs'] to Invitation.step_outputs, then accept (fires the
        webhook). Idempotent for already-accepted invitations. Returns success."""
        if not self.tenant:
            return False
        invite_code = self.state.get('invite_code')
        if not invite_code:
            return False
        inv = await Invitation.get_or_none(tenant=self.tenant, code=invite_code)
        if inv is None:
            return False
        if inv.status == 'pending':
            # Persist outputs BEFORE accept so the webhook envelope can read them (§2.7).
            # Through the store (like every other write) so open tables stay live.
            from domain.stores import get_invitation_store
            await get_invitation_store(self.tenant).update_item(
                inv.id, {"step_outputs": dict(self.state.get('outputs', {})) or None})
            if not await accept_invitation(self.tenant, invite_code):
                return False
        return True

    def _render_heading(self) -> None:
        persona_label = ''
        persona_key = self.state.get('persona_key')
        if persona_key and self.tenant:
            try:
                persona_label = get_persona_config(self.tenant, persona_key).label('nl')
            except Exception:
                persona_label = ''

        suffix = (' ' + _('as') + ' ' + persona_label) if persona_label else ''
        given = self.state.get('given_name')
        if given:
            ui.label(f"{_('Welcome')}, {given}{suffix}").classes('page-title')
        else:
            ui.label(_('Welcome{suffix}', suffix=suffix)).classes('page-title')
        ui.label(
            _('Follow the step-by-step plan below to accept your invitation{suffix}.', suffix=suffix)
        ).classes('page-subtitle')

    @ui.refreshable
    def render(self) -> None:
        if self.is_complete:
            render_welcome(self.tenant, self.state.get('persona_key'), self.state.get('given_name'))
            return
        if self.state.get('finalize_failed'):
            with Col(classes='accept-terminal'):
                ui.icon('error_outline', size='3em').classes('icon-error')
                ui.label(_('This invitation cannot be processed right now.')).classes('page-title')
                ui.label(_('Please contact the sender of your invitation.')).classes('page-subtitle')
            return

        self._render_heading()
        for i, step in enumerate(self.step_instances):
            outcome = self.outcomes.get(step.step_id, 'pending')
            is_enabled = all(
                self.outcomes.get(self.step_instances[j].step_id) in ('completed', 'skipped')
                for j in range(i)
            )
            step.render(self.state, outcome, is_enabled)
