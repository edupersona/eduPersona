"""Intake-collection step: a short free-form form (organisatie + toepassingsscenario).

Both fields are nullable — the step always completes; whatever the user typed (or
nothing) is recorded and surfaced to the persona's completion side effect.
"""
from ng_rdm.components import Button
from nicegui import ui

from services.i18n import _
from steps.base import StepCard, expandable_info


class CollectIntakeStep(StepCard):
    """Collect optional intake details (organisation + an open scenario question)."""

    def render_enabled(self) -> None:
        with self.form_column():
            ui.input(label='naam van je organisatie') \
                .bind_value(self.state, 'organisatie').classes('form-input')
            ui.textarea(label='heb je al een toepassing in gedachten?') \
                .bind_value(self.state, 'toepassingsscenario').classes('form-input')
            Button(_(self.config.get('submit_label', 'Verder')), on_click=self._submit) \
                .classes('step-primary-button')

    async def _submit(self) -> None:
        await self.complete({
            'organisatie': (self.state.get('organisatie') or '').strip() or None,
            'toepassingsscenario': (self.state.get('toepassingsscenario') or '').strip() or None,
        })

    def render_completed(self) -> None:
        ui.label(_(self.completed_text)).classes('text-success')
        out = self.state.get('outputs', {})
        if out:
            expandable_info({
                'organisatie': out.get('organisatie') or '',
                'toepassingsscenario': out.get('toepassingsscenario') or '',
            })
