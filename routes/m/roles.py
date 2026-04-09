# /roles page

from fastapi import Depends
from nicegui import html, ui

from ng_rdm.components import (
    ActionButtonTable, Column, Dialog, Tabs, TableConfig, FormConfig,
    ViewStack, EditCard, ListTable, DetailCard, rdm_init, none_as_text, Col, Row,
)
from ng_rdm.components.fields import build_form_field
from ng_rdm.utils import logger
from services.auth.dependencies import require_role_admin_auth
from services.i18n import _
from services.tenant import get_tenant_from_session
from services.scim_observer import bulk_sync_to_scim
from domain.stores import get_role_store, get_role_assignment_store, get_guest_store
from domain.invitation_flow import create_role_assignment, update_role_assignment
from services.theme import frame


def _render_app_logo(row: dict):
    tenant = row.get('tenant')
    logo = row.get('logo_file_name')
    if tenant and logo:
        html.img(src=f'/static/{tenant}/logos/{logo}')
    else:
        ui.label(row.get('redirect_text') or '-')


ROLES_TABLE_CONFIG = TableConfig(
    columns=[
        Column(name="app", label="app", width_percent=10, render=_render_app_logo),
        Column(name="name", label=_("Role name"), width_percent=40),
        Column(name="role_details", label=_("Details"), width_percent=45),
        Column(name="scope", label=_("Scope"), width_percent=8),
    ],
    empty_message=_("No roles found"),
    add_button=_("New Role..."),
    toolbar_position="bottom",
)

ROLES_FORM_CONFIG = FormConfig(
    columns=[
        Column(name="name", label=_("Role name"),
               placeholder=_("e.g. Visiting Professor of Mathematics")),
        Column(name="org_name", label=_("Organizational unit inviting the guest"),
               placeholder=_("e.g., Faculty of Physics & Mathematics")),
        Column(name="role_details", label=_("Role details (course, term, period, code)"),
               placeholder=_("e.g. visiting professor term II / 2026-2027")),
        Column(name="mail_sender_email", label=_("Sender email"),
               placeholder=_("Invite sender's mail address")),
        Column(name="mail_sender_name", label=_("Sender name"),
               placeholder=_("e.g., Carol Johnson")),
        Column(name="redirect_text", label=_("Application name"),
               placeholder=_("e.g. Canvas (UvA)")),
        Column(name="redirect_url", label=_("Application URL"),
               placeholder=_("https://example.com/")),
        Column(name="default_start_date", label=_("Default start date (optional)"),
               placeholder=_("YYYY-MM-DD")),
        Column(name="default_end_date", label=_("Default end date (optional)"),
               placeholder=_("YYYY-MM-DD")),
        Column(name="role_end_date", label=_("Role end date (required)"),
               placeholder=_("YYYY-MM-DD")),
        Column(name="scope", label=_("Scope (who can use and manage this role)"),
               placeholder=_("e.g. upva")),
    ],
    title_add=_("New Role"),
    title_edit=_("Edit Role"),
)


async def render_role_details(role: dict):
    MAX_LEN_URL = 40

    with Row(classes='rdm-detail-header'):
        tenant = role.get('tenant')
        logo = role.get('logo_file_name')
        if tenant and logo:
            ui.image(f'/static/{tenant}/logos/{logo}').classes('rdm-detail-image')
        with Col(classes='rdm-detail-title-group'):
            ui.label(role.get('name', '')).classes('rdm-detail-title')
            ui.label(role.get('org_name', '')).classes('rdm-detail-subtitle')
    ui.separator()
    with Row(classes='rdm-detail-columns'):
        with Col(classes='rdm-detail-column'):
            ui.label(_('Dates')).classes('rdm-detail-section-label')
            ui.label(f"{_('Default start')}: {none_as_text(role.get('default_start_date', ''))}").classes(
                'rdm-detail-text-sm')
            ui.label(f"{_('Default end')}: {none_as_text(role.get('default_end_date', ''))}").classes('rdm-detail-text-sm')
            ui.label(f"{_('Role end')}: {none_as_text(role.get('role_end_date', ''))}").classes('rdm-detail-text-sm')
        with Col(classes='rdm-detail-column'):
            ui.label(_('Details')).classes('rdm-detail-section-label')
            ui.label(role.get('role_details', '-') or '-').classes('rdm-detail-text-sm')
            ui.label(f"{_('Scope')}: {role.get('scope', '-') or '-'}").classes('rdm-detail-text-sm')
        with Col(classes='rdm-detail-column'):
            ui.label(_('Application')).classes('rdm-detail-section-label')
            ui.label(role.get('redirect_text', '-') or '-').classes('rdm-detail-text-sm')
            if (url := role.get('redirect_url')):
                if len(url) > MAX_LEN_URL:
                    url = url[:MAX_LEN_URL] + '...'
                ui.link(url, role['redirect_url']).classes('rdm-detail-text-sm')


def _go_to_guest(row: dict):
    """Navigate to guest detail page."""
    tenant = get_tenant_from_session()
    if tenant and (guest_id := row.get("guest_id")):
        ui.navigate.to(f'/{tenant}/m/guests?id={guest_id}')


def get_role_guests_config() -> TableConfig:
    return TableConfig(
        columns=[
            Column(name="guest__user_id", label=_("Guest"), width_percent=26, on_click=_go_to_guest),
            Column(name="guest__email", label=_("Email"), width_percent=25),
            Column(name="start_date", label=_("Start"), width_percent=15, formatter=none_as_text),
            Column(name="end_date", label=_("End"), width_percent=15, formatter=none_as_text),
        ],
        empty_message=_("No guests assigned"),
        show_add_button=True,
        add_button=_("Assign Role..."),
        show_edit_button=True,
        show_delete_button=True,
        toolbar_position="bottom",
    )


ASSIGN_GUEST_COLUMNS = [
    Column(name="start_date", label=_("Start date"), placeholder=_("YYYY-MM-DD (optional)")),
    Column(name="end_date", label=_("End date"), placeholder=_("YYYY-MM-DD (optional)")),
]


async def _assign_guest_dialog(tenant: str, role: dict, table):
    """Dialog to assign this role to a guest."""
    guest_store = get_guest_store(tenant)
    role_assignment_store = get_role_assignment_store(tenant)

    guests = await guest_store.read_items()
    existing = await role_assignment_store.read_items(filter_by={"role_id": role["id"]})
    existing_guest_ids = {a["guest_id"] for a in existing}
    available_guests = [g for g in guests if g["id"] not in existing_guest_ids]

    if not available_guests:
        ui.notify(_("All guests already assigned to this role"), type="info")
        return

    guest_options = {g["id"]: g.get("display_name") or g.get("user_id", "-") for g in available_guests}
    state = {"guest_id": None, "start_date": "", "end_date": ""}

    with Dialog() as dlg:
        async def handle_assign():
            if not state["guest_id"]:
                dlg._notify(_("Please select a guest"), type="warning")
                return
            try:
                await create_role_assignment(
                    tenant, state["guest_id"], role["id"],
                    state["start_date"], state["end_date"]
                )
                dlg._notify(_("Role assigned"), type="positive")
                dlg.close()
                await table.build.refresh()
            except Exception as e:
                dlg._notify(str(e), type="negative")

        ui.label(_('Assign "{name}" to Guest', name=role.get("name", ""))).classes('dialog-header')
        ui.select(
            options=guest_options, label=_("Select Guest"),
            with_input=True, clearable=True,
        ).bind_value(state, "guest_id").classes('form-input').props('popup-content-style="z-index: 6100"')
        for col in ASSIGN_GUEST_COLUMNS:
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
                dlg._notify(_("Dates are updated"), type="positive")
                dlg.close()
            except Exception as e:
                dlg._notify(str(e), type="negative")

        guest_name = row.get("guest__user_id", "")
        ui.label(_("Edit dates for {guest}", guest=guest_name)).classes('dialog-header')
        ui.input(label=_("Start date"), placeholder=_("YYYY-MM-DD")).bind_value(state, "start_date") \
            .classes('form-input').props('type=date')
        ui.input(label=_("End date"), placeholder=_("YYYY-MM-DD")).bind_value(state, "end_date") \
            .classes('form-input').props('type=date')
        with Row(classes='edit-card-actions'):
            ui.button(_("Save"), on_click=handle_save).classes('btn-primary')
            ui.button(_("Cancel"), on_click=dlg.close).classes('btn-secondary')
    dlg.open()


async def _revoke_assignment(row: dict, store):
    ui.notify(_("Role has been revoked"), type="positive")
    await store.delete_item(row)


async def render_role_tabs(role: dict, tenant: str):
    role_id = role.get('id')
    store = get_role_assignment_store(tenant)

    async def guests_panel():
        async def handle_edit(row: dict):
            await _edit_assignment_dialog(tenant, row)

        async def handle_revoke(row: dict):
            await _revoke_assignment(row, store)

        with Row(classes='rdm-detail-outer'):
            table = ActionButtonTable(
                data_source=store,
                config=get_role_guests_config(),
                filter_by={"role_id": role_id},
                on_add=lambda: _assign_guest_dialog(tenant, role, table),
                on_edit=handle_edit,
                on_delete=handle_revoke,
            )
            await table.build()     # type: ignore

    async def admins_panel():
        ui.label(_("Admin functions coming soon"))

    tabs = Tabs(tabs=[
        ("guests", _("Guests"), guests_panel),
        ("admins", _("Admins"), admins_panel),
    ])
    await tabs.build()      # type: ignore


@ui.page('/{tenant}/m/roles')
async def roles_page(tenant: str = Depends(require_role_admin_auth), id: int | None = None):
    logger.debug(f"roles page accessed by tenant: {tenant}")
    rdm_init()

    ui_state = {"viewstack": {}, "editcard": {}, "detail_card": {}}

    with frame('roles', tenant):
        role_store = get_role_store(tenant)

        async def render_list(vs: ViewStack):
            async def on_click(row_id):
                items = await role_store.read_items(filter_by={"id": row_id})
                if items:
                    vs.show_detail(items[0])
            table = ListTable(
                data_source=role_store, config=ROLES_TABLE_CONFIG,
                on_click=on_click, on_add=vs.show_edit_new,
            )
            await table.build()

        async def render_detail(vs: ViewStack, item: dict):
            async def render_body(_: dict):
                await render_role_tabs(item, tenant)

            detail = DetailCard(
                state=ui_state["detail_card"],
                data_source=role_store,
                render_summary=render_role_details,
                render_related=render_body,
                on_edit=lambda i: vs.show_edit_existing(i),
                show_delete=False,
            )
            detail.set_item(item)
            await detail.build()

        async def render_edit(vs: ViewStack, item: dict | None):
            edit = EditCard(
                state=ui_state['editcard'],
                data_source=role_store, config=ROLES_FORM_CONFIG,
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
            roles = await role_store.read_items(filter_by={"id": id})
            if roles:
                stack.show_detail(roles[0])


def scim_sync_dialog(tenant, table):
    """Show SCIM sync dialog and perform bulk sync"""
    logger.info("Opening SCIM sync dialog")

    async def handle_sync():
        logger.info("Starting SCIM bulk sync")
        sync_dialog.close()

        with ui.dialog() as progress_dialog, ui.card().classes('dialog-card'):
            ui.label(_('SCIM Synchronization')).classes('dialog-header')
            with Col(classes='centered-content'):
                ui.spinner('dots', size='lg')
                ui.label(_('Synchronizing...'))

        progress_dialog.open()

        try:
            results = await bulk_sync_to_scim(tenant)
            progress_dialog.close()

            if results.get('error'):
                ui.notify(_('SCIM sync failed'), type='negative', timeout=5000)
            else:
                success_msg = (
                    f"{_('SCIM sync completed!')}\n"
                    f"{_('Guests: {count} synchronized', count=results['guests']['synced'])}\n"
                    f"{_('Roles: {count} synchronized', count=results['roles']['synced'])}\n"
                    f"{_('Memberships: {count} synchronized', count=results['memberships']['synced'])}"
                )
                ui.notify(success_msg, type='positive', timeout=5000, multi_line=True)
                await table.build.refresh()

        except Exception as e:
            progress_dialog.close()
            logger.error(f"SCIM sync failed: {e}")
            ui.notify(_('SCIM sync error'), type='negative', timeout=5000)

    def handle_cancel():
        logger.info("SCIM sync cancelled")
        sync_dialog.close()

    with ui.dialog() as sync_dialog, ui.card().classes('dialog-card'):
        ui.label(_('SCIM Synchronization')).classes('dialog-header')
        ui.label(_('This will synchronize all existing guests, roles and memberships to the SCIM server.'))
        ui.label(_('Are you sure you want to continue?')).classes('text-warning')

        with Row(classes='dialog-actions'):
            ui.button(_('Synchronize'), on_click=handle_sync).classes('btn-success')
            ui.button(_('Cancel'), on_click=handle_cancel).classes('btn-secondary')

    sync_dialog.open()
