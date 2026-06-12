"""eduID / institutional OIDC login step."""
from nicegui import ui

from ng_rdm.components import Col, Row, Button
from ng_rdm.utils import logger

from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login

from steps.base import StepCard, StepResult, expandable_info


class OIDCLoginStep(StepCard):
    """Generic OIDC login step. Records the verified userinfo as its output (keyed,
    like every step, by this step's id)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.idp: str = config['idp']
        self.primary_button_label: str = config['primary_button_label']
        self.secondary_button: dict | None = config.get('secondary_button')

    async def act(self) -> StepResult | None:
        assert self.tenant and self.steps
        await start_oidc_login(
            tenant=self.tenant,
            idp=self.idp,
            callback_handler=self.result_handler,
            next_url=f"/accept/{self.steps.context['invite_code']}",
            force_login=True,
        )
        # Completion arrives asynchronously via result_handler; no immediate result.
        return None

    def render_enabled(self) -> None:
        self.render_help()
        with Row().classes('button-row'):
            with Col():
                Button(_(self.primary_button_label), on_click=self._handle_click).classes('step-primary-button')
            if self.secondary_button:
                with Col(style='align-items: center; gap: 8px;'):
                    # Native <a target="_blank"> (via Quasar href) so the browser opens the
                    # tab on the click gesture itself — a Python handler calling
                    # ui.navigate.to(new_tab=True) round-trips and trips the popup blocker.
                    Button(_(self.secondary_button['label'])).props(
                        f'href="{self.secondary_button["url"]}" target="_blank"').classes('step-secondary-button')
                    if self.secondary_button.get('hint'):
                        ui.label(_(self.secondary_button['hint'])).classes('step-secondary-hint')

    def render_completed(self) -> None:
        ui.label(_(self.completed_text)).classes('text-success')
        expandable_info(self.state.get('outputs', {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        logger.debug(f"{self.idp} login completed with userinfo: {userinfo}")
        await self.complete(userinfo)
