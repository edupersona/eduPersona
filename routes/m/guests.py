# /guests page

import json

from fastapi import Depends
from nicegui import ui

from ng_rdm.components import (
    ActionButtonTable, Column, Dialog, TableConfig, FormConfig,
    ViewStack, EditCard, DetailCard, ListTable, none_as_text,
    Col, Row, Separator,
)
from ng_rdm.components.fields import build_form_field
from ng_rdm.utils import logger
from services.auth.dependencies import require_guests_auth
from services.i18n import _
from services.tenant import get_tenant_from_session
from domain.stores import (
    get_guest_store, get_guest_attribute_store, get_role_assignment_store, get_role_store,
)
from domain.assignments import create_role_assignment, update_role_assignment
from domain.guests import delete_guest
from services.theme import frame


def render_guest_statuses(row: dict):
    """Render guest statuses as colored chips."""
    statuses = row.get("guest_statuses", []) or []
    chips = ' '.join(
        f'<span class="status-chip status-chip-{s}">{s.replace("_", " ")}</span>'
        for s in statuses
    )
    ui.html(chips, sanitize=False)


def get_guests_table_config() -> TableConfig:
    return TableConfig(
        columns=[
            Column(name="display_name", label=_("Name"), width_percent=25),
            Column(name="email", label=_("Email"), width_percent=28),
            # Column(name="assignment_count", label=_("Roles"), width_percent=8),
            Column(name="max_end_date", label=_("End date"), width_percent=14, formatter=none_as_text),
            Column(name="guest_statuses", label=_("Status"), width_percent=26, render=render_guest_statuses),
        ],
        empty_message=_("No guests found"),
        add_button=_("New Guest..."),
        toolbar_position="bottom",
    )


def get_guests_form_config() -> FormConfig:
    return FormConfig(
        columns=[
            Column(name="email", label=_("Email address"),
                   placeholder=_("The mail address to send the invitation to")),
            Column(name="user_id", label=_("User ID"),
                   placeholder=_("User identifier in our systems")),
            Column(name="given_name", label=_("Given name"),
                   placeholder=_(" ")),
            Column(name="family_name", label=_("Family name"),
                   placeholder=_(" ")),
        ],
        title_add=_("New Guest"),
        title_edit=_("Edit Guest"),
    )


async def render_guest_details(guest: dict):
    statuses = guest.get('guest_statuses', []) or []
    chips = ' '.join(
        f'<span class="status-chip status-chip-{s}">{_(s.replace("_", " "))}</span>'
        for s in statuses
    )
    with Row(classes='rdm-detail-header'):
        ui.icon('person', size='xl').classes('rdm-detail-icon')
        with Col(classes='rdm-detail-title-group'):
            with Row(classes='rdm-items-center gap-2'):
                ui.label(guest.get('display_name') or guest.get('user_id', '')).classes('rdm-detail-title')
                ui.html(chips, sanitize=False)
            ui.label(guest['email']).classes('rdm-detail-subtitle')

    Separator()

    with Row(classes='rdm-detail-columns', gap='4rem'):
        with Col(classes='rdm-detail-column'):
            ui.label(_('Name')).classes('rdm-detail-section-label')
            if guest.get('given_name'):
                ui.label(f"{_('Given name')}: {guest['given_name']}").classes('rdm-detail-text-sm')
            if guest.get('family_name'):
                ui.label(f"{_('Family name')}: {guest['family_name']}").classes('rdm-detail-text-sm')

            # if len(emails) > 1:
            #     ui.label(f"{_('Emails')}: {', '.join(emails)}").classes('rdm-detail-text-sm')

        with Col(classes='rdm-detail-column'):
            ui.label(_('Identity')).classes('rdm-detail-section-label')
            ui.label(f"user_id: {guest.get('user_id', '-')}").classes('rdm-detail-text-sm')
            eduid_p = guest.get('eduid_pseudonym')
            if eduid_p:
                ui.label(f"eduid: {eduid_p}").classes('rdm-detail-text-sm')
            scim_id = guest.get('scim_id')
            if scim_id:
                ui.label(f"scim_id: {scim_id}").classes('rdm-detail-text-sm')

        with Col(classes='rdm-detail-column'):
            ui.label(_('Role Assignments')).classes('rdm-detail-section-label')
            count = guest.get('assignment_count', 0)
            ui.label(f"{count} {_('active role(s)')}").classes('rdm-detail-text-sm')
            ui.label(f"{_('Latest end date')}: {none_as_text(guest.get('max_end_date', ''))}").classes('rdm-detail-text-sm')

    # Guest attributes (from OIDC flows)
    guest_id = guest.get('id')
    if guest_id:
        attr_store = get_guest_attribute_store(guest.get('tenant', ''))
        attrs = await attr_store.read_items(filter_by={"guest_id": guest_id})
        if attrs:
            Separator()

            with ui.expansion(_('Attributes')).props('switch-toggle-side').classes('rdm-detail-section-label'):
                with Row(classes='attr-row'):
                    for attr in attrs:
                        with Col(classes='attr-card'):
                            ui.label(attr['name']).classes('attr-name')
                            try:
                                data = json.loads(attr['value'])
                                if isinstance(data, dict):
                                    for key, value in data.items():
                                        _render_attribute_value(key, value)
                                else:
                                    ui.label(str(data)).classes('attr-value')
                            except (json.JSONDecodeError, TypeError):
                                ui.label(str(attr['value'])).classes('attr-value')


def _render_attribute_value(key: str, value):
    """Helper to render a single attribute key-value pair with truncation + tooltip."""
    MAX_LENGTH = 60

    with Row(classes='attr-kv-row'):
        ui.label(f"{key}:").classes('attr-key')

        if isinstance(value, bool):
            ui.label('✓' if value else '✗').classes('attr-bool')
            return
        elif value is None:
            ui.label('null').classes('attr-null')
            return
        elif isinstance(value, list):
            value_str = ', '.join(str(v) for v in value) if value else '[]'
        elif isinstance(value, (str, int, float)):
            value_str = str(value)
        else:
            value_str = json.dumps(value)

        if len(key) + len(value_str) > MAX_LENGTH:
            remaining = MAX_LENGTH - len(key)
            truncated = value_str[:max(1, remaining)] + '...'
            with Row(classes='attr-kv-row'):
                ui.label(truncated).classes('attr-value')
                ui.icon('add_circle_outline', size='xs').classes('attr-expand-icon').tooltip(value_str)
        else:
            ui.label(value_str).classes('attr-value')


def _go_to_role(row: dict):
    """Navigate to role detail page."""
    tenant = get_tenant_from_session()
    if tenant and (role_id := row.get("role_id")):
        ui.navigate.to(f'/{tenant}/m/roles?id={role_id}')


def get_role_assignment_config() -> TableConfig:
    return TableConfig(
        columns=[
            Column(name="role__name", label=_("Role"), width_percent=37, on_click=_go_to_role),
            Column(name="role__redirect_text", label=_("App"), width_percent=20),
            Column(name="start_date", label=_("Start"), width_percent=12, formatter=none_as_text),
            Column(name="end_date", label=_("End"), width_percent=12, formatter=none_as_text),
        ],
        empty_message=_("No role assignments"),
        show_add_button=True,
        add_button=_("Assign Role..."),
        show_edit_button=True,
        show_delete_button=True,
        toolbar_position="bottom",
    )


ASSIGN_ROLE_COLUMNS = [
    Column(name="start_date", label=_("Start date"), placeholder=_("YYYY-MM-DD (optional)")),
    Column(name="end_date", label=_("End date"), placeholder=_("YYYY-MM-DD (optional)")),
]


async def _assign_role_dialog(tenant: str, guest: dict, table):
    """Dialog to assign a new role to guest."""
    role_store = get_role_store(tenant)
    role_assignment_store = get_role_assignment_store(tenant)

    roles = await role_store.read_items()
    existing = await role_assignment_store.read_items(filter_by={"guest_id": guest["id"]})
    existing_role_ids = {a["role_id"] for a in existing}
    available_roles = [r for r in roles if r["id"] not in existing_role_ids]

    if not available_roles:
        ui.notify(_("All roles already assigned"), type="info")
        return

    role_options = {r["id"]: r["name"] for r in available_roles}
    state = {"role_id": None, "start_date": "", "end_date": ""}

    async def handle_assign():
        if not state["role_id"]:
            ui.notify(_("Please select a role"), type="warning")
            return
        try:
            await create_role_assignment(
                tenant, guest["id"], state["role_id"],
                state["start_date"], state["end_date"]
            )
            dlg._notify(_("Role assigned"), type="positive")
            dlg.close()
        except Exception as e:
            dlg._notify(str(e), type="negative")

    with Dialog() as dlg:
        ui.label(_("Assign Role to {name}", name=guest.get("display_name")
                 or guest.get("user_id", ""))).classes('dialog-header')
        ui.select(
            options=role_options, label=_("Select Role"),
        ).bind_value(state, "role_id").classes('form-input').props('popup-content-style="z-index: 6100"')
        for col in ASSIGN_ROLE_COLUMNS:
            build_form_field(col, state)
        with Row(classes='edit-card-actions'):
            ui.button(_("Assign"), on_click=handle_assign).classes('btn-primary')
            ui.button(_("Cancel"), on_click=dlg.close).classes('btn-secondary')
    dlg.open()


async def _edit_assignment_dialog(tenant: str, row: dict):
    """Dialog to edit start/end dates of a role assignment."""
    state = {
        "start_date": row.get("start_date") or "",
        "end_date": row.get("end_date") or "",
    }

    with Dialog() as dlg:
        async def handle_save():
            try:
                await update_role_assignment(
                    tenant, row["id"],
                    state["start_date"], state["end_date"]
                )
                dlg._notify(_("Updated"), type="positive")
                dlg.close()
            except Exception as e:
                dlg._notify(str(e), type="negative")

        role_name = row.get("role__name", "")
        ui.label(_("Edit dates for {role}", role=role_name)).classes('dialog-header')
        ui.input(label=_("Start date"), placeholder=_("YYYY-MM-DD")).bind_value(state, "start_date") \
            .classes('form-input').props('type=date')
        ui.input(label=_("End date"), placeholder=_("YYYY-MM-DD")).bind_value(state, "end_date") \
            .classes('form-input').props('type=date')
        with Row(classes='edit-card-actions'):
            ui.button(_("Save"), on_click=handle_save).classes('btn-primary')
            ui.button(_("Cancel"), on_click=dlg.close).classes('btn-secondary')
    dlg.open()


async def _revoke_assignment(row: dict, store):
    # role_name = row.get("role__name", "")
    # confirmed = await confirm_dialog({
    #     'question': _('Revoke role "{role}"?', role=role_name),
    #     # 'explanation': _('This will remove the role assignment.'),
    # })
    # if confirmed:
    ui.notify(_("Role has been revoked"), type="positive")
    await store.delete_item(row)


async def render_guest_role_assignments(guest: dict, tenant: str):
    """Render role assignments table with edit/revoke buttons and navigation to role."""
    guest_id = guest.get('id')
    store = get_role_assignment_store(tenant)

    async def handle_edit(row: dict):
        await _edit_assignment_dialog(tenant, row)

    async def handle_revoke(row: dict):
        await _revoke_assignment(row, store)

    table = ActionButtonTable(
        data_source=store,
        config=get_role_assignment_config(),
        filter_by={"guest_id": guest_id},
        on_add=lambda: _assign_role_dialog(tenant, guest, table),
        on_edit=handle_edit,
        on_delete=handle_revoke,
    )
    await table.build()     # type: ignore


@ui.page('/{tenant}/m/guests')
async def guests_page(tenant: str = Depends(require_guests_auth), id: int | None = None):

    ui_state = {"viewstack": {}, "editcard": {}, "detail_card": {}}

    with frame('guests', tenant):
        guest_store = get_guest_store(tenant)
        table_config = get_guests_table_config()
        form_config = get_guests_form_config()

        async def render_list(vs: ViewStack):
            async def on_click(row_id):
                items = await guest_store.read_items(filter_by={"id": row_id})
                if items:
                    vs.show_detail(items[0])
            table = ListTable(
                data_source=guest_store, config=table_config,
                on_click=on_click, on_add=vs.show_edit_new,
            )
            await table.build_with_toolbars()

        async def render_detail(vs: ViewStack, item: dict):
            async def render_body(_: dict):
                await render_guest_role_assignments(item, tenant)

            detail = DetailCard(
                state=ui_state["detail_card"],
                data_source=guest_store,
                render_summary=render_guest_details,
                render_related=render_body,
                on_edit=lambda i: vs.show_edit_existing(i),
                on_delete=lambda i: delete_guest(tenant, i["id"]),
                on_deleted=vs.show_list,
            )
            detail.set_item(item)
            await detail.build()

        async def render_edit(vs: ViewStack, item: dict | None):
            edit = EditCard(
                state=ui_state['editcard'],
                data_source=guest_store, config=form_config,
                on_saved=lambda saved: vs.show_detail(saved),
                on_cancel=lambda: vs.show_detail(item) if item else vs.show_list(),
            )
            edit.set_item(item)
            await edit.build()

        stack = ViewStack(
            state=ui_state['viewstack'],
            render_list=render_list,
            render_detail=render_detail,
            render_edit=render_edit,
        )
        await stack.build()

        if id is not None:
            guests = await guest_store.read_items(filter_by={"id": id})
            if guests:
                stack.show_detail(guests[0])
