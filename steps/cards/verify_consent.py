"""Consent step (dialog-confirm): the guest reviews a consent text and/or an external
link, ticks a checkbox, and confirms. The only fact recorded is `consent_given` — an
ISO-8601 UTC timestamp of when Confirm was pressed. No backend round-trip, but the
StepCard contract (prerequisite gating, output keyed by step_id, callback delivery) is real."""
from datetime import datetime, timezone

from ng_rdm.components import Button, Dialog
from nicegui import ui

from services.i18n import _
from steps.base import StepCard, expandable_info


class VerifyConsentStep(StepCard):
    def __init__(self, config: dict):
        super().__init__(config)
        self.primary_button: dict | None = config.get('primary_button', {})
        self.dialog_title: str = config['dialog_title']
        self.confirm_button_label: str = config['confirm_button_label']
        self.consent_text: str | None = config.get('consent_text')
        self.consent_link: dict | None = config.get('consent_link')
        self.consent_label: str = config.get('consent_label', 'I agree')
        self.state['consent_checked'] = False
        # Built once, lazily, on first render: Dialog mounts its backdrop on the client
        # root layout, so it survives render() rebuilds — rebuilding would leak backdrops.
        self._dialog: Dialog | None = None

    def _open(self) -> None:
        self.state['consent_checked'] = False  # reset the gate each time the dialog opens
        self._ensure_dialog().open()

    async def _confirm(self) -> None:
        if self._dialog:
            self._dialog.close()
        await self.complete({'consent_given': datetime.now(timezone.utc).isoformat()})

    def _ensure_dialog(self) -> Dialog:
        if self._dialog is None:
            self._dialog = Dialog(title=_(self.dialog_title), dialog_class="panel-dialog consent-dialog")
            with self._dialog:
                if self.consent_text:
                    ui.textarea(value=_(self.consent_text)).props('readonly autogrow=false').classes('consent-text')
                if self.consent_link and self.consent_link.get('url'):
                    ui.link(_(self.consent_link.get('label') or self.consent_link['url']),
                            self.consent_link['url'], new_tab=True).classes('consent-link')
                ui.checkbox(_(self.consent_label)).bind_value(self.state, 'consent_checked').classes('consent-check')
                with self._dialog.actions():
                    Button(_(self.confirm_button_label), on_click=self._confirm) \
                        .bind_enabled_from(self.state, 'consent_checked')
        return self._dialog

    def render_enabled(self) -> None:
        if self.primary_button:
            Button(_(self.primary_button.get('label', '')), on_click=self._open).classes('step-primary-button')

    def render_completed(self) -> None:
        ui.label(self.completed_text).classes('text-success')
        expandable_info(self.state.get('outputs', {}))
