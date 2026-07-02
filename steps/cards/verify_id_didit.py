"""Didit ID-verification step: passport / Dutch ID card + liveness + face match.

Structural twin of OIDCLoginStep: the button starts a hosted Didit session and
redirects away; completion arrives asynchronously when Didit redirects the browser
back to /didit_callback, which polls the decision and calls result_handler_didit.
The extracted ID fields (name, document number, DOB, nationality, ...) become this
step's output, delivered to the webhook keyed by the step id.
"""
from nicegui import app, ui

from ng_rdm.components import Button, Col, Row
from ng_rdm.utils import logger

from services.didit import (
    bind_pending_state,
    create_session,
    extract_id_fields,
    new_state,
    register_pending_session,
)
from services.i18n import _
from services.settings import config

from steps.base import StepCard, StepResult, expandable_info


class VerifyIdDiditStep(StepCard):
    """Verify a government ID via Didit's hosted flow. Records the extracted document
    fields as its output. On a non-approved decision the step fails (non-fatal) and
    stays retryable, showing `declined_text`."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.primary_button: dict | None = config.get('primary_button')
        self.declined_text: str = config.get('declined_text') or \
            'Verification was not successful. Please try again.'

    async def act(self) -> StepResult | None:
        assert self.tenant and self.steps
        self.state.pop('declined', None)  # clear a prior decline on retry
        invite_code = self.steps.context['invite_code']

        # Mint the state token first so it can go into the callback URL, then create the
        # session, then register the transaction (needs the returned session_id).
        state = new_state()
        base_url = config.get('base_url', 'http://localhost:8080')
        callback_url = f"{base_url}/didit_callback?state={state}"
        vendor_data = f"{self.tenant}:{invite_code}:{self.step_id}"
        try:
            session = await create_session(self.tenant, vendor_data, callback_url)
        except ValueError as e:
            logger.error(f"Didit session create failed: {e}")
            ui.notify(_('Could not start ID verification. Please try again later.'), type='negative')
            return None

        session_id, session_url = session.get('session_id'), session.get('url')
        if not session_id or not session_url:
            logger.error(f"Didit session response missing id/url: {session}")
            ui.notify(_('Could not start ID verification. Please try again later.'), type='negative')
            return None

        register_pending_session(state, {
            'tenant': self.tenant,
            'session_id': session_id,
            'callback_handler': self.result_handler_didit,
            'next_url': f"/accept/{invite_code}",
        })
        await ui.context.client.connected()
        bind_pending_state(app.storage.user.setdefault('didit_pending_states', []), state)
        ui.navigate.to(session_url)
        # Completion arrives asynchronously via result_handler_didit; no immediate result.
        return None

    async def result_handler_didit(self, decision: dict) -> None:
        """Called from /didit_callback with the polled decision."""
        status = (decision.get('status') or '').lower()
        logger.debug(f"Didit decision status={status!r}")
        if status == 'approved':
            await self.complete(extract_id_fields(decision))
        else:
            self.state['declined'] = True
            await self.fail(error=f"didit status: {decision.get('status')}")

    def render_enabled(self) -> None:
        if self.state.get('declined'):
            ui.label(_(self.declined_text)).classes('text-error')
        self.render_help()
        with Row().classes('button-row'):
            if self.primary_button:
                with Col():
                    Button(_(self.primary_button.get('label', '')),
                           on_click=self._handle_click).classes('step-primary-button')
                    if self.primary_button.get('hint'):
                        ui.label(_(self.primary_button['hint'])).classes('step-primary-hint step-hint')

    def render_completed(self) -> None:
        ui.label(_(self.completed_text)).classes('text-success')
        expandable_info(self.state.get('outputs', {}))
