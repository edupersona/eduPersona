"""Step card components for the onboarding flow"""
from nicegui import app, ui

from services.logging import logger
from services.oidc_mt.multitenant import start_oidc_login
from services.storage import assign_group, find_one, update


def update_guest_from_userinfo(invite_code: str, userinfo: dict, step_key: str) -> None:
    """Store OIDC userinfo in guest.attributes[step_key] without overwriting primary attributes"""
    membership = find_one("memberships", membership_id=invite_code)
    if membership:
        # Get current guest to preserve existing attributes
        guest = find_one("guests", guest_id=membership["guest_id"])
        current_attributes = guest.get("attributes", {}) if guest else {}

        # Store complete userinfo under step-specific key
        current_attributes[step_key] = userinfo

        # Update only attributes field
        update("guests", membership["guest_id"], attributes=current_attributes)

def expandable_info(valdict: dict) -> None:
    if valdict:
        with ui.expansion('Bekijk attributen', icon='info').classes('mt-2'):
            with ui.column().classes('gap-1'):
                for key, value in valdict.items():
                    if value:
                        ui.label(f'{key}: {value}').classes('text-sm')

# Base Step Card Class
class StepCard:
    """Base class for all step cards in the onboarding flow"""

    def __init__(self, config: dict):
        self.title = config['title']
        self.completed_text = config['completed_text']
        self.disabled_text = config.get('disabled_text', '')
        self.completed_key = config['completed_key']
        self.steps = None  # Will be set by Steps container
        self.state = {}  # Will be set by Steps container
        self.info = {}

    def render(self, state: dict, is_enabled: bool, step_number: int) -> None:
        """Render the step card UI components"""
        is_completed = self.is_completed(state)
        status_color = 'positive' if is_completed else 'grey'
        status_icon = 'check_circle' if is_completed else 'radio_button_unchecked'

        with ui.card().classes('w-full mb-4'):
            with ui.row().classes('items-center w-full'):
                ui.icon(status_icon, color=status_color).classes('text-2xl mr-4')
                with ui.column().classes('flex-grow'):
                    ui.label(self.title).classes('text-lg font-semibold')
                    if is_completed:
                        self.render_completed(state)
                    elif is_enabled:
                        self.render_enabled(state)
                    else:
                        self.render_disabled(state)

    def render_enabled(self, state: dict) -> None:
        """Implement in subclasses for step-specific content"""
        raise NotImplementedError

    def render_completed(self, state: dict) -> None:
        """Override in subclasses to customize completed_content"""
        ui.label(self.completed_text).classes('text-green-600 mt-2')

    def render_disabled(self, state: dict) -> None:
        """Override in subclasses to customize disabled content"""
        ui.label(self.disabled_text).classes('text-gray-500 mt-2')

    def is_completed(self, state: dict) -> bool:
        """Check if this step is completed"""
        return state['steps_completed'].get(self.completed_key, False)

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """Override in subclasses to handle OIDC completion results"""
        pass


# Step Subclasses
class VerifyInviteStep(StepCard):
    """Step 1: Verify invitation code"""

    def render_enabled(self, state: dict) -> None:
        from routes.accept import process_invite_code

        invite_code_input = ui.input(
            'Voer hier uw uitnodigingscode in',
            placeholder='Uitnodigingscode'
        ).classes('w-full')

        def handle_code_submit():
            process_invite_code(state, invite_code_input.value)
            # Use the steps reference to trigger refresh
            if self.steps:
                self.steps.render.refresh()

        ui.button('Code bevestigen', on_click=handle_code_submit).classes('mt-2')


class VerifyEduIDStep(StepCard):
    """Step 2: Verify eduID login"""

    def render_enabled(self, state: dict) -> None:
        async def handle_eduid_login():
            await start_oidc_login(
                tenant="uva",
                idp="eduid",
                callback_handler=self.result_handler,
                force_login=True
            )

        ui.button(
            'Inloggen met (test!) eduID',
            on_click=handle_eduid_login
        ).classes('mr-4')

        with ui.row().classes('items-center mt-2'):
            ui.label('Nog geen test-eduID?').classes('text-sm')
            ui.link('Maak hem hier aan', 'https://test.eduid.nl/home', new_tab=True).classes('text-sm ml-1')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-green-600 mt-2')
        expandable_info(state.get('eduid_userinfo', {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """Handle eduID OIDC completion"""
        logger.debug(f"eduID login completed with userinfo: {userinfo}")
        # Get invite code directly from state
        invite_code = self.state.get('invite_code')

        # Update state
        self.state['eduid_userinfo'] = userinfo
        self.state['steps_completed']['eduid_login'] = True

        # Update storage
        if invite_code:
            # Store userinfo under step-specific key
            update_guest_from_userinfo(invite_code, userinfo, self.completed_key)

            # Update primary guest attributes from eduID data (authoritative source)
            membership = find_one("memberships", membership_id=invite_code)
            if membership:
                guest_updates = {
                    "upn": userinfo.get('eduperson_principal_name', ''),
                    "name": userinfo.get('name', ''),
                    "given_name": userinfo.get('given_name', ''),
                    "family_name": userinfo.get('family_name', ''),
                    "emails": [userinfo['email']] if userinfo.get('email') else []
                }
                update("guests", membership["guest_id"], **guest_updates)


class VerifyInstitutionalStep(StepCard):
    """Step 3: Verify institutional account"""

    def render_enabled(self, state: dict) -> None:
        async def handle_institutional_login():
            await start_oidc_login(
                tenant="uva",
                idp="institutional",
                callback_handler=self.result_handler,
                force_login=True
            )

        ui.label('Log in via test-IDP om uw instellingsidentiteit te verifiëren.').classes('text-gray-600 mb-2')
        ui.button(
            'Inloggen via (dummy) instelling',
            on_click=handle_institutional_login
        ).classes('bg-blue-500 text-white')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-green-600 mt-2')
        expandable_info(state.get('secondary_userinfo', {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """Handle institutional OIDC completion"""
        logger.debug(f"Institutional login completed with userinfo: {userinfo}")
        # Get invite code directly from state
        invite_code = self.state.get('invite_code')

        if invite_code:
            # Update state
            self.state['steps_completed']['mfa_verified'] = True
            self.state['steps_completed']['completed'] = True

            # Store institutional userinfo under step-specific key (no primary attribute updates)
            self.state['secondary_userinfo'] = userinfo
            update_guest_from_userinfo(invite_code, userinfo, self.completed_key)

            # Accept membership and provision to SCIM
            membership = find_one("memberships", membership_id=self.state['invite_code'])
            if membership:
                assign_group(membership['guest_id'], membership['group_id'])


class LinkApplicationStep(StepCard):
    """Step 4: Link to the application"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.link_url = config.get('default_link_url', '')
        self.link_text = config.get('default_link_text', '')

    def render_enabled(self, state: dict) -> None:
        # Show success message and link
        ui.label('✓ Uw eduID is nu gekoppeld!').classes('text-green-600 mb-2')

        # Use dynamic values from state if available, otherwise use config defaults
        redirect_url = state.get('redirect_url', self.link_url)
        redirect_text = state.get('redirect_text', self.link_text)

        ui.link(
            f'Klik hier om in te loggen op {redirect_text}',
            redirect_url,
            new_tab=True
        ).classes('bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600')


# Step Card Class Registry
STEP_CARD_CLASSES = {
    'VerifyInviteStep': VerifyInviteStep,
    'VerifyEduIDStep': VerifyEduIDStep,
    'VerifyInstitutionalStep': VerifyInstitutionalStep,
    'LinkApplicationStep': LinkApplicationStep
}


# Steps Collection Class
class Steps:
    """Collection of step cards for the onboarding flow"""

    def __init__(self, state: dict, tenant_config: dict):
        self.state = state
        self.tenant_config = tenant_config
        self.step_instances = self._create_steps()

    def _create_steps(self) -> list[StepCard]:
        """Create step instances based on tenant config"""
        steps = []
        for step_config in self.tenant_config['steps']:
            step_class_name = step_config['class']
            if step_class_name not in STEP_CARD_CLASSES:
                raise ValueError(f"Unknown step card class: {step_class_name}")
            step_class = STEP_CARD_CLASSES[step_class_name]
            step_instance = step_class(step_config['config'])
            step_instance.steps = self  # Add reference to parent Steps container
            step_instance.state = self.state  # Store state reference on step card
            steps.append(step_instance)
        return steps

    @ui.refreshable
    def render(self) -> None:
        """Render all step cards"""
        for i, step in enumerate(self.step_instances):
            # Check if prerequisites (all previous steps) are met
            is_enabled = all(
                self.step_instances[j].is_completed(self.state)
                for j in range(i)
            )
            step.render(self.state, is_enabled, i + 1)
