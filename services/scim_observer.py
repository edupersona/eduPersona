"""Dormant, opt-in SCIM bare-user provisioning (persona-mode).

The webhook callback (services/webhook/) owns the *core* completion flow. This module
is a **separate, opt-in** capability: when a tenant configures a `scim` block, an
accepted invitation also pushes the *bare verified user* — eduID identity from
`Invitation.step_outputs` plus the invitation email — to the client's IGA via SCIM.
No groups, no roles, no local Guest entity (those live in the client's IAM/IGA).

Dormant by default: `push_verified_user` is a no-op unless the tenant's `scim` block
is present and enabled, so importing or shipping this module costs nothing. The
heavyweight `scim2-*` deps are imported lazily inside `SCIMClient`, only when enabled.
"""
from typing import Any

from ng_rdm.utils import logger
from services.settings import get_tenant_config


class SCIMClient:
    """Minimal SCIM client for bare-user upsert (create-or-replace by externalId)."""

    def __init__(self, base_url: str, bearer_token: str):
        from httpx import Client
        from scim2_client.engines.httpx import SyncSCIMClient
        from scim2_models import SearchRequest

        http_client = Client(base_url=base_url, headers={"Authorization": f"Bearer {bearer_token}"})
        self.client = SyncSCIMClient(http_client)
        self.client.discover()  # auto-discover server schemas (incl. Enterprise extensions)
        self.User = self.client.get_resource_model("User")
        self.SearchRequest = SearchRequest

    def _build_user(self, user: dict, scim_id: str | None = None):
        """Build a SCIM User from a flat user dict.

        Nested objects are passed as dicts because discover() yields server-specific
        Name/Email classes that differ from the scim2_models defaults.
        """
        display_name = (
            user.get("display_name")
            or ((user.get("given_name") or "") + " " + (user.get("family_name") or "")).strip()
            or None
        )
        email = user.get("email") or ""
        return self.User(
            id=scim_id,  # type: ignore
            external_id=user.get("user_id"),  # type: ignore
            user_name=user.get("user_id") or "",  # type: ignore
            name={  # type: ignore
                "formatted": display_name,
                "familyName": user.get("family_name"),
                "givenName": user.get("given_name"),
            },
            display_name=display_name,  # type: ignore
            active=True,  # type: ignore
            emails=[{"value": email}] if email else [],  # type: ignore
        )

    def create_or_update_user(self, user: dict) -> str | None:
        """Upsert a SCIM User by externalId; return its SCIM id, or None on failure."""
        user_id = user.get("user_id")
        if not user_id:
            return None
        try:
            search = self.SearchRequest(filter=f'externalId eq "{user_id}"')  # type: ignore
            existing = self.client.query(self.User, query_parameters=search)
            if existing and getattr(existing, "resources", None):  # type: ignore
                scim_id = existing.resources[0].id  # type: ignore
                self.client.replace(self._build_user(user, scim_id))
                logger.info(f"SCIM: replaced user {user_id} (SCIM id {scim_id})")
                return scim_id
            created = self.client.create(self._build_user(user))
            logger.info(f"SCIM: created user {user_id} (SCIM id {getattr(created, 'id', None)})")
            return getattr(created, "id", None)
        except Exception as e:
            logger.error(f"SCIM: upsert of user {user_id} failed: {e}")
            return None


def _scim_config(tenant: str) -> dict | None:
    """Return the tenant's scim block iff enabled and fully configured, else None."""
    sc: dict[str, Any] = get_tenant_config(tenant).get("scim", {}) or {}
    if sc.get("scim_enabled") and sc.get("scim_base_url") and sc.get("bearer_token"):
        return sc
    return None


def _bare_user_from_invitation(invitation, identity_key: str) -> dict:
    """Flatten an accepted invitation's verified eduID identity into a user dict."""
    identity: dict = (invitation.step_outputs or {}).get(identity_key, {})
    return {
        "user_id": identity.get("sub") or invitation.invitation_email,
        "given_name": identity.get("given_name") or invitation.given_name,
        "family_name": identity.get("family_name") or invitation.family_name,
        "email": identity.get("email") or invitation.invitation_email,
        "display_name": identity.get("name"),
    }


async def push_verified_user(tenant: str, invitation) -> bool:
    """Best-effort: push the accepted invitation's bare verified user to SCIM.

    No-op (returns False) unless the tenant has an enabled `scim` block. The eduID
    identity is read from `step_outputs[identity_key]` (default "eduid"). Never raises —
    SCIM provisioning must not affect invitation acceptance.
    """
    sc = _scim_config(tenant)
    if sc is None:
        return False
    try:
        user = _bare_user_from_invitation(invitation, sc.get("identity_key", "eduid"))
        scim_id = SCIMClient(sc["scim_base_url"], sc["bearer_token"]).create_or_update_user(user)
        return scim_id is not None
    except Exception as e:
        logger.error(f"SCIM: push_verified_user failed for tenant {tenant}: {e}")
        return False
