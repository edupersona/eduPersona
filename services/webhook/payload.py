"""Build the outbound callback envelope from an Invitation.

Single source of truth: universal fields come straight off the Invitation row;
the `verifications` block is built by iterating the persona's `callback_outputs`
and reading `Invitation.step_outputs[key]` verbatim (§2.7, §7). No Guest joins,
no cross-invitation lookups.
"""

from datetime import datetime
from typing import Any

from ng_rdm.utils import logger
from ng_rdm.utils.helpers import str_to_utc_datetime
from domain.models import Invitation
from services.persona_loader import get_persona_config


def _iso(value: Any) -> str | None:
    """Normalize a stored datetime to ISO 8601 (gotcha 7).

    Persona-mode writes native datetimes (so this is just `.isoformat()`), but the
    legacy store wrote `'%Y-%m-%d / %H:%M:%S'` local strings — parse those back to
    UTC so the envelope is always ISO regardless of who wrote the row.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return str_to_utc_datetime(value).isoformat()
        except ValueError:
            return value  # already ISO (or unknown) — pass through
    return str(value)


def build_payload(invitation: Invitation, tenant: str) -> dict:
    """Construct the callback body for `invitation`.

    Universal fields are always present. `verifications` contains one entry per
    persona `callback_outputs` key that has a matching `step_outputs` entry; a
    declared-but-missing source is logged and omitted (never breaks delivery).
    """
    cfg = get_persona_config(tenant, invitation.persona_key or "")
    step_outputs: dict = invitation.step_outputs or {}

    verifications: dict[str, Any] = {}
    for key in cfg.callback_outputs:
        if key in step_outputs:
            verifications[key] = step_outputs[key]
        else:
            logger.warning(
                f"build_payload: persona '{invitation.persona_key}' declares callback_output "
                f"'{key}' but invitation {invitation.id} has no step_outputs['{key}'] — omitting"
            )

    return {
        "tenant": tenant,
        "persona": invitation.persona_key,
        "invitation_code": invitation.code,
        "guest_id": invitation.guest_id,
        "completed_at": _iso(invitation.accepted_at),
        "email": invitation.invitation_email,
        "persona_params": invitation.persona_params or {},
        "verifications": verifications,
    }
