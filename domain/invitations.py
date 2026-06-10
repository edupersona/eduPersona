"""Invitation lifecycle — the only invitation surface.

An invitation is the only entity. These functions write
the `Invitation` model directly. `given_name`/`family_name`
are display strings from the client app, never refined from eduID.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

import pytz

from domain.models import Invitation
from domain.stores import get_invitation_store
from ng_rdm.store.multitenancy import valid_tenants
from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc, str_to_utc_datetime, utc_datetime_to_str
from services.persona_loader import get_persona_config, validate_persona_params
from services.settings import get_tenant_config
from services.webhook import enqueue_callback


DEFAULT_EXPIRY_DAYS = 14


def _expiry_str_for(tenant: str) -> str | None:
    """Store-format expiry timestamp from the tenant's `expiry_duration` (days).
    0 / unset → None (never expires)."""
    days = get_tenant_config(tenant).get("expiry_duration", DEFAULT_EXPIRY_DAYS)
    if not days or int(days) <= 0:
        return None
    return utc_datetime_to_str(now_utc() + timedelta(days=int(days)))


async def find_invitation_tenant(code: str) -> Optional[str]:
    """Resolve the tenant owning invitation `code`, scanning all tenants."""
    for tenant in valid_tenants:
        if await Invitation.exists(tenant=tenant, code=code):
            return tenant
    return None


async def expire_overdue_invitations(tenant: str | None = None) -> int:
    """Flip pending invitations past their `expiry_date` to 'expired'. Scans one tenant
    or all. Reads and writes both go through the store so open tables stay coherent;
    NULL expiry → never expires."""
    tenants = [tenant] if tenant else list(valid_tenants)
    now = now_utc()
    n = 0
    for t in tenants:
        store = get_invitation_store(t)
        for item in await store.read_items(filter_by={"status": "pending"}):
            raw = item.get("expiry_date")  # store-hydrated 'YYYY-MM-DD / HH:MM:SS'
            if raw and str_to_utc_datetime(raw) <= now:
                await store.update_item(item["id"], {"status": "expired"})
                n += 1
    return n


def invitation_to_dict(inv: Invitation) -> dict:
    return {
        "id": inv.id,
        "code": inv.code,
        "status": inv.status,
        "persona_key": inv.persona_key,
        "guest_id": inv.guest_id,
        "invitation_email": inv.invitation_email,
        "given_name": inv.given_name,
        "family_name": inv.family_name,
        "persona_params": inv.persona_params or {},
        "callback_url": inv.callback_url,
        "sender_email": inv.sender_email,
        "sender_name": inv.sender_name,
        "expiry_date": utc_datetime_to_str(inv.expiry_date) if inv.expiry_date else None,
    }


async def create_invitation(
    tenant: str,
    persona_key: str,
    email: str,
    guest_id: str,
    *,
    given_name: Optional[str] = None,
    family_name: Optional[str] = None,
    persona_params: Optional[dict] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
    callback_url: Optional[str] = None,
    expiry_date: Optional[datetime] = None,
) -> dict:
    """Create an invitation row directly.

    `guest_id` (the client app's identifier for the guest) is required — it maps to
    the SCIM externalId on provisioning. Validates the persona and its params via the
    loader (UnknownPersonaError / PersonaParamsError, both ValueError). `callback_url`
    falls back to the persona's configured default. `expiry_date` overrides the tenant
    default duration (naive → treated as UTC). Re-invites are never deduplicated.
    """
    if not (guest_id := (guest_id or "").strip()):
        raise ValueError("guest_id is required")
    cfg = get_persona_config(tenant, persona_key)          # UnknownPersonaError if absent
    coerced = validate_persona_params(cfg, persona_params)  # PersonaParamsError on violation

    if expiry_date is not None:
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=pytz.utc)
        expiry_str = utc_datetime_to_str(expiry_date.astimezone(pytz.utc))
    else:
        expiry_str = _expiry_str_for(tenant)

    # Persist through the store so its StoreEvent reaches any open invitations table.
    created = await get_invitation_store(tenant).create_item({
        "code": uuid.uuid4().hex,
        "invitation_email": email,
        "status": "pending",
        "persona_key": persona_key,
        "given_name": given_name,
        "family_name": family_name,
        "guest_id": guest_id,
        "persona_params": coerced or None,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "callback_url": callback_url or cfg.callback_url,
        "expiry_date": expiry_str,
    })
    if created is None:
        raise ValueError(f"invitation persistence failed for persona '{persona_key}'")
    inv = await Invitation.get(tenant=tenant, id=created["id"])
    return invitation_to_dict(inv)


async def accept_invitation(tenant: str, code: str) -> bool:
    """Mark a pending invitation accepted and fire its callback.

    Callback failure is logged, never raised — it must not roll back acceptance.
    """
    inv = await Invitation.get_or_none(tenant=tenant, code=code)
    if inv is None:
        logger.warning(f"accept_invitation: invitation not found for code={code}")
        return False
    if inv.status != "pending":
        logger.warning(f"accept_invitation: invitation {inv.id} not pending (status={inv.status})")
        return False

    # Through the store so the status flip repaints any open invitations table. The
    # store round-trips datetimes as strings; build_payload's _iso normalizes either way.
    await get_invitation_store(tenant).update_item(
        inv.id, {"status": "accepted", "accepted_at": utc_datetime_to_str(now_utc())})

    if inv.callback_url:
        try:
            await enqueue_callback(tenant, inv.id)
        except Exception as e:  # delivery is best-effort; acceptance already committed
            logger.error(f"accept_invitation: callback enqueue failed for {inv.id}: {e}")

    # Dormant opt-in: push the bare verified user to the client's IGA over SCIM.
    # No-op unless the tenant configures an enabled `scim` block (never raises).
    from services.scim import push_verified_user
    await push_verified_user(tenant, inv)
    return True


async def apply_invite_to_state(tenant: str, state: dict, code: str) -> bool:
    """Populate session `state` with persona context for the accept flow.

    Sets invite_code, invitation_id, persona_key, persona_params, guest_email,
    given_name, family_name. Pure mutation.

    When the tab switches to a *different* invitation, clears the orchestrator-owned
    onboarding progress (outcomes/outputs/completion flags) so persona A's status never
    bleeds into persona B — each invitation onboards from scratch. Gated on the
    invitation changing, so the OIDC round-trip (same code, page reloads mid-flow)
    keeps in-progress steps.
    """
    inv = await Invitation.get_or_none(tenant=tenant, code=code.strip())
    if inv is None:
        logger.warning(f"apply_invite_to_state: invalid code attempted: {code}")
        return False

    if state.get("invitation_id") != inv.id:
        state["outcomes"] = {}
        state["outputs"] = {}
        state.pop("completed", None)
        state.pop("finalize_failed", None)

    state["invite_code"] = inv.code
    state["invitation_id"] = inv.id
    state["persona_key"] = inv.persona_key
    state["persona_params"] = inv.persona_params or {}
    state["guest_email"] = inv.invitation_email
    state["given_name"] = inv.given_name
    state["family_name"] = inv.family_name
    return True
