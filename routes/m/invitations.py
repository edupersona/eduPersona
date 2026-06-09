# /m/{tenant}/invitations — persona-mode invitations list (view, resend, delete),
# built on the ng_rdm ViewStack → ListTable → DetailCard widgets. Creation lives in
# /m/{tenant}/simulator, so this page has no add-dialog.

import httpx
import jinja2
from fastapi import Depends
from nicegui import ui, html

from ng_rdm.components import (
    Button, Column, TableConfig,
    ViewStack, ListTable, DetailCard, Dialog,
    none_as_text, Col, Row, Separator,
)

from domain.invitations import invitation_to_dict
from domain.models import Invitation, WebhookDelivery
from domain.stores import get_invitation_store
from services.auth.dependencies import require_invite_auth
from services.i18n import _
from services.persona_loader import get_persona_config
from services.postmark.postmark import send_invitation_mail
from services.ui_errors import ui_guard
from services.theme import frame


def render_status(row: dict) -> None:
    """Render status as a colored chip (styled by .status-chip-* under .invitations-page)."""
    status = row.get("status", "") or ""
    ui.html(f'<span class="status-chip status-chip-{status}">{_(status)}</span>', sanitize=False)


@ui.page("/m/{tenant}/invitations")
async def invitations_page(tenant: str = Depends(require_invite_auth)):
    invitation_store = get_invitation_store(tenant)
    ui_state = {"viewstack": {}, "detail_card": {}, "params_dlg": {}, "facts_dlg": {}}
    dlg_data: dict = {}  # current item's params/outputs, fed to the dialog bodies

    def persona_label(key: str) -> str:
        try:
            return get_persona_config(tenant, key).label("nl")
        except ValueError:
            return key

    def render_persona(row: dict) -> None:
        ui.label(persona_label(row.get("persona_key") or ""))

    def render_kv(data: dict) -> None:
        with html.div().classes("facts-kv"):
            for k, v in data.items():
                ui.label(str(k)).classes("facts-kv-key")
                ui.label(str(v)).classes("facts-kv-val")

    # Detail-view dialogs are built ONCE here, not inside the refreshable detail
    # body — Dialog attaches its backdrop to the client root layout, so rebuilding
    # it per detail-navigation would leak backdrops. Bodies refresh from dlg_data.
    @ui.refreshable
    def params_body() -> None:
        params = dlg_data.get("params") or {}
        render_kv(params) if params else ui.label(_("No parameters.")).classes("rdm-detail-text-sm")

    @ui.refreshable
    def facts_body() -> None:
        outputs = dlg_data.get("outputs") or {}
        if not outputs:
            ui.label(_("No collected facts.")).classes("rdm-detail-text-sm")
        for section, facts in outputs.items():
            with html.div().classes("facts-section"):
                ui.label(section).classes("rdm-detail-section-label")
                render_kv(facts) if isinstance(facts, dict) else ui.label(str(facts)).classes("facts-kv-val")

    params_dlg = Dialog(state=ui_state["params_dlg"], title=_("Invitation parameters"),
                        dialog_class="panel-dialog facts-dialog")
    with params_dlg:
        params_body()
    facts_dlg = Dialog(state=ui_state["facts_dlg"], title=_("Verified facts"),
                       dialog_class="panel-dialog facts-dialog")
    with facts_dlg:
        facts_body()

    def open_params(item: dict) -> None:
        dlg_data["params"] = item.get("persona_params") or {}
        params_body.refresh()
        params_dlg.open()

    def open_facts(item: dict) -> None:
        dlg_data["outputs"] = item.get("step_outputs") or {}
        facts_body.refresh()
        facts_dlg.open()

    table_config = TableConfig(
        columns=[
            Column(name="calc_guest_name", label=_("Guest"), width_percent=22),
            Column(name="persona_key", label=_("Persona"), width_percent=16, render=render_persona),
            Column(name="invited_at", label=_("Invited"), width_percent=16, formatter=none_as_text),
            Column(name="expiry_date", label=_("Expires"), width_percent=14, formatter=none_as_text),
            Column(name="accepted_at", label=_("Accepted"), width_percent=16, formatter=none_as_text),
            Column(name="status", label=_("Status"), width_percent=12, render=render_status),
        ],
        empty_message=_("No invitations found."),
    )

    async def render_summary(item: dict) -> None:
        status = item.get("status", "") or ""
        with Row(classes="rdm-detail-header"):
            ui.icon("mail", size="xl").classes("rdm-detail-icon")
            with Col(classes="rdm-detail-title-group"):
                ui.label(item.get("calc_guest_name") or "").classes("rdm-detail-title")
                ui.html(f'<span class="status-chip status-chip-{status}">{_(status)}</span>', sanitize=False)

        Separator()

        with Row(classes="rdm-detail-columns"):
            with Col(classes="rdm-detail-column"):
                ui.label(_("Invitation details")).classes("rdm-detail-section-label")
                for label, value in (
                    (_("Email"), item.get("invitation_email")),
                    (_("Invited at"), none_as_text(item.get("invited_at", ""))),
                    (_("Expires at"), none_as_text(item.get("expiry_date", ""))),
                    (_("Accepted at"), none_as_text(item.get("accepted_at", ""))),
                    (_("Code"), item.get("code")),
                    (_("Guest ID"), item.get("guest_id")),
                ):
                    if value:
                        ui.label(f"{label}: {value}").classes("rdm-detail-text-sm")

            with Col(classes="rdm-detail-column"):
                ui.label("Persona: " + persona_label(item.get("persona_key") or "")).classes("rdm-detail-section-label")
                with Row(classes="rdm-detail-actions"):
                    if item.get("persona_params"):
                        Button(_("Inputs") + "…", color="secondary", icon="input",
                               on_click=lambda _e, i=item: open_params(i))
                    if item.get("step_outputs"):
                        Button(_("Outputs") + "…", color="secondary", icon="output",
                               on_click=lambda _e, i=item: open_facts(i))

    async def do_resend(item: dict) -> None:
        inv = await Invitation.get_or_none(id=item.get("id"), tenant=tenant)
        ok = False
        with ui_guard(_("Failed to send email"),
                      catch=(ValueError, jinja2.TemplateError, httpx.HTTPError)):
            ok = bool(inv) and await send_invitation_mail(tenant, invitation_to_dict(inv))  # type: ignore[arg-type]
        if ok:
            ui.notify(_("Email sent successfully!"), type="positive")

    async def do_delete(item: dict) -> None:
        await WebhookDelivery.filter(invitation_id=item.get("id")).delete()
        await invitation_store.delete_item(item)

    async def render_related(item: dict) -> None:
        with html.div().classes("rdm-detail-actions"):
            Button(_("Resend"), on_click=lambda _e, i=item: do_resend(i))

    async def render_list(vs: ViewStack) -> None:
        async def on_click(row_id) -> None:
            items = await invitation_store.read_items(filter_by={"id": row_id})
            if items:
                vs.show_detail(items[0])

        table = ListTable(data_source=invitation_store, config=table_config, on_click=on_click)
        await table.build()

    async def render_detail(vs: ViewStack, item: dict) -> None:
        detail = DetailCard(
            data_source=invitation_store,
            render_summary=render_summary,
            state=ui_state["detail_card"],
            render_related=render_related,
            on_delete=do_delete,
            on_deleted=vs.show_list,
            show_edit=False,
        )
        detail.set_item(item)
        await detail.build()

    async def render_edit(_vs: ViewStack, _item: dict | None) -> None:
        pass  # invitations are not editable

    stack = ViewStack(
        state=ui_state["viewstack"],
        render_list=render_list,
        render_detail=render_detail,
        render_edit=render_edit,
    )

    with frame("invitations", tenant):
        await stack.build()
