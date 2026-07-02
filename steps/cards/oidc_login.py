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
    `https://refeds.org/profile/mfa` to force MFA step-up); verification is handled by the
    generic gate — a derived exact match rule on the output's `acr` (see steps/matching.py).
    A mismatch blocks the step via render_match_failed, like any other gate failure."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.idp: str = config['idp']
        self.primary_button: dict | None = config.get('primary_button')
        self.secondary_button: dict | None = config.get('secondary_button')
        # Optional ACR step-up: a single ACR to request (OIDC `acr_values`). Verified via a
        # derived exact match rule so the check goes through the same gate as every other step.
        self.acr_value: str | None = config.get('acr_value')
        if self.acr_value:
            self.match_rules.append({'source': f'const:{self.acr_value}', 'field': 'acr',
                                     'label': 'Authentication level', 'exact': True})

    async def act(self) -> StepResult | None:
        assert self.tenant and self.steps
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
        self.render_help()
        with Row().classes('button-row'):
            if self.primary_button:
                with Col():
                    Button(_(self.primary_button.get('label', '')),
                           on_click=self._handle_click).classes('step-primary-button')
                    if self.primary_button.get('hint'):
                        ui.label(_(self.primary_button['hint'])).classes('step-primary-hint step-hint')
            if self.secondary_button:
                with Col(style='align-items: center; gap: 8px;'):
                    # Native <a target="_blank"> (via Quasar href) so the browser opens the
                    # tab on the click gesture itself — a Python handler calling
                    # ui.navigate.to(new_tab=True) round-trips and trips the popup blocker.
                    Button(_(self.secondary_button['label'])).props(
                        f'href="{self.secondary_button["url"]}" target="_blank"').classes('step-secondary-button')
                    if self.secondary_button.get('hint'):
                        ui.label(_(self.secondary_button['hint'])).classes('step-secondary-hint step-hint')

    def render_completed(self) -> None:
        ui.label(_(self.completed_text)).classes('text-success')
        expandable_info(self.state.get('outputs', {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        returned_acr = id_token_claims.get('acr')
        logger.debug(f"{self.idp} login completed (acr={returned_acr!r})")
        logger.debug(f"{self.idp} all id_token claims: {id_token_claims}")
        logger.debug(f"{self.idp} userinfo: {userinfo}")
        if returned_acr is not None:
            userinfo['acr'] = returned_acr  # acr is an id_token claim; surface it in the output
        # ACR is verified by the gate (derived match rule); a mismatch blocks in record().
        await self.complete(userinfo)
