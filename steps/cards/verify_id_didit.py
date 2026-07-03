"""Didit ID-verification step: passport / Dutch ID card + liveness + face match.

Self-contained in-app flow, no browser redirect: clicking Start creates a hosted Didit
session and shows its URL as a QR code. The user scans it with their phone and captures
document + selfie there (the phone talks only to Didit); meanwhile this card polls the
decision on a timer and advances the desktop in place when it's Approved. The extracted
ID fields (name, document number, DOB, nationality, ...) become this step's output,
delivered to the webhook keyed by the step id.

Phases live in `self.state['phase']` ('start' | 'awaiting' | 'declined'); panels toggle
via bind_visibility_from (like VerifyMobileStep), so no manual orchestrator refresh.
"""
import time

from nicegui import ui

from ng_rdm.components import Button, Col, Row
from ng_rdm.utils import logger

from services.didit import create_session, extract_id_fields, get_decision, qr_data_uri
from services.i18n import _

from steps.base import StepCard, expandable_info


class VerifyIdDiditStep(StepCard):
    """Verify a government ID via Didit's hosted flow, driven from the desktop by polling.
    Records the extracted document fields as its output. A non-approved decision moves to
    the 'declined' phase (non-fatal) and stays retryable."""

    POLL_INTERVAL = 4.0    # seconds between decision polls (limit is 100/min)
    POLL_TIMEOUT = 600     # give up (→ declined) after 10 min of waiting

    def __init__(self, config: dict):
        super().__init__(config)
        self.primary_button: dict | None = config.get('primary_button')
        self.declined_text: str = config.get('declined_text') or \
            'Verification was not successful. Please try again.'
        self.timeout_text: str = config.get('timeout_text') or \
            'Verification timed out. Please try again.'
        self.review_text: str = config.get('review_text') or \
            'Your verification needs manual review. Please contact the sender of your invitation.'
        self.state['phase'] = 'start'
        self._polling = False

    # ── flow ───────────────────────────────────────────────────────────

    async def _start(self) -> None:
        """Create a session and enter the 'awaiting' phase showing the QR."""
        assert self.tenant and self.steps
        vendor_data = f"{self.tenant}:{self.steps.context['invite_code']}:{self.step_id}"
        try:
            session = await create_session(self.tenant, vendor_data)
        except ValueError as e:
            logger.error(f"Didit session create failed: {e}")
            ui.notify(_('Could not start ID verification. Please try again later.'), type='negative')
            return
        session_id, url = session.get('session_id'), session.get('url')
        if not session_id or not url:
            logger.error(f"Didit session response missing id/url: {session}")
            ui.notify(_('Could not start ID verification. Please try again later.'), type='negative')
            return
        self.state.update(
            session_id=session_id,
            qr=qr_data_uri(url),
            link_html=f'<a href="{url}" target="_blank" class="step-secondary-hint step-hint">'
            f'{_("Open verification on this device")}</a>',
            awaiting_since=time.monotonic(),
            phase='awaiting',
        )

    async def _poll(self) -> None:
        """Timer tick: while awaiting, fetch the decision and act on a terminal status."""
        if self.state.get('phase') != 'awaiting' or self._polling:
            return
        session_id = self.state.get('session_id')
        if not session_id or not self.tenant:
            return
        since = self.state.get('awaiting_since') or 0
        if since and time.monotonic() - since > self.POLL_TIMEOUT:
            self.state.update(phase='declined', status_message=_(self.timeout_text))
            return

        self._polling = True
        try:
            decision = await get_decision(self.tenant, session_id)
        except ValueError as e:
            logger.warning(f"Didit poll failed (will retry): {e}")
            return
        finally:
            self._polling = False

        logger.info(f"Didit decision status={decision.get('status')!r} keys={list(decision)}")
        # logger.debug(f"Didit decision payload: {decision}")

        status = (decision.get('status') or '').lower()
        if status == 'approved':
            fields = extract_id_fields(decision)
            if not fields:
                feats = decision.get('features')
                logger.warning("Didit approved but extracted no ID fields — shape mismatch. "
                               f"top-level keys={list(decision)} "
                               f"features keys={list(feats) if isinstance(feats, dict) else None}")
            self.state['phase'] = 'done'  # stop polling; complete() flips to render_completed
            await self.complete(fields)
        elif status in ('declined', 'expired', 'abandoned', 'kyc expired'):
            self.state.update(phase='declined', status_message=_(self.declined_text))
        elif status == 'in review':
            self.state.update(phase='declined', status_message=_(self.review_text))
        # 'not started' / 'in progress' → keep polling

    # ── rendering ────────────────────────────────────────────────────────

    def render_enabled(self) -> None:
        with self.form_column():
            start = Col()
            start.element.bind_visibility_from(self.state, 'phase', value='start')
            with start:
                if self.primary_button:
                    Button(_(self.primary_button.get('label', '')),
                           on_click=self._start).classes('step-primary-button')
                    if self.primary_button.get('hint'):
                        ui.label(_(self.primary_button['hint'])).classes('step-primary-hint step-hint')

            awaiting = Col(style='align-items: center; gap: 0.75rem;')
            awaiting.element.bind_visibility_from(self.state, 'phase', value='awaiting')
            with awaiting:
                ui.label(_('Scan this QR code with your phone to start:')).classes('text')
                ui.image().bind_source_from(self.state, 'qr').classes('step-qr')
                ui.html().bind_content_from(self.state, 'link_html')
                with Row().classes('items-center'):
                    ui.spinner(size='sm')
                    ui.label(_("We'll continue automatically when you're done — keep this page open."))\
                        .classes('text')

            declined = Col()
            declined.element.bind_visibility_from(self.state, 'phase', value='declined')
            with declined:
                ui.label().bind_text_from(self.state, 'status_message').classes('text-error')
                Button(_('Try again'), on_click=self._start).classes('step-primary-button')

            ui.timer(self.POLL_INTERVAL, self._poll)

    def render_completed(self) -> None:
        ui.label(_(self.completed_text)).classes('text-success')
        expandable_info(self.state.get('outputs', {}))
