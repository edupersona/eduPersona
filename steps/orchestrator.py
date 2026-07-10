"""The onboarding orchestrator (`Steps`) and the terminal welcome screen.

`Steps` owns scenario instantiation, completion bookkeeping (`state['outcomes']`),
the derived `outputs` map (each step's output lives in its own state slot), positional
prerequisite evaluation, and the finalize side effect — gated behind the Register button.
Cards never touch any of this — they signal outcomes via StepCard.complete()/fail()
(or by returning a StepResult from act()), which funnel through `record()`.
"""
from nicegui import ui

from ng_rdm.components import Col, Button
from ng_rdm.utils import logger

from services.i18n import _
from services.persona_loader import get_persona_config
from domain.invitations import accept_invitation
from domain.models import Invitation

from steps.base import StepCard, StepResult, STEP_CARD_CLASSES
from steps.collected_data import CollectedDataModal
from steps.matching import evaluate_matches


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
            message = cfg.completion_message
            cta_label = cfg.cta_label
            redirect_url = cfg.success_redirect_url
        except Exception:
            pass
    with Col(classes='accept-terminal'):
        ui.icon('check_circle', color='positive', size='3em')
        heading = f"{_('Welcome')}, {given_name}!" if given_name else _('Welcome')
        ui.label(heading).classes('page-title')
        subtitle = _(message) if message else _('Your onboarding has been completed successfully.')
        ui.label(subtitle).classes('page-subtitle')
        if redirect_url:
            Button(_(cta_label) if cta_label else _('Continue'), on_click=lambda: ui.navigate.to(redirect_url))


class Steps:
    """Onboarding orchestrator.

    Owns: scenario instantiation, completion bookkeeping (`state['outcomes']`),
    the derived `outputs` map (per-step, from each card's own state), prerequisite
    evaluation (positional), and the finalize side effect, gated behind Register.
    """

    def __init__(self, tenant: str, state: dict, persona_config: dict):
        self.tenant = tenant
        self.state = state
        self.scenario_config = persona_config
        self.state.setdefault('outcomes', {})
        self.step_instances = self._create_steps()
        self._modal: CollectedDataModal | None = None

    @property
    def outcomes(self) -> dict[str, str]:
        return self.state['outcomes']

    @property
    def outputs(self) -> dict[str, dict]:
        """Derived {step_id: output} map — each step's output lives in its own state slot."""
        return {sid: st['outputs'] for sid, st in self.state.get('step_state', {}).items()
                if isinstance(st, dict) and st.get('outputs') is not None}

    @property
    def is_complete(self) -> bool:
        """True once every step is done and the finalize side effect has succeeded."""
        return self.state.get('completed') is True

    @property
    def all_steps_done(self) -> bool:
        """Every step completed or skipped — the review gate (Register button) shows."""
        return bool(self.step_instances) and all(
            self.outcomes.get(s.step_id) in ('completed', 'skipped')
            for s in self.step_instances)

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
            own = self.state.setdefault('step_state', {}).setdefault(step_id, {})
            for k, v in step_instance.state.items():  # preserve constructor-set defaults; resumed state wins
                own.setdefault(k, v)
            step_instance.state = own  # the card's own (persisted) state — never the session dict
            step_instance.tenant = self.tenant
            instances.append(step_instance)
        return instances

    async def startup(self) -> None:
        """Replay durable markers — verification steps with a durable DB marker record
        as 'skipped'. Finalization is gated behind the Register button, not run here."""
        for step in self.step_instances:
            if self.outcomes.get(step.step_id) in ('completed', 'skipped'):
                continue
            if await step.is_already_done():
                self.outcomes[step.step_id] = 'skipped'

    async def record(self, step_id: str, result: StepResult) -> None:
        """The single state-mutation funnel. A completed step whose output fails its
        verification gate (match rules) is downgraded to 'failed' and its output dropped —
        the specific differences are stashed for render_match_failed to surface."""
        slot = self.state.setdefault('step_state', {}).setdefault(step_id, {})
        if result.outcome == 'completed' and result.output is not None:
            step = next((s for s in self.step_instances if s.step_id == step_id), None)
            failures = evaluate_matches(step.match_rules, self.state, result.output) if step else []
            if failures:
                slot['match_failures'] = [vars(f) for f in failures]
                result = StepResult('failed', error='verification mismatch')  # drop the rejected output
            else:
                slot.pop('match_failures', None)

        self.outcomes[step_id] = result.outcome
        if result.output is not None:  # output lives in the step's own state slot (= card.state)
            slot['outputs'] = result.output
        # No auto-finalize: once every step is done the render shows a review gate
        # with a 'Register' button; finalization happens on that explicit click.
        # Refresh if a live render exists; OIDC callback context has no live render.
        try:
            self.render.refresh()
        except Exception:
            pass

    async def restart(self) -> None:
        """Start the flow over from step 1 within this session — the retry affordance for a
        blocked (match-failed) step. Clears progress and rebuilds the cards; the invitation is
        never touched, so it stays pending. Mirrors apply_invite_to_state's reset-on-change."""
        self.state['outcomes'] = {}
        self.state['step_state'] = {}
        self.state.pop('completed', None)
        self.state.pop('finalize_failed', None)
        self.step_instances = self._create_steps()
        try:
            self.render.refresh()
        except Exception:
            pass

    def _ensure_modal(self) -> None:
        """Create the collected-data receipt modal once. The Dialog escapes to the
        client root layout, so caching the instance keeps render() refreshes from leaking
        backdrops."""
        if self._modal is None:
            self._modal = CollectedDataModal()

    async def _collected_segments(self) -> list[tuple[str, dict]]:
        """(segment_title, key→value) blocks for the receipt modal: a general
        invitation-level block, optional persona parameters, then one block per step's
        recorded output — mirroring the step cards."""
        persona_key = self.state.get('persona_key')
        persona_label = persona_key or ''
        if persona_key and self.tenant:
            try:
                persona_label = _(get_persona_config(self.tenant, persona_key).display_name)
            except Exception:
                pass
        inv = await Invitation.get_or_none(tenant=self.tenant, code=self.state.get('invite_code', ''))
        name = f"{self.state.get('given_name') or ''} {self.state.get('family_name') or ''}".strip()
        general = {
            _('Persona'): persona_label,
            _('Name'): name,
            _('Email'): self.state.get('guest_email'),
            _('Guest ID'): inv.guest_id if inv else None,
            _('Code'): self.state.get('invite_code'),
        }
        segments: list[tuple[str, dict]] = [(_('General information'), {k: v for k, v in general.items() if v})]
        params = self.state.get('persona_params') or {}
        if params:
            segments.append((_('Persona parameters'), params))
        title_by_id = {s.step_id: _(s.title) for s in self.step_instances}
        for step_id, output in self.outputs.items():
            if output:
                segments.append((title_by_id.get(step_id, step_id), output))
        return segments

    async def register(self) -> None:
        """The 'Register' button. Persists the `outputs` map to Invitation.step_outputs,
        accepts (firing the webhook callback + any SCIM push), flips to the welcome
        screen, then surfaces the collected-data receipt modal over it (the PoC stand-in
        for a real listener). Gated on every step being done; idempotent — guarded by the
        `completed`/`finalize_failed` flags within the session and by the invitation's own
        status across sessions.
        """
        if self.state.get('completed') or self.state.get('finalize_failed'):
            return
        if not self.all_steps_done:
            return
        try:
            ok = await self._finalize()
        except Exception as e:
            logger.error(f"finalize raised: {e}")
            self.state['finalize_failed'] = True
        else:
            self.state['completed' if ok else 'finalize_failed'] = True
        try:
            self.render.refresh()
        except Exception:
            pass
        # Receipt: show what was just delivered, over the welcome screen. Only when a
        # live render built the modal (headless callers — tests, OIDC — leave it None).
        if self.state.get('completed') and self._modal is not None:
            self._modal.open(await self._collected_segments())

    async def _finalize(self) -> bool:
        """Persist the `outputs` map to Invitation.step_outputs, then accept (fires the
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
            # Persist outputs BEFORE accept so the webhook envelope can read them.
            # Through the store (like every other write) so open tables stay live.
            from domain.stores import get_invitation_store
            await get_invitation_store(self.tenant).update_item(
                inv.id, {"step_outputs": self.outputs or None})
            if not await accept_invitation(self.tenant, invite_code):
                return False
        return True

    def _render_heading(self) -> None:
        persona_label = ''
        persona_key = self.state.get('persona_key')
        if persona_key and self.tenant:
            try:
                persona_label = _(get_persona_config(self.tenant, persona_key).display_name)
            except Exception:
                persona_label = ''

        suffix = (' ' + _('as') + ' ' + persona_label) if persona_label else ''
        given = self.state.get('given_name', '')
        if given:
            ui.label(f"{_('Welcome')}, {given}").classes('page-title')
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
        # First not-yet-passed step — the one the guest acts on now. `len` (past the
        # end) means every step is done, so the review gate below is the active target.
        active_index = next(
            (i for i, s in enumerate(self.step_instances)
             if self.outcomes.get(s.step_id) not in ('completed', 'skipped')),
            len(self.step_instances),
        )
        for i, step in enumerate(self.step_instances):
            if i == active_index:
                ui.element('div').classes('accept-active-anchor')
            outcome = self.outcomes.get(step.step_id, 'pending')
            is_enabled = all(
                self.outcomes.get(self.step_instances[j].step_id) in ('completed', 'skipped')
                for j in range(i)
            )
            step.render(outcome, is_enabled)

        # Review gate: every step is verified, but nothing is sent yet. The guest
        # reviews the data above, then registers to fire the callback + accept.
        if self.all_steps_done:
            self._ensure_modal()  # pre-build the receipt modal in the render slot; register() opens it
            ui.element('div').classes('accept-active-anchor')
            with Col(classes='accept-register'):
                Button(_('Register'), on_click=self.register).classes('step-primary-button')

        # Narrow screens only: after a step completes the next card is below the fold —
        # bring it to the top. Mirrors ui.sub_pages' own scroll-into-view. Skipped on a
        # fresh start (active_index 0, heading stays visible) and on desktop (media guard).
        if active_index > 0:
            ui.run_javascript(
                "if (window.matchMedia('(max-width: 768px)').matches) requestAnimationFrame(() => "
                "document.querySelector('.accept-active-anchor')"
                "?.scrollIntoView({behavior: 'smooth', block: 'start'}))"
            )
