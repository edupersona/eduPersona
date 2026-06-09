"""eduID / institutional OIDC login step."""
from nicegui import ui

from ng_rdm.components import Col, Row, Button
from ng_rdm.utils import logger

from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login

from steps.base import StepCard, StepResult, expandable_info


class OIDCLoginStep(StepCard):
    """Generic OIDC login step. Writes verified userinfo to state['outputs'][idp]
    (keyed by IdP name, gotcha 10) — no GuestAttribute."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.idp: str = config['idp']
        self.primary_button_label: str = config['primary_button_label']
        self.secondary_button: dict | None = config.get('secondary_button')

    async def act(self) -> StepResult | None:
        assert self.tenant
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
        self.render_help()
        with Row().classes('button-row'):
            with Col():
                Button(_(self.primary_button_label), on_click=self._handle_click).classes('step-primary-button')
            if self.secondary_button:
                with Col(style='align-items: center; gap: 8px;'):
                    Button(_(self.secondary_button['label']), on_click=self._secondary_button_handler).classes(
                        'step-secondary-button')
                    if self.secondary_button.get('hint'):
                        ui.label(_(self.secondary_button['hint'])).classes('step-secondary-hint')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success')
        expandable_info(state.get('outputs', {}).get(self.idp, {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        logger.debug(f"{self.idp} login completed with userinfo: {userinfo}")
        self.state.setdefault('outputs', {})[self.idp] = userinfo
        await self.complete()
