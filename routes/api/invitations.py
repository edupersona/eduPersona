"""Invitation API (persona-mode) — the only invitation API surface post-cutover.

    POST   /api/v1/{tenant}/invitations            - create + fire mail
    GET    /api/v1/{tenant}/invitations            - list (filters + pagination)
    GET    /api/v1/{tenant}/invitations/{id}       - single + webhook_deliveries summary
    GET    /api/v1/{tenant}/invitations/code/{code} - public lookup by code
    POST   /api/v1/{tenant}/invitations/{id}/resend - bump invited_at, re-fire mail
    DELETE /api/v1/{tenant}/invitations/{id}        - revoke
"""
from fastapi import Query, Request
from pydantic import BaseModel

from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc, utc_datetime_to_str
from domain.invitations import create_invitation
from domain.models import Invitation, WebhookDelivery
from services.persona_loader import PersonaParamsError, UnknownPersonaError
from services.postmark.postmark import send_invitation_mail

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


# ── response models (drive /docs + /redoc; success payloads use the {data, meta} envelope) ──


class InvitationData(BaseModel):
    id: int
    code: str
    status: str
    persona_key: str
    client_ref: str | None = None
    invitation_email: str
    given_name: str | None = None
    family_name: str | None = None
    persona_params: dict = {}
    callback_url: str | None = None
    invited_at: str | None = None
    accepted_at: str | None = None
    accept_url: str


class DeliverySummary(BaseModel):
    id: int
    status: str
    attempt_n: int
    last_status_code: int | None = None
    next_retry_at: str | None = None


class InvitationDetailData(InvitationData):
    webhook_deliveries: list[DeliverySummary] = []


class Meta(BaseModel):
    timestamp: str
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class InvitationEnvelope(BaseModel):
    data: InvitationData
    meta: Meta


class InvitationDetailEnvelope(BaseModel):
    data: InvitationDetailData
    meta: Meta


class InvitationListEnvelope(BaseModel):
    data: list[InvitationData]
    meta: Meta


class DeleteResult(BaseModel):
    deleted: bool
    id: int


class DeleteEnvelope(BaseModel):
    data: DeleteResult
    meta: Meta


class _ApiError(BaseModel):
    code: str
    message: str
    details: dict | None = None


class _ErrorDetail(BaseModel):
    error: _ApiError


class ErrorEnvelope(BaseModel):
    detail: _ErrorDetail


# Reusable error-response docs (the api_error envelope) attached per endpoint.
_AUTH_ERR = {401: {"model": ErrorEnvelope, "description": "Missing or invalid API key"}}
_NOT_FOUND_ERR = {404: {"model": ErrorEnvelope, "description": "Invitation or persona not found"}}
_VALIDATION_ERR = {400: {"model": ErrorEnvelope, "description": "Invalid request data"}}


def _valid_email(value: str) -> bool:
    """Basic format check (no domain restriction in the base app, §2.2)."""
    if not value or value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain and not domain.endswith(".")


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _to_api_dict(inv: Invitation, request: Request) -> dict:
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
        "accept_url": _accept_url(request, inv.code),
    }


def _accept_url(request: Request, code: str) -> str:
    return str(request.base_url).rstrip("/") + f"/accept/{code}"


async def _send_mail_best_effort(tenant: str, invitation: dict) -> None:
    """Send the persona invite mail. Best-effort — never fatal (gotcha 6)."""
    ok = await send_invitation_mail(tenant, invitation)
    if not ok:
        logger.warning(f"persona invite mail not sent for {invitation['code']} (transport returned false)")


@api_router.post("/invitations", response_model=InvitationEnvelope,
                 responses={**_AUTH_ERR, **_VALIDATION_ERR, **_NOT_FOUND_ERR})
async def create_invitation_endpoint(tenant: str, data: InvitationCreate, request: Request):
    """Create an invitation and fire its mail (best-effort)."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/invitations", tenant, persona_key=data.persona_key)

    if not _valid_email(data.email):
        raise api_error("VALIDATION_ERROR", f"Invalid email: {data.email!r}", status_code=400)
    if data.sender_email is not None and not _valid_email(data.sender_email):
        raise api_error("VALIDATION_ERROR", f"Invalid sender_email: {data.sender_email!r}", status_code=400)

    try:
        invitation = await create_invitation(
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

    # Return the full resource (same shape as GET) so create and fetch agree.
    inv = await Invitation.get(tenant=tenant, id=invitation["id"])
    return api_response(_to_api_dict(inv, request))


@api_router.get("/invitations", response_model=InvitationListEnvelope, responses={**_AUTH_ERR})
async def list_invitations(
    tenant: str,
    request: Request,
    status: str | None = None,
    persona_key: str | None = None,
    client_ref: str | None = None,
    email: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List invitations with optional filters."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", "/invitations", tenant, status=status, persona_key=persona_key)

    qs = Invitation.filter(tenant=tenant)
    if status:
        qs = qs.filter(status=status)
    if persona_key:
        qs = qs.filter(persona_key=persona_key)
    if client_ref:
        qs = qs.filter(client_ref=client_ref)
    if email:
        qs = qs.filter(invitation_email=email)

    rows = await qs.order_by("-id").all()
    items = [_to_api_dict(inv, request) for inv in rows]
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


@api_router.get("/invitations/code/{code}", response_model=InvitationEnvelope,
                responses={**_AUTH_ERR, **_NOT_FOUND_ERR})
async def get_invitation_by_code(tenant: str, code: str, request: Request):
    """Public lookup by code (used by the accept page)."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/invitations/code/{code[:8]}...", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, code=code)
    if inv is None:
        raise api_error("NOT_FOUND", "Invitation not found", status_code=404)
    return api_response(_to_api_dict(inv, request))


@api_router.get("/invitations/{invitation_id}", response_model=InvitationDetailEnvelope,
                responses={**_AUTH_ERR, **_NOT_FOUND_ERR})
async def get_invitation(tenant: str, invitation_id: int, request: Request):
    """Single invitation plus a summary of its webhook deliveries."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/invitations/{invitation_id}", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, id=invitation_id)
    if inv is None:
        raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

    deliveries = await WebhookDelivery.filter(invitation_id=invitation_id).order_by("id").all()
    item = _to_api_dict(inv, request)
    item["webhook_deliveries"] = [_delivery_summary(d) for d in deliveries]
    return api_response(item)


@api_router.post("/invitations/{invitation_id}/resend", response_model=InvitationEnvelope,
                 responses={**_AUTH_ERR, **_NOT_FOUND_ERR})
async def resend_invitation(tenant: str, invitation_id: int, request: Request):
    """Bump invited_at and re-fire the invite mail (best-effort)."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", f"/invitations/{invitation_id}/resend", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, id=invitation_id)
    if inv is None:
        raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

    # Through the store (auto_now_add won't re-write invited_at on save) so the bump
    # repaints any open invitations table.
    from domain.stores import get_invitation_store
    await get_invitation_store(tenant).update_item(invitation_id, {"invited_at": utc_datetime_to_str(now_utc())})
    inv = await Invitation.get(id=invitation_id)
    from domain.invitations import invitation_to_dict
    try:
        await _send_mail_best_effort(tenant, invitation_to_dict(inv))
    except Exception as e:
        logger.error(f"persona invite resend mail failed (non-fatal) for {inv.code}: {e}")
    return api_response(_to_api_dict(inv, request))


@api_router.delete("/invitations/{invitation_id}", response_model=DeleteEnvelope,
                   responses={**_AUTH_ERR, **_NOT_FOUND_ERR})
async def delete_invitation(tenant: str, invitation_id: int):
    """Revoke (delete) an invitation and its webhook deliveries."""
    validate_tenant_or_raise(tenant)
    log_api_call("DELETE", f"/invitations/{invitation_id}", tenant)

    inv = await Invitation.get_or_none(tenant=tenant, id=invitation_id)
    if inv is None:
        raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

    await WebhookDelivery.filter(invitation_id=invitation_id).delete()
    from domain.stores import get_invitation_store
    await get_invitation_store(tenant).delete_item({"id": invitation_id})
    return api_response({"deleted": True, "id": invitation_id})
