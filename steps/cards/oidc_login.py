"""eduID / institutional OIDC login step."""
from nicegui import ui

from ng_rdm.components import Col, Row, Button
from ng_rdm.utils import logger

from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login

from steps.base import StepCard, StepResult, expandable_info


class OIDCLoginStep(StepCard):
    """Generic OIDC login step. Records the verified userinfo as its output (keyed,
    like every step, by this step's id); the id_token's `acr` is merged into that
    userinfo so the callback always carries it.

    With an optional `acr_value`, the step additionally *requests* that ACR (e.g.
    `https://refeds.org/profile/mfa` to force MFA step-up) and *verifies* the returned
    `acr` matches before completing. On mismatch the step fails (non-fatal) and stays
    retryable, showing `acr_failed_text`."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.idp: str = config['idp']
        self.primary_button_label: str = config['primary_button_label']
        self.secondary_button: dict | None = config.get('secondary_button')
        # Optional ACR step-up: a single ACR to request and verify (OIDC `acr_values`).
        self.acr_value: str | None = config.get('acr_value')
        self.acr_failed_text: str = config.get('acr_failed_text') or \
            'Required authentication level not met. Please try again.'

    async def act(self) -> StepResult | None:
        assert self.tenant and self.steps
        self.state.pop('acr_failed', None)  # clear a prior mismatch on retry
        await start_oidc_login(
            tenant=self.tenant,
            idp=self.idp,
            callback_handler=self.result_handler,
            next_url=f"/accept/{self.steps.context['invite_code']}",
            force_login=True,
            acr_value=self.acr_value,  # None ⇒ dropped by start_oidc_login
        )
        # Completion arrives asynchronously via result_handler; no immediate result.
        return None

    def render_enabled(self) -> None:
        if self.state.get('acr_failed'):
            ui.label(_(self.acr_failed_text)).classes('text-error')
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
        returned_acr = id_token_claims.get('acr')
        logger.debug(f"{self.idp} login completed (acr={returned_acr!r}) with userinfo: {userinfo}")
        if self.acr_value and returned_acr != self.acr_value:
            logger.warning(f"{self.idp} ACR check failed: requested {self.acr_value!r}, got {returned_acr!r}")
            self.state['acr_failed'] = True
            await self.fail(error=f"acr mismatch: requested {self.acr_value!r}, got {returned_acr!r}")
            return
        if returned_acr is not None:
            userinfo['acr'] = returned_acr  # acr is an id_token claim; surface it in the output
        await self.complete(userinfo)
