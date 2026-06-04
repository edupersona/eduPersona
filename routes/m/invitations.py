# /m/{tenant}/invitations — persona-mode invitations list (view, resend, revoke).

from fastapi import Depends
from nicegui import ui

from ng_rdm.utils import logger
from domain.invitations import invitation_to_dict
from domain.models import Invitation, WebhookDelivery
from services.auth.dependencies import require_invite_auth
from services.i18n import _
from services.persona_loader import get_persona_config
from services.postmark.postmark import send_invitation_mail
from services.theme import frame


def _persona_label(tenant: str, persona_key: str) -> str:
    try:
        return get_persona_config(tenant, persona_key).label("nl")
    except Exception:
        return persona_key


def _guest_name(inv: Invitation) -> str:
    name = " ".join(p for p in (inv.given_name, inv.family_name) if p).strip()
    return name or inv.invitation_email


@ui.page("/m/{tenant}/invitations")
async def invitations_page(tenant: str = Depends(require_invite_auth)):
    ui.label(_("Invitations")).classes("page-title")

    columns = [
        {"name": "guest", "label": _("Guest"), "field": "guest", "align": "left"},
        {"name": "persona", "label": _("Persona"), "field": "persona", "align": "left"},
        {"name": "invited_at", "label": _("Invited"), "field": "invited_at", "align": "left"},
        {"name": "accepted_at", "label": _("Accepted"), "field": "accepted_at", "align": "left"},
        {"name": "status", "label": _("Status"), "field": "status", "align": "left"},
    ]

    @ui.refreshable
    async def render_table() -> None:
        rows_data = await Invitation.filter(tenant=tenant).order_by("-id").all()
        rows = [{
            "id": inv.id,
            "code": inv.code,
            "guest": _guest_name(inv),
            "persona": _persona_label(tenant, inv.persona_key),
            "invited_at": inv.invited_at.isoformat(sep=" ", timespec="minutes") if inv.invited_at else "",
            "accepted_at": inv.accepted_at.isoformat(sep=" ", timespec="minutes") if inv.accepted_at else "—",
            "status": inv.status,
        } for inv in rows_data]

        table = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")
        table.add_slot("body-cell-actions", "")  # placeholder; actions handled via row click below

        async def show_detail(inv_id: int) -> None:
            inv = await Invitation.get_or_none(id=inv_id)
            if inv is None:
                return
            with ui.dialog() as dialog, ui.card().style("min-width: 28rem;"):
                ui.label(f"{_guest_name(inv)} — {_persona_label(tenant, inv.persona_key)}").classes("step-title")
                for label, value in [
                    (_("Email"), inv.invitation_email),
                    (_("Code"), inv.code),
                    (_("Client reference"), inv.client_ref or "—"),
                    (_("Status"), inv.status),
                ]:
                    ui.label(f"{label}: {value}")
                if inv.persona_params:
                    with ui.expansion(_("Persona parameters"), icon="tune"):
                        for k, v in inv.persona_params.items():
                            ui.label(f"{k}: {v}").style("font-size: 0.875rem;")
                if inv.step_outputs:
                    with ui.expansion(_("Verified facts"), icon="verified"):
                        ui.code(str(inv.step_outputs)).style("white-space: pre-wrap;")

                with ui.row():
                    async def do_resend() -> None:
                        ok = await send_invitation_mail(tenant, invitation_to_dict(inv))
                        ui.notify(_("Email sent successfully!") if ok else _("Failed to send email"),
                                  type="positive" if ok else "negative")

                    async def do_delete() -> None:
                        await WebhookDelivery.filter(invitation_id=inv.id).delete()
                        await inv.delete()
                        dialog.close()
                        render_table.refresh()
                        ui.notify(_("Deleted"), type="positive")

                    ui.button(_("Resend"), on_click=do_resend)
                    ui.button(_("Delete"), on_click=do_delete).props("color=negative")
                    ui.button(_("Close"), on_click=dialog.close).props("flat")
            dialog.open()

        table.on("rowClick", lambda e: show_detail(e.args[1]["id"]))

    with frame("invitations", tenant):
        await ui.context.client.connected()
        await render_table()
