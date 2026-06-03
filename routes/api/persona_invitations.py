"""Persona-mode invitation API (parallel to the legacy role-mode invitations API).

    POST   /api/v1/{tenant}/persona-invitations            - create + fire mail
    GET    /api/v1/{tenant}/persona-invitations            - list (filters + pagination)
    GET    /api/v1/{tenant}/persona-invitations/{id}       - single + webhook_deliveries summary
    GET    /api/v1/{tenant}/persona-invitations/code/{code} - public lookup by code
    POST   /api/v1/{tenant}/persona-invitations/{id}/resend - bump invited_at, re-fire mail
    DELETE /api/v1/{tenant}/persona-invitations/{id}        - revoke

Distinct `/persona-invitations` prefix avoids colliding with the role-mode
`/invitations` routes until the Phase I cutover folds this in.
"""
from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc
from domain.invitations_persona import create_persona_invitation
from domain.models import Invitation, WebhookDelivery
from services.persona_loader import PersonaParamsError, UnknownPersonaError

from . import tenant_api_router as api_router
from .common import (
    api_error, api_response, apply_pagination, log_api_call, validate_tenant_or_raise,
)


class InvitationCreate(BaseModel):
    persona_key: str
    email: str
    given_name: str | None = None
    family_name: str | None = None
    client_ref: str | None = None
    persona_params: dict | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    callback_url: str | None = None


def _valid_email(value: str) -> bool:
    """Basic format check (no domain restriction in the base app, §2.2)."""
    if not value or value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain and not domain.endswith(".")


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _to_api_dict(inv: Invitation) -> dict:
    return {
        "id": inv.id,
        "code": inv.code,
        "status": inv.status,
        "persona_key": inv.persona_key,
        "client_ref": inv.client_ref,
        "invitation_email": inv.invitation_email,
        "given_name": inv.given_name,
        "family_name": inv.family_name,
        "persona_params": inv.persona_params or {},
        "callback_url": inv.callback_url,
        "invited_at": _iso(inv.invited_at),
        "accepted_at": _iso(inv.accepted_at),
    }


def _accept_url(request: Request, code: str) -> str:
    return str(request.base_url).rstrip("/") + f"/accept/p/{code}"


async def _send_mail_best_effort(tenant: str, invitation: dict) -> None:
    """Send the persona invite mail. Best-effort — never fatal (gotcha 6).

    Phase E stub: logs only. Phase F replaces the body with send_persona_invitation.
    """
    logger.info(f"persona invite mail (stub) tenant={tenant} code={invitation['code']}")


@api_router.post("/persona-invitations")
async def create_persona_invitation_endpoint(tenant: str, data: InvitationCreate, request: Request):
    """Create a persona-mode invitation and fire its mail (best-effort)."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/persona-invitations", tenant, persona_key=data.persona_key)

    if not _valid_email(data.email):
        raise api_error("VALIDATION_ERROR", f"Invalid email: {data.email!r}", status_code=400)
    if data.sender_email is not None and not _valid_email(data.sender_email):
        raise api_error("VALIDATION_ERROR", f"Invalid sender_email: {data.sender_email!r}", status_code=400)

    try:
        invitation = await create_persona_invitation(
            tenant, data.persona_key, data.email,
            given_name=data.given_name, family_name=data.family_name,
            client_ref=data.client_ref, persona_params=data.persona_params,
            sender_email=data.sender_email, sender_name=data.sender_name,
            callback_url=data.callback_url,
        )
    except UnknownPersonaError as e:
        raise api_error("NOT_FOUND", str(e), status_code=404)
    except PersonaParamsError as e:
        raise api_error("VALIDATION_ERROR", str(e), status_code=400)

    try:
        await _send_mail_best_effort(tenant, invitation)
    except Exception as e:  # mail outage must not roll back the persisted invitation
        logger.error(f"persona invite mail failed (non-fatal) for {invitation['code']}: {e}")

    return api_response({
        "id": invitation["id"],
        "code": invitation["code"],
        "status": invitation["status"],
        "persona_key": invitation["persona_key"],
        "client_ref": invitation["client_ref"],
        "accept_url": _accept_url(request, invitation["code"]),
    })


@api_router.get("/persona-invitations")
async def list_persona_invitations(
    tenant: str,
    status: str | None = None,
    persona_key: str | None = None,
    client_ref: str | None = None,
    email: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List persona invitations with optional filters."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", "/persona-invitations", tenant, status=status, persona_key=persona_key)

    qs = Invitation.filter(tenant=tenant, persona_key__isnull=False)
    if status:
        qs = qs.filter(status=status)
    if persona_key:
        qs = qs.filter(persona_key=persona_key)
    if client_ref:
        qs = qs.filter(client_ref=client_ref)
    if email:
        qs = qs.filter(invitation_email=email)

    rows = await qs.order_by("-id").all()
    items = [_to_api_dict(inv) for inv in rows]
    total = len(items)
    return api_response(apply_pagination(items, limit, offset), total=total, limit=limit, offset=offset)


def _delivery_summary(d: WebhookDelivery) -> dict:
    return {
        "id": d.id,
        "status": d.status,
        "attempt_n": d.attempt_n,
        "last_status_code": d.last_status_code,
        "next_retry_at": _iso(d.next_retry_at),
    }


@api_router.get("/persona-invitations/code/{code}")
async def get_persona_invitation_by_code(tenant: str, code: str):
    """Public lookup by code (used by the accept page)."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/persona-invitations/code/{code[:8]}...", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, code=code, persona_key__isnull=False)
    if inv is None:
        raise api_error("NOT_FOUND", "Invitation not found", status_code=404)
    return api_response(_to_api_dict(inv))


@api_router.get("/persona-invitations/{invitation_id}")
async def get_persona_invitation(tenant: str, invitation_id: int):
    """Single invitation plus a summary of its webhook deliveries."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/persona-invitations/{invitation_id}", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, id=invitation_id, persona_key__isnull=False)
    if inv is None:
        raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

    deliveries = await WebhookDelivery.filter(invitation_id=invitation_id).order_by("id").all()
    item = _to_api_dict(inv)
    item["webhook_deliveries"] = [_delivery_summary(d) for d in deliveries]
    return api_response(item)


@api_router.post("/persona-invitations/{invitation_id}/resend")
async def resend_persona_invitation(tenant: str, invitation_id: int):
    """Bump invited_at and re-fire the invite mail (best-effort)."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", f"/persona-invitations/{invitation_id}/resend", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, id=invitation_id, persona_key__isnull=False)
    if inv is None:
        raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

    # queryset update — invited_at is auto_now_add, which model.save() won't re-write
    await Invitation.filter(id=invitation_id).update(invited_at=now_utc())
    inv = await Invitation.get(id=invitation_id)
    try:
        await _send_mail_best_effort(tenant, _to_api_dict(inv))
    except Exception as e:
        logger.error(f"persona invite resend mail failed (non-fatal) for {inv.code}: {e}")
    return api_response(_to_api_dict(inv))


@api_router.delete("/persona-invitations/{invitation_id}")
async def delete_persona_invitation(tenant: str, invitation_id: int):
    """Revoke (delete) a persona invitation and its webhook deliveries."""
    validate_tenant_or_raise(tenant)
    log_api_call("DELETE", f"/persona-invitations/{invitation_id}", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, id=invitation_id, persona_key__isnull=False)
    if inv is None:
        raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

    await WebhookDelivery.filter(invitation_id=invitation_id).delete()
    await inv.delete()
    return api_response({"deleted": True, "id": invitation_id})
