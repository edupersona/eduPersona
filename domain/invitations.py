"""Invitation lifecycle (persona-mode) — the only invitation surface post-cutover.

Shape B (§2.7, gotcha 9): an invitation is the only entity. These functions write
the `Invitation` model directly — no Guest find-or-create. `given_name`/`family_name`
are display strings from the client app, never refined from eduID.
"""

import uuid
from typing import Optional

from domain.models import Invitation
from domain.stores import get_invitation_store
from ng_rdm.store.multitenancy import valid_tenants
from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc, utc_datetime_to_str
from services.persona_loader import get_persona_config, validate_persona_params
from services.webhook import enqueue_callback


async def find_invitation_tenant(code: str) -> Optional[str]:
    """Resolve the tenant owning invitation `code`, scanning all tenants."""
    for tenant in valid_tenants:
        if await Invitation.exists(tenant=tenant, code=code):
            return tenant
    return None


def invitation_to_dict(inv: Invitation) -> dict:
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
        "sender_email": inv.sender_email,
        "sender_name": inv.sender_name,
    }


async def create_invitation(
    tenant: str,
    persona_key: str,
    email: str,
    *,
    given_name: Optional[str] = None,
    family_name: Optional[str] = None,
    client_ref: Optional[str] = None,
    persona_params: Optional[dict] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
    callback_url: Optional[str] = None,
) -> dict:
    """Create an invitation row directly (no Guest entity).

    Validates the persona and its params via the loader (UnknownPersonaError /
    PersonaParamsError, both ValueError). `callback_url` falls back to the persona's
    configured default. Re-invites are never deduplicated (§2.1).
    """
    cfg = get_persona_config(tenant, persona_key)          # UnknownPersonaError if absent
    coerced = validate_persona_params(cfg, persona_params)  # PersonaParamsError on violation

    # Persist through the store so its StoreEvent reaches any open invitations table.
    created = await get_invitation_store(tenant).create_item({
        "code": uuid.uuid4().hex,
        "invitation_email": email,
        "status": "pending",
        "persona_key": persona_key,
        "given_name": given_name,
        "family_name": family_name,
        "client_ref": client_ref,
        "persona_params": coerced or None,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "callback_url": callback_url or cfg.callback_url,
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
    from services.scim_observer import push_verified_user
    await push_verified_user(tenant, inv)
    return True


async def apply_invite_to_state(tenant: str, state: dict, code: str) -> bool:
    """Populate session `state` with persona context for the accept flow (§5.3).

    Sets invite_code, invitation_id, persona_key, persona_params, guest_email,
    given_name, family_name. Pure mutation.
    """
    inv = await Invitation.get_or_none(tenant=tenant, code=code.strip())
    if inv is None:
        logger.warning(f"apply_invite_to_state: invalid code attempted: {code}")
        return False

    state["invite_code"] = inv.code
    state["invitation_id"] = inv.id
    state["persona_key"] = inv.persona_key
    state["persona_params"] = inv.persona_params or {}
    state["guest_email"] = inv.invitation_email
    state["given_name"] = inv.given_name
    state["family_name"] = inv.family_name
    return True
