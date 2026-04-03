# /invitations page - shows all invitations with ViewStack (list → detail)
# Click row to view details, with Resend and Delete actions

from fastapi import Depends
from nicegui import ui, html

from ng_rdm.components import (
    Button, Column, Dialog, RowAction, TableConfig, FormConfig,
    ViewStack, ListTable, DetailCard,
    rdm_init, none_as_text,
)
from ng_rdm.components.fields import build_form_field
from domain.models import RoleAssignment
from ng_rdm.utils import logger
from services.auth.dependencies import require_invite_auth
from services.i18n import _
from services.postmark.postmark import send_postmark_invitation, test_template
from domain.invitation_flow import create_invitation, create_role_assignment
from domain.stores import (
    get_guest_store,
    get_role_store,
    get_role_assignment_store,
    get_invitation_store,
)
from services.theme import frame


def render_status(row: dict):
    """Render status as a colored chip using HTML/CSS."""
    status = row.get("status", "") or ""
    label = _(status)
    ui.html(f'<span class="status-chip status-chip-{status}">{label}</span>')


def get_invitations_table_config() -> TableConfig:
    return TableConfig(
        columns=[
            Column(name="calc_guest_name", label=_("Guest"), width_percent=22),
            Column(name="role_names", label=_("Roles"), width_percent=35),
            Column(name="invited_at", label=_("Invited"), width_percent=30, formatter=none_as_text),
            Column(name="status", label=_("Status"), width_percent=12, render=render_status),
        ],
        empty_message=_("No invitations found."),
        add_button=_("New invitation..."),
        toolbar_position="bottom",
    )


async def render_invitation_details(invitation: dict):
    """Render the detail view for an invitation."""
    guest_name = invitation.get('calc_guest_name') or invitation.get('guest_id', '')
    status = invitation.get('status', '')

    with ui.row().classes('rdm-detail-header'):
        ui.icon('mail', size='xl').classes('rdm-detail-icon')
        with ui.column().classes('rdm-detail-title-group'):
            ui.label(guest_name).classes('rdm-detail-title')
            ui.html(f'<span class="status-chip status-chip-{status}">{status}</span>')

    ui.separator()

    with ui.row().classes('rdm-detail-columns'):
        with ui.column().classes('rdm-detail-column'):
            ui.label(_('Invitation Details')).classes('rdm-detail-section-label')
            ui.label(f"{_('Email')}: {invitation.get('invitation_email', '-')}")
            ui.label(f"{_('Invited at')}: {none_as_text(invitation.get('invited_at', ''))}").classes('rdm-detail-text-sm')
            if invitation.get('code'):
                ui.label(f"{_('Code')}: {invitation.get('code')}").classes('rdm-detail-text-sm')

        with ui.column().classes('rdm-detail-column'):
            ui.label(_('Roles')).classes('rdm-detail-section-label')
            role_names = invitation.get('role_names', '')
            if role_names:
                for role in role_names.split(', '):
                    ui.label(f"• {role}")
            else:
                ui.label(_('No roles assigned')).classes('text-muted')

    if invitation.get('personal_message'):
        ui.separator()
        ui.label(_('Personal Message')).classes('rdm-detail-section-label')
        ui.label(invitation.get('personal_message', '')).classes('rdm-detail-text-sm')


# Form columns for invitation details (used in new invitation dialog)
INVITATION_COLUMNS = [
    Column(name="invitation_email", label=_("Invitation email"), placeholder=_("Email for this invitation")),
    Column(name="personal_message", label=_("Personal message"), ui_type=ui.textarea, placeholder=_("Optional")),
]


def _prepare_role_assignments(assignments: list[dict]) -> list[dict]:
    """Add display fields to role assignments."""
    for a in assignments:
        start = none_as_text(a.get("start_date", ""))
        end = none_as_text(a.get("end_date", ""))
        dates = f" ({start} → {end})"
        a["display_label"] = f"{a.get('role__name', 'Role')}{dates}"
    return assignments


async def new_invitation_dialog(tenant: str, roles: list[dict], on_created=None):
    """Single dialog for creating invitations: select guest, check roles, fill details."""
    guest_store = get_guest_store(tenant)
    role_assignment_store = get_role_assignment_store(tenant)

    guests = await guest_store.read_items()
    role_map = {r["id"]: r for r in roles}

    guest_options = {g['id']: g.get('display_name') or g['user_id'] for g in guests}

    state = {
        'guest_id': None,
        'guest': None,
        'role_assignments': [],
        'selected_ra_ids': set(),
        'invitation_email': '',
        'personal_message': '',
        'new_role_id': None,
    }

    async def load_guest_role_assignments():
        """Load role assignments for selected guest."""
        if not state['guest_id']:
            state['role_assignments'] = []
            return
        ras = await role_assignment_store.read_items(
            filter_by={"guest_id": state['guest_id']},
            join_fields=["role__name"]
        )
        state['role_assignments'] = _prepare_role_assignments(ras)

    async def on_guest_change(e):
        state['guest_id'] = e.value
        state['selected_ra_ids'] = set()
        state['new_role_id'] = None
        if e.value:
            state['guest'] = next((g for g in guests if g['id'] == e.value), None)
            if state['guest']:
                state['invitation_email'] = state['guest'].get('email', '')
        else:
            state['guest'] = None
            state['invitation_email'] = ''
        await load_guest_role_assignments()
        roles_section.refresh()  # type: ignore

    with Dialog() as dlg:
        async def add_role():
            """Add new role assignment for selected guest."""
            if not state['new_role_id'] or not state['guest_id']:
                dlg._notify(_("Select a guest and role first"), type="warning")
                return
            role = role_map.get(state['new_role_id'])
            if not role:
                return
            start_date, end_date = RoleAssignment.calculate_assignment_dates(role)
            try:
                new_ra = await create_role_assignment(
                    tenant, state['guest_id'], state['new_role_id'],
                    start_date, end_date
                )
                state['selected_ra_ids'].add(new_ra['id'])
                state['new_role_id'] = None
                dlg._notify(_("Role added"), type="positive")
                await load_guest_role_assignments()
                roles_section.refresh()  # type: ignore
            except Exception as e:
                dlg._notify(str(e), type="negative")

        async def handle_create():
            """Create invitation with selected role assignments."""
            if not state['guest_id']:
                dlg._notify(_("Please select a guest"), type="warning")
                return
            if not state['selected_ra_ids']:
                dlg._notify(_("Please select at least one role"), type="warning")
                return
            invitation_email = state['invitation_email'].strip()
            if not invitation_email:
                dlg._notify(_("Invitation email is required"), type="warning")
                return

            try:
                await create_invitation(
                    tenant,
                    guest_id=state['guest_id'],
                    role_assignment_ids=list(state['selected_ra_ids']),
                    invitation_email=invitation_email,
                    personal_message=state['personal_message'].strip(),
                )
                dlg._notify(_('Invitation created'), type='positive')
                dlg.close()
                if on_created:
                    on_created()
            except Exception as e:
                logger.error(f"Error creating invitation: {e}")
                dlg._notify(str(e), type='negative')

        ui.label(_("New Invitation")).classes('dialog-header')

        # Guest selection dropdown
        ui.select(
            options=guest_options, label=_("Select Guest"),
            on_change=on_guest_change,
            with_input=True, clearable=True,
        ).classes('form-input').props('popup-content-style="z-index: 6100"')

        # Role assignments section (refreshable)
        @ui.refreshable
        def roles_section():
            if not state['guest_id']:
                ui.label(_("Select a guest to see their role assignments")).classes('text-caption')
                return

            ui.label(_("Select roles to include")).classes('rdm-detail-section-label')

            ras = state['role_assignments']
            if ras:
                with ui.column().classes('q-gutter-sm'):
                    for ra in ras:
                        def make_toggle(ra_id):
                            def toggle(e):
                                if e.value:
                                    state['selected_ra_ids'].add(ra_id)
                                else:
                                    state['selected_ra_ids'].discard(ra_id)
                            return toggle

                        ui.checkbox(
                            ra.get('display_label', ''),
                            value=ra['id'] in state['selected_ra_ids'],
                            on_change=make_toggle(ra['id'])
                        )
            else:
                ui.label(_("No role assignments for this guest")).classes('text-caption')

            # Invitation details
            ui.separator()
            ui.label(_("Invitation details")).classes('rdm-detail-section-label')
            for col in INVITATION_COLUMNS:
                build_form_field(col, state)

        roles_section()

        # Actions
        with ui.row().classes('edit-card-actions'):
            ui.button(_("Create Invitation"), on_click=handle_create).classes('btn-primary')
            ui.button(_("Cancel"), on_click=dlg.close).classes('btn-secondary')

    dlg.open()


@ui.page('/{tenant}/m/invitations')
async def invitations_page(tenant: str = Depends(require_invite_auth)):
    logger.debug(f"invitations page accessed by tenant: {tenant}")
    rdm_init()

    ui_state = {"viewstack": {}, "list_table": {}, "detail_card": {}}

    invitation_store = get_invitation_store(tenant)
    role_store = get_role_store(tenant)
    roles = await role_store.read_items()

    async def send_email(invitation: dict):
        try:
            ui.notify(_('Sending email...'), type='info')
            success = await send_postmark_invitation(tenant=tenant, code=invitation.get('code'))
            if success:
                ui.notify(_('Email sent successfully!'), type='positive')
            else:
                ui.notify(_('Failed to send email'), type='negative')
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            ui.notify(f"{_('Error')}: {str(e)}", type='negative')

    async def run_test_template():
        await test_template(tenant=tenant)
        ui.notify(_('Template test written to /static'), type='positive')
        import time
        timestamp = int(time.time())
        ui.run_javascript(f"window.open('/static/test_output.html?t={timestamp}', '_blank', 'width=768,height=700')")

    custom_actions = [
        RowAction(icon="send", label=_("Resend"), callback=send_email),
        RowAction(label=_("Test Template"), callback=lambda _: run_test_template(), variant="secondary"),
    ]

    table_config = get_invitations_table_config()

    async def render_list(vs: ViewStack):
        def render_toolbar():
            Button(_('Accept invitation  ▶︎'),
                   on_click=lambda: ui.navigate.to(f'/{tenant}/accept'), variant="secondary")

        async def on_click(row_id):
            items = await invitation_store.read_items(filter_by={"id": row_id})
            if items:
                vs.show_detail(items[0])

        table = ListTable(
            state=ui_state['list_table'], data_source=invitation_store, config=table_config,
            on_click=on_click,
            on_add=lambda: new_invitation_dialog(tenant, roles, on_created=vs.build.refresh),
            render_toolbar=render_toolbar,
        )
        await table.build()

    async def render_detail(vs: ViewStack, item: dict):
        async def render_body(_: dict):
            with html.div().classes("rdm-detail-actions"):
                for action in custom_actions:
                    variant = action.variant or "primary"
                    with html.button().classes(f"rdm-btn rdm-btn-{variant}").on(
                        "click", lambda _, i=item, a=action: a.callback(i) if a.callback else None
                    ):
                        if action.icon:
                            html.i().classes(f"bi bi-{action.icon}")
                        if action.label:
                            html.span(action.label)

        detail = DetailCard(
            state=ui_state["detail_card"],
            data_source=invitation_store,
            render_summary=render_invitation_details,
            render_related=render_body,
            show_edit=False,
            on_deleted=vs.show_list,
        )
        detail.set_item(item)
        await detail.build()

    async def render_edit(vs: ViewStack, item: dict | None):
        pass  # invitations are not editable

    stack = ViewStack(
        state=ui_state['viewstack'],
        render_list=render_list,
        render_detail=render_detail,
        render_edit=render_edit,
    )

    with frame('invitations', tenant):
        await stack.build()
