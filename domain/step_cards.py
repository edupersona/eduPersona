"""Step card components for the onboarding flow"""
from nicegui import app, ui

from ng_rdm.components import Col, Row, Button
from ng_rdm.utils import logger
from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login
from services.auth.guest_auth import establish_guest_session_for_code
from domain.invitations import accept_invitation
from domain.models import GuestAttribute
from domain.stores import get_invitation_store, get_guest_store, get_role_store

def expandable_info(valdict: dict) -> None:
    if valdict:
        with ui.expansion(_('View attributes'), icon='info').style('margin-top: 0.5rem;'):
            with Col(style='gap: 0.25rem;'):
                for key, value in valdict.items():
                    if value:
                        ui.label(f'{key}: {value}').style('font-size: 0.875rem;')


userinfo_mapping = {
    'identity': ['name', 'given_name', 'family_name', 'eduperson_principal_name', 'sub', 'uids'],
    'email': ['email', 'email_verified'],
    'affiliation': ['schac_home_organization', 'eduperson_affiliation'],
    'authentication': ['acr']
}

async def update_guest_from_userinfo(tenant: str, invite_code: str, userinfo: dict, idp: str) -> None:
    """Replace this guest's GuestAttribute row for `idp` with the new userinfo.

    Args:
        tenant: Tenant identifier
        invite_code: Invitation code (32-char hex string)
        userinfo: OIDC userinfo dict
        idp: IdP identifier from settings.oidc (e.g., "eduid", "institutional")
    """
    import json

    invitation_store = get_invitation_store(tenant)

    invitations = await invitation_store.read_items(filter_by={"code": invite_code})
    if not invitations:
        logger.warning(f"update_guest_from_userinfo: invitation not found for code: {invite_code}")
        return

    guest_id = invitations[0]["guest_id"]

    # Replace any prior attributes from this IdP (re-acceptance must not accumulate)
    await GuestAttribute.filter(guest_id=guest_id, name=idp).delete()
    await GuestAttribute.create(guest_id=guest_id, name=idp, value=json.dumps(userinfo))

    # # eduID is the authoritative source for the guest's display name
    # guest_store = get_guest_store(tenant)
    # if idp == "eduid":
    #     guest_updates = {}
    #     if userinfo.get('given_name'):
    #         guest_updates["given_name"] = userinfo['given_name']
    #     if userinfo.get('family_name'):
    #         guest_updates["family_name"] = userinfo['family_name']
    #     # if userinfo.get('email'):
    #     #     guest_updates["email"] = userinfo['email']
    #
    #     if guest_updates:
    #         await guest_store.update_item(guest_id, guest_updates)


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
        self.tenant = None  # Will be set by Steps container
        self.info = {}

    async def click_handler(self):
        """Override in subclasses to handle click actions (for button and icon)"""
        pass

    def render(self, state: dict, is_enabled: bool, step_number: int) -> None:
        """Render the step card UI components"""
        is_completed = self.is_completed(state)
        status_color = 'positive' if is_completed else 'grey'
        status_icon = 'check_circle' if is_completed else 'radio_button_unchecked'

        with ui.card().classes('step-card'):
            with Row().classes('step-card-row'):
                icon = ui.icon(status_icon, color=status_color).classes('step-icon')

                # Make icon clickable if enabled
                if is_enabled and not is_completed:
                    icon.on('click', self.click_handler)

                with Col(classes='step-content'):
                    ui.label(self.title).classes('step-title')
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
        ui.label(self.completed_text).classes('text-success').style('margin-top: 0.5rem;')

    def render_disabled(self, state: dict) -> None:
        """Override in subclasses to customize disabled content"""
        ui.label(self.disabled_text).classes('text-muted').style('margin-top: 0.5rem;')

    def is_completed(self, state: dict) -> bool:
        """Check if this step is completed"""
        return state['steps_completed'].get(self.completed_key, False)

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """Override in subclasses to handle OIDC completion results"""
        pass


# Step Subclasses
class VerifyInviteStep(StepCard):
    """Step 1: Verify invitation code"""

    async def click_handler(self):
        """Submit invitation code"""
        from routes.accept import process_invite_code

        invite_code_value = self.state.get('invite_code_input', '')
        if self.tenant and invite_code_value:
            await process_invite_code(self.tenant, self.state, invite_code_value)
            # Use the steps reference to trigger refresh
            if self.steps:
                self.steps.render.refresh()

    def render_enabled(self, state: dict) -> None:
        ui.input(
            _('Enter your invitation code here'),
            placeholder=_('Invitation code')
        ).classes('form-input').bind_value(self.state, 'invite_code_input')

        Button(_('Confirm code'), on_click=self.click_handler).style('margin-top: 0.5rem;')


class VerifyEduIDStep(StepCard):
    """Step 2: Verify eduID login"""

    idp = "eduid"

    async def click_handler(self):
        """Initiate eduID login flow"""
        if not self.tenant:
            logger.error("Tenant not set in step card")
            return
        await start_oidc_login(
            tenant=self.tenant,
            idp="eduid",
            callback_handler=self.result_handler,
            next_url=f"/{self.tenant}/accept",
            force_login=True
        )

    def create_eduid_handler(self):
        ui.navigate.to('https://test.eduid.nl/home', new_tab=True)

    def render_enabled(self, state: dict) -> None:
        with Row().classes('button-row'):
            with Col():
                Button(
                    _('YES! I already have a (test!) eduID'),
                    on_click=self.click_handler
                ).style('margin-right: 1rem;')

            with Col(style='align-items: center; gap: 8px;'):
                Button(
                    _("No - I don't have a (test!) eduID yet"),
                    on_click=self.create_eduid_handler
                )
                ui.label(_("Come back here after you've created it!")).style('font-size: 0.95rem;')

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success').style('margin-top: 0.5rem;')
        expandable_info(state.get('eduid_userinfo', {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """Handle eduID OIDC completion"""
        logger.debug(f"eduID login completed with userinfo: {userinfo}")
        # Get invite code directly from state
        invite_code = self.state.get('invite_code')

        # Update state
        self.state['eduid_userinfo'] = userinfo
        self.state['steps_completed']['eduid login'] = True

        # Update storage
        if invite_code and self.tenant:
            await update_guest_from_userinfo(self.tenant, invite_code, userinfo, self.idp)


class VerifyInstitutionalStep(StepCard):
    """Step 3: Verify institutional account"""

    idp = "institutional"

    async def click_handler(self):
        """Initiate institutional login flow"""
        if not self.tenant:
            logger.error("Tenant not set in step card")
            return
        await start_oidc_login(
            tenant=self.tenant,
            idp="institutional",
            callback_handler=self.result_handler,
            next_url=f"/{self.tenant}/accept",
            force_login=True
        )

    def render_enabled(self, state: dict) -> None:
        ui.label(_('Log in via test-IDP to verify your institutional identity.')).classes('text-muted')
        ui.label('Demo van willekeurige test-IDP als secundaire verificatie. Kies bijvoorbeeld voor "professor5/professor5"').classes(
            'text-muted')
        with Row().classes('button-row'):
            Button(
                _('Login via (dummy) institution'),
                on_click=self.click_handler
            )

    def render_completed(self, state: dict) -> None:
        ui.label(self.completed_text).classes('text-success').style('margin-top: 0.5rem;')
        expandable_info(state.get('secondary_userinfo', {}))

    async def result_handler(self, userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        """Handle institutional OIDC completion"""
        logger.debug(f"Institutional login completed with userinfo: {userinfo}")
        invite_code = self.state.get('invite_code')

        if invite_code:
            self.state['steps_completed']['login instelling'] = True
            self.state['steps_completed']['completed'] = True
            self.state['secondary_userinfo'] = userinfo

            if not self.tenant:
                logger.error("Tenant not set in step card")
                return

            await update_guest_from_userinfo(self.tenant, invite_code, userinfo, self.idp)

            # Accept invitation and provision to SCIM (also promotes eduid_pseudonym)
            accepted = await accept_invitation(self.tenant, invite_code)
            if not accepted:
                logger.error(f"Failed to accept invitation: {invite_code}")
            else:
                # Log the guest in so the final-step link to /apps works without re-auth
                await establish_guest_session_for_code(self.tenant, invite_code)

            # Redirect URL/text already set in state from process_invite_code


class LinkApplicationStep(StepCard):
    """Step 4: Link to the application"""

    def render_completed(self, state: dict) -> None:
        # note: no render_enabled at the moment:
        # because self.state['steps_completed']['completed'] is already set in card 3

        ui.label(_('✓ Your eduID is now linked!')).classes('text-success')

        # Show links to each assigned role's application
        role_assignments = state.get('role_assignments', [])
        for ra in role_assignments:
            role = ra.get('role', {})
            redirect_url = role.get('redirect_url', '')
            redirect_text = role.get('redirect_text', '')
            if redirect_url and redirect_text:
                ui.link(
                    _('Click here to log in to {app}', app=redirect_text),
                    redirect_url,
                    new_tab=True
                ).classes('btn-primary') \
                    .style('padding: 0.5rem 1rem; border-radius: 0.25rem; font-size: 14pt; color:white; font-weight: 500; text-decoration: none; display: inline-block; margin-top: 0.5rem;')

        # Direct link to the guest's services overview — session was established at accept time
        if self.tenant:
            ui.link(
                _('Go to my services overview'),
                f'/{self.tenant}/apps',
            ).style('margin-top: 1rem; display: inline-block;')


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

    def __init__(self, tenant: str, state: dict, tenant_config: dict):
        self.tenant = tenant
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
            step_instance.tenant = self.tenant  # Store tenant reference on step card
            steps.append(step_instance)
        return steps

    @ui.refreshable
    def render(self) -> None:
        """Render all step cards"""
        state = app.storage.tab
        suffix = ''
        if state['role_name']:
            suffix = ' ' + _('as') + ' ' + state['role_name']

        ui.label(_('Welcome{suffix}', suffix=suffix)).classes('page-title')
        ui.label(
            _('Follow the step-by-step plan below to accept your invitation{suffix}.', suffix=suffix)).classes('page-subtitle')

        for i, step in enumerate(self.step_instances):
            # Check if prerequisites (all previous steps) are met
            is_enabled = all(
                self.step_instances[j].is_completed(self.state)
                for j in range(i)
            )
            step.render(self.state, is_enabled, i + 1)
