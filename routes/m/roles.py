# /roles page

from fastapi import Depends
from nicegui import html, ui

from ng_loba.crud import ActionButtonTable, Column, CrudDialog, CrudTabs, TableConfig, ViewStack, page_init, none_as_text
from ng_loba.crud.fields import build_form_field
from ng_loba.utils import logger
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


def get_roles_config_select() -> TableConfig:
    return TableConfig(
        table_columns=[
            Column(name="app", label="app", width_percent=10, render=_render_app_logo),
            Column(name="name", label=_("Role name"), width_percent=40),
            Column(name="role_details", label=_("Details"), width_percent=45),
            Column(name="scope", label=_("Scope"), width_percent=8),
        ],
        empty_message=_("No roles found"),
        add_button=_("New Role..."),
    )


def get_roles_config_detail() -> TableConfig:
    return TableConfig(
        dialog_columns=[
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
            # Column(name="more_info_email", label=_("For more info, mail to (optional)"),
            #        placeholder=_("e.g., servicedesk@university.com")),
            # Column(name="more_info_name", label=_("For more info, contact name (optional)"),
            #        placeholder=_("e.g., Servicedesk")),
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
        dialog_title_add=_("New Role"),
        dialog_title_edit=_("Edit Role"),
    )


async def render_role_details(role: dict):
    MAX_LEN_URL = 40

    with ui.row().classes('detail-header'):
        tenant = role.get('tenant')
        logo = role.get('logo_file_name')
        if tenant and logo:
            ui.image(f'/static/{tenant}/logos/{logo}').classes('detail-image')
        with ui.column().classes('detail-title-group'):
            ui.label(role.get('name', '')).classes('detail-title')
            ui.label(role.get('org_name', '')).classes('detail-subtitle')
    ui.separator()
    with ui.row().classes('detail-columns'):
        with ui.column().classes('detail-column'):
            ui.label(_('Dates')).classes('detail-section-label')
            ui.label(f"{_('Default start')}: {none_as_text(role.get('default_start_date', ''))}")
            ui.label(f"{_('Default end')}: {none_as_text(role.get('default_end_date', ''))}")
            ui.label(f"{_('Role end')}: {none_as_text(role.get('role_end_date', ''))}")
        with ui.column().classes('detail-column'):
            ui.label(_('Details')).classes('detail-section-label')
            ui.label(role.get('role_details', '-') or '-')
            ui.label(f"{_('Scope')}: {role.get('scope', '-') or '-'}").classes('detail-text-sm')
        with ui.column().classes('detail-column'):
            ui.label(_('Application')).classes('detail-section-label')
            ui.label(role.get('redirect_text', '-') or '-')
            if (url := role.get('redirect_url')):
                if len(url) > MAX_LEN_URL:
                    url = url[:MAX_LEN_URL] + '...'
                ui.link(url, role['redirect_url']).classes('detail-text-sm')


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
        show_edit_button=True,
        show_delete_button=True,
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

    with CrudDialog() as dlg:
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
        with ui.row().classes('edit-card-actions'):
            ui.button(_("Assign"), on_click=handle_assign).classes('btn-primary')
            ui.button(_("Cancel"), on_click=dlg.close).classes('btn-secondary')
    dlg.open()


async def _edit_assignment_dialog(tenant: str, row: dict):
    """Dialog to edit start/end dates of a role assignment."""
    state = {
        "start_date": row.get("start_date") or "",
        "end_date": row.get("end_date") or "",
    }

    with CrudDialog() as dlg:
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
        with ui.row().classes('edit-card-actions'):
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

        table = ActionButtonTable(
            state={},
            data_source=store,
            config=get_role_guests_config(),
            filter_by={"role_id": role_id},
            on_edit=handle_edit,
            on_delete=handle_revoke,
            edit_label=_("Edit"),
            delete_label=_("Revoke"),
        )
        await table.build()     # type: ignore

        with ui.row().classes('content-actions'):
            ui.button(_("Assign Role..."), icon="add",
                      on_click=lambda: _assign_guest_dialog(tenant, role, table)).classes('btn-primary')

    async def admins_panel():
        ui.label(_("Admin functions coming soon"))

    tabs = CrudTabs([
        ("guests", _("Guests"), guests_panel),
        ("admins", _("Admins"), admins_panel),
    ])
    await tabs.build()      # type: ignore


@ui.page('/{tenant}/m/roles')
async def roles_page(tenant: str = Depends(require_role_admin_auth), id: int | None = None):
    logger.debug(f"roles page accessed by tenant: {tenant}")
    page_init()

    with frame('roles', tenant):
        role_store = get_role_store(tenant)

        async def role_detail_footer(role: dict):
            await render_role_tabs(role, tenant)

        stack = ViewStack(
            data_source=role_store,
            select_config=get_roles_config_select(),
            detail_config=get_roles_config_detail(),
            render_detail=render_role_details,
            breadcrumb_root=_("Roles"),
            item_label=lambda item: item.get("name", ""),
            detail_footer=role_detail_footer,
        )
        await stack.build()  # type: ignore

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
            with ui.column().classes('centered-content'):
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

        with ui.row().classes('dialog-actions'):
            ui.button(_('Synchronize'), on_click=handle_sync).classes('btn-success')
            ui.button(_('Cancel'), on_click=handle_cancel).classes('btn-secondary')

    sync_dialog.open()
