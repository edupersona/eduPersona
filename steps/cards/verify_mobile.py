"""Mobile-number verification step: a self-contained code exchange inside one card."""
import re
import secrets

from nicegui import ui

from ng_rdm.components import Col, Row, Button

from services.i18n import _

from steps.base import StepCard, expandable_info


class VerifyMobileStep(StepCard):
    """Verify a mobile number by a self-contained code exchange, all inside one step.

    The card is a free-form reactive canvas: an "enter number" section and an "enter
    code" section, toggled by the `state['code_sent']` flag via bind_visibility. Pressing
    "Send code" generates a one-time code and surfaces it via ui.notify (no real SMS);
    entering it back records completion. The code is ephemeral (in-memory, single-session);
    is_already_done stays default False. Writes its payload to state['outputs'][step_id]."""

    CODE_LENGTH = 4  # code constant, not config

    def __init__(self, config: dict):
        super().__init__(config)
        self.mobile_label: str = config.get('mobile_label', 'Mobile number')
        self.code_label: str = config.get('code_label', 'Verification code')
        self.send_button_label: str = config.get('send_button_label', 'Send code')
        self.verify_button_label: str = config.get('verify_button_label', 'Verify')
        self.resend_label: str = config.get('resend_label', 'Change number / resend')
        self.phone_pattern: str = config.get('phone_pattern', r'^\+?[0-9\s\-]{7,15}$')
        self._reset()

    def _number_valid(self, value: str) -> bool:
        return bool(re.match(self.phone_pattern, (value or '').strip()))

    def _send_code(self) -> None:
        if not self._number_valid(self.state.get('mobile_number') or ''):
            ui.notify(_('Enter a valid mobile number'), type='negative')
            return
        self._code = ''.join(secrets.choice('0123456789') for _i in range(self.CODE_LENGTH))
        self.state['mobile_code'] = ''
        ui.notify(_('Enter code: {code}', code=self._code))  # no real SMS
        self.state['code_sent'] = True

    def _reset(self) -> None:
        self._code = None
        self.state['code_sent'] = False

    async def _verify(self) -> None:
        if not self._code or (self.state.get('mobile_code') or '').strip() != self._code:
            ui.notify(_('Incorrect code — please try again.'), type='negative')
            return
        await self.complete({'mobile': (self.state.get('mobile_number') or '').strip()})

    def render_enabled(self, state: dict) -> None:
        with self.form_column():
            number_box = Col(style='gap: 0.75rem;')
            number_box.element.bind_visibility_from(self.state, 'code_sent', value=False)
            with number_box:
                ui.input(
                    label=_(self.mobile_label),
                    placeholder='+31612345678',
                    validation={_('Enter a valid mobile number'): lambda v: self._number_valid(v)},
                ).bind_value(self.state, 'mobile_number') \
                 .props('type=tel inputmode=tel').classes('form-input')
                Button(_(self.send_button_label), on_click=self._send_code).classes('step-primary-button')
            code_box = Col(style='gap: 0.75rem;')
            code_box.element.bind_visibility_from(self.state, 'code_sent')
            with code_box:
                ui.input(
                    label=_(self.code_label),
                    placeholder='1234',
                    validation={_('Four digits required'): lambda v: bool(re.fullmatch(r'\d{4}', v or ''))},
                ).bind_value(self.state, 'mobile_code') \
                 .props('type=text inputmode=numeric maxlength=4').classes('form-input')
                with Row().classes('button-row'):
                    Button(_(self.verify_button_label), on_click=self._verify)
                    Button(_(self.resend_label), on_click=self._reset)

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success')
        out = state.get('outputs', {}).get(self.step_id, {})
        if out.get('mobile'):
            expandable_info({_(self.mobile_label): out['mobile']})
