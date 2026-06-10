"""Step-card contract: the base class adopters subclass, the result type, and the
auto-registry. See docs/step_cards.md for the full lifecycle, the MAY / MAY NOT
rules, and the single-session invariant.

OIDC steps write verified userinfo to state['outputs'][idp] (keyed by IdP name);
non-OIDC steps write to state['outputs'][step_id]. Finalization is a built-in
orchestrator side effect (Steps._finalize), not a card.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from nicegui import ui

from ng_rdm.components import Col, Row

from services.i18n import _

if TYPE_CHECKING:
    from steps.orchestrator import Steps


Outcome = Literal['pending', 'in_progress', 'completed', 'failed', 'skipped']


@dataclass
class StepResult:
    """Outcome of a step's action. Returned from StepCard.act() and result handlers."""
    outcome: Outcome
    output: dict | None = None
    error: str | None = None
    fatal: bool = False


# Registry: every StepCard subclass auto-registers by class name (= the "class"
# field in settings.json), so adding a card is just dropping a module in steps/cards/.
STEP_CARD_CLASSES: dict[str, type['StepCard']] = {}


def expandable_info(valdict: dict) -> None:
    if valdict:
        with ui.expansion(_('View attributes'), icon='info').classes('step-expansion'):
            with Col(style='gap: 0.25rem;'):
                for key, value in valdict.items():
                    if value:
                        ui.label(f'{key}: {value}').style('font-size: 0.875rem;')


class StepCard:
    """Base class for all step cards. To build one, subclass this and:

      • read your config in __init__ (call super().__init__(config) first);
      • paint your UI in render_enabled(state) — a free-form NiceGUI canvas
        (use `with self.form_column():` for the standard single-column form chrome);
      • finish with `await self.complete(output)` / `await self.fail(...)`, or — for a
        single-button step — override act() to return a StepResult.

    The orchestrator (card chrome, prerequisite gating, finalize/webhook) stays
    invisible: cards never read state['outcomes'] or call the orchestrator directly.
    """

    def __init__(self, config: dict):
        self.config = config
        self.title = config['title']
        self.completed_text = config['completed_text']
        self.disabled_text = config.get('disabled_text') or ''
        self.help_text: str | None = config.get('help_text')
        # Assigned by Steps._create_steps:
        self.step_id: str = ''
        self.steps: Steps | None = None
        self.state: dict = {}
        self.tenant: str | None = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        STEP_CARD_CLASSES[cls.__name__] = cls

    # ── overridable hooks ──────────────────────────────────────────────

    async def is_already_done(self) -> bool:
        """Override on verification-style steps that have a durable DB marker.
        Returning True at scenario startup → step is recorded as 'skipped'.
        Default: never auto-skip. No cross-persona auto-skip."""
        return False

    async def act(self) -> StepResult | None:
        """User-triggered action for single-button steps. Override to return a
        StepResult (recorded immediately), or None when completion is signaled
        asynchronously (e.g. via an OIDC callback's `result_handler`)."""
        return None

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """OIDC callback. Override on OIDC-bound steps."""
        pass

    # ── completion helpers (how a card finishes — no orchestrator vocabulary) ──

    async def complete(self, output: dict | None = None) -> None:
        """Record this step completed; `output` lands in state['outputs'][step_id]."""
        if self.steps:
            await self.steps.record(self.step_id, StepResult('completed', output=output))

    async def fail(self, error: str | None = None, *, notify: str | None = None, fatal: bool = False) -> None:
        """Record a failure (recoverable by default); optionally toast `notify` first."""
        if notify:
            ui.notify(_(notify), type='negative')
        if self.steps:
            await self.steps.record(self.step_id, StepResult('failed', error=error, fatal=fatal))

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
                    ui.label(_(self.title)).classes('step-title')
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

    def render_help(self) -> None:
        """Render the optional help_text label, if configured."""
        if self.help_text:
            ui.label(_(self.help_text)).classes('text')

    @contextmanager
    def form_column(self) -> Iterator[Col]:
        """Standard single-column form chrome: renders help_text, then yields the column."""
        col = Col(style='gap: 0.75rem; max-width: 24rem;')
        with col:
            self.render_help()
            yield col

    def render_enabled(self, state: dict) -> None:
        raise NotImplementedError

    def render_completed(self, state: dict) -> None:
        ui.label(_(self.completed_text)).classes('text-success')

    def render_disabled(self, state: dict) -> None:
        ui.label(_(self.disabled_text)).classes('text')
