"""Persona-mode invitation lifecycle — parallel to the legacy role-mode functions.

Shape B (§2.7, gotcha 9): an invitation is the only entity. These functions write
the `Invitation` model directly — no `Guest` find-or-create, the legacy `guest`
FK is left NULL. `given_name`/`family_name` are display strings from the client
app, never refined from eduID. Lives alongside `domain/invitations.py` until the
Phase I cutover folds it in.
"""

import uuid
from typing import Optional

from domain.models import Invitation
from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc
from services.persona_loader import get_persona_config, validate_persona_params
from services.webhook import enqueue_callback


def _invitation_to_dict(inv: Invitation) -> dict:
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


async def create_persona_invitation(
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
    """Create a persona-mode invitation row directly (no Guest entity).

    Validates the persona and its params via the loader (UnknownPersonaError /
    PersonaParamsError, both ValueError). `callback_url` falls back to the
    persona's configured default. Re-invites are never deduplicated — every call
    creates a new row (§2.1); the client app owns re-verify policy.
    """
    cfg = get_persona_config(tenant, persona_key)          # UnknownPersonaError if absent
    coerced = validate_persona_params(cfg, persona_params)  # PersonaParamsError on violation

    inv = await Invitation.create(
        tenant=tenant,
        code=uuid.uuid4().hex,
        guest=None,                       # Shape B: no Guest in persona-mode
        invitation_email=email,
        status="pending",
        persona_key=persona_key,
        given_name=given_name,
        family_name=family_name,
        client_ref=client_ref,
        persona_params=coerced or None,
        sender_email=sender_email,
        sender_name=sender_name,
        callback_url=callback_url or cfg.callback_url,
    )
    return _invitation_to_dict(inv)


async def accept_persona_invitation(tenant: str, code: str) -> bool:
    """Mark a pending persona invitation accepted and fire its callback.

    Sets status/accepted_at, then enqueues the webhook when `callback_url` is set.
    Callback failure is logged, never raised — it must not roll back acceptance.
    """
    inv = await Invitation.get_or_none(tenant=tenant, code=code)
    if inv is None:
        logger.warning(f"accept_persona_invitation: invitation not found for code={code}")
        return False
    if inv.status != "pending":
        logger.warning(f"accept_persona_invitation: invitation {inv.id} not pending (status={inv.status})")
        return False

    inv.status = "accepted"
    inv.accepted_at = now_utc()   # native datetime — build_payload reads it as ISO (gotcha 7)
    await inv.save()

    if inv.callback_url:
        try:
            await enqueue_callback(tenant, inv.id)
        except Exception as e:  # delivery is best-effort; acceptance already committed
            logger.error(f"accept_persona_invitation: callback enqueue failed for {inv.id}: {e}")
    return True


async def apply_persona_invite_to_state(tenant: str, state: dict, code: str) -> bool:
    """Populate session `state` with persona context for the accept flow (§5.3).

    Sets invite_code, invitation_id, persona_key, persona_params, guest_email,
    given_name, family_name. No role_assignments, no guest_id. Pure mutation.
    """
    inv = await Invitation.get_or_none(tenant=tenant, code=code.strip())
    if inv is None:
        logger.warning(f"apply_persona_invite_to_state: invalid code attempted: {code}")
        return False

    state["invite_code"] = inv.code
    state["invitation_id"] = inv.id
    state["persona_key"] = inv.persona_key
    state["persona_params"] = inv.persona_params or {}
    state["guest_email"] = inv.invitation_email
    state["given_name"] = inv.given_name
    state["family_name"] = inv.family_name
    return True
