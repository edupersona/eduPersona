"""
Guest authentication: eduID-based session for returning guests.
Parallel to services/auth/oidc.py (admin) — reuses the tenant's oidc.eduid config.
"""
from datetime import datetime

from nicegui import app, ui

from domain.stores import get_guest_store, get_invitation_store
from ng_rdm.utils import logger


async def establish_guest_session_for_code(tenant: str, invite_code: str) -> bool:
    """Establish a guest session for the guest linked to this invitation code.

    Used at onboarding completion so the freshly-verified guest can access /apps
    without a second eduID login. Returns True on success, False (with a logged
    reason) on any lookup failure.
    """
    invitations = await get_invitation_store(tenant).read_items(filter_by={"code": invite_code})
    if not invitations:
        logger.error(f"establish_guest_session: invitation not found for code={invite_code}")
        return False
    guest_id = invitations[0].get("guest_id")
    guests = await get_guest_store(tenant).read_items(filter_by={"id": guest_id})
    if not guests:
        logger.error(f"establish_guest_session: guest {guest_id} not found (invite {invite_code})")
        return False
    await complete_guest_authentication(tenant, guests[0])
    return True


async def complete_guest_authentication(tenant: str, guest: dict) -> None:
    """Establish a guest session in app.storage.user after eduID verification."""
    display_name = " ".join(filter(None, [guest.get("given_name"), guest.get("family_name")])) \
        or guest.get("email") or "gast"
    app.storage.user.update({
        "tenant": tenant,
        "username": display_name,
        "authenticated": True,
        "last_activity_datetime": datetime.now(),
        "expired": False,
        "authz": [],                    # no admin permissions
        "user_type": "guest",
        "guest_id": guest["id"],
        "eduid_pseudonym": guest.get("eduid_pseudonym"),
        "language": "nl_nl",
    })
    logger.info(f"Guest session established: tenant={tenant}, guest_id={guest['id']}")


def create_guest_oidc_handler(tenant: str):
    """Factory: OIDC callback handler that matches eduID pseudonym to a Guest and logs them in."""

    async def guest_result_handler(userinfo: dict, id_token_claims: dict, token_data: dict, next_url: str = "") -> None:
        uids = userinfo.get("uids") or []
        if not uids:
            logger.error("Guest eduID login: userinfo missing 'uids' claim")
            ui.navigate.to(f"/{tenant}/apps/no_account")
            return

        pseudonym = uids[0]
        guests = await get_guest_store(tenant).read_items(filter_by={"eduid_pseudonym": pseudonym})
        if not guests:
            logger.info(f"Guest eduID login: no guest with pseudonym={pseudonym[:8]}...")
            ui.navigate.to(f"/{tenant}/apps/no_account")
            return

        await complete_guest_authentication(tenant, guests[0])
        ui.navigate.to(next_url or f"/{tenant}/apps")

    return guest_result_handler
