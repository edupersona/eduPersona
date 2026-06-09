"""Simulated MFA / ACR verification step (dialog-confirm)."""
from ng_rdm.components import Button, Dialog

from services.i18n import _

from steps.base import StepCard


class VerifyMfaStep(StepCard):
    """MFA / ACR verification. The card button opens a confirm dialog; confirming
    records the configured ACR as a verified fact. (Behaviour is currently simulated —
    no real IdP round-trip — but the contract is the real thing.)

    If `target_output` names an existing output (e.g. the eduID userinfo from a prior
    step), the ACR is merged there so it rides that step's `callback_outputs`;
    otherwise it lands under this step's own id."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.primary_button_label: str = config['primary_button_label']
        self.dialog_title: str = config['dialog_title']
        self.confirm_button_label: str = config['confirm_button_label']
        self.acr_value: str = config['acr_value']
        self.target_output: str | None = config.get('target_output')
        # Built once, lazily, on first render: Dialog mounts its backdrop on the client
        # root layout, so it survives render() rebuilds — rebuilding would leak backdrops.
        self._dialog: Dialog | None = None

    async def _confirm(self) -> None:
        if self._dialog:
            self._dialog.close()
        outputs = self.state.setdefault('outputs', {})
        if self.target_output and isinstance(outputs.get(self.target_output), dict):
            outputs[self.target_output]['acr'] = self.acr_value
            await self.complete()
        else:
            await self.complete({'acr': self.acr_value})

    def _ensure_dialog(self) -> Dialog:
        if self._dialog is None:
            self._dialog = Dialog(title=self.dialog_title, dialog_class="panel-dialog")
            with self._dialog, self._dialog.actions():
                Button(_(self.confirm_button_label), on_click=self._confirm)
        return self._dialog

    def render_enabled(self, state: dict) -> None:
        dialog = self._ensure_dialog()
        Button(_(self.primary_button_label), on_click=dialog.open).classes('step-primary-button')
