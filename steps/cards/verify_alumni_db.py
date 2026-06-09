"""Alumni-database verification step (simulated two-field lookup)."""
import re

from ng_rdm.components import Button
from nicegui import ui

from services.i18n import _
from steps.base import StepCard, expandable_info

# voor demo-doeleinden: iedereen die tussen 1960 en 1990 is geboren en een zescijferig nummer invoert
# geldt als "herkende alumnus" -> in de outputs['alumni_db'] komt dan de "opgezochte" alumnus_id van "A203920" te staan
#
MIN_DOB_YEAR = 1960
MAX_DOB_YEAR = 1990
STUDENT_NR_PATTERN = r'^\d{6}$'  # zes cijfers
DUMMY_ALUMNUS_ID = 'A203920'

class VerifyAlumniDb(StepCard):
    """Verify alumni status against a (simulated) records lookup using date of birth and student number."""

    def __init__(self, config: dict):
        super().__init__(config)
        # Exclusive year bounds (year-of-birth must be strictly between min and max).

    def _dob_year(self, value: str) -> int | None:
        try:
            return int((value or '').split('-')[0])
        except ValueError:
            return None

    def _student_number_valid(self, value: str) -> bool:
        return bool(re.match(STUDENT_NR_PATTERN, value or ''))

    async def _verify(self) -> None:
        dob = (self.state.get('alumni_dob') or '').strip()
        student_number = (self.state.get('alumni_student_number') or '').strip()
        year = self._dob_year(dob)
        if (
            year is None
            or not (MIN_DOB_YEAR < year < MAX_DOB_YEAR)
            or not self._student_number_valid(student_number)
        ):
            await self.fail(
                'alumni lookup failed',
                notify='Geen alumnus gevonden — kloppen jouw gegevens? Probeer het nog eens.',
            )
            return
        # registreer de gevonden alumnus_id, bij afronding onboarding wordt dit gekoppeld aan de guest_id
        await self.complete({'alumnus_id': DUMMY_ALUMNUS_ID})

    def render_enabled(self, state: dict) -> None:
        with self.form_column():
            ui.input(label='geboortedatum', placeholder='YYYY-MM-DD') \
                .bind_value(self.state, 'alumni_dob').props('type=date').classes('form-input')
            ui.input(
                label='studentnummer',
                placeholder='123456',
                validation={
                    'studentnummer moet uit exact zes cijfers bestaan': lambda v: self._student_number_valid(v),
                },
            ).bind_value(self.state, 'alumni_student_number') \
             .props('type=text inputmode=numeric maxlength=6').classes('form-input')
            Button('Verifiëren', on_click=self._verify).classes('step-primary-button')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success')
        out = state.get('outputs', {}).get(self.step_id, {})
        if out:
            expandable_info({
                'alumnus_id': out.get('alumnus_id', ''),
            })
