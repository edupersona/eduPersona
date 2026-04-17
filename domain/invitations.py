"""
Invitation lifecycle: create, accept, resend, delete (incl. junction cleanup), query with roles.
"""
import uuid

from domain.models import RoleAssignment, InvitationRoleAssignment
from domain.stores import (
    get_invitation_store,
    get_role_assignment_store,
    get_role_store,
)
from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc, utc_datetime_to_str


async def create_invitation(
    tenant: str, guest_id: int, role_assignment_ids: list[int],
    invitation_email: str, personal_message: str = "",
) -> dict:
    """Create an invitation for existing role assignments.

    Generates invitation code and creates junction records.
    Returns the created invitation dict.
    """
    invitation_store = get_invitation_store(tenant)

    invitation_data = {
        "code": uuid.uuid4().hex,
        "guest_id": guest_id,
        "invitation_email": invitation_email,
        "status": "pending",
        "personal_message": personal_message,
    }

    invitation = await invitation_store.create_item(invitation_data)
    if not invitation:
        raise ValueError("Failed to create invitation")

    # Create junction records linking invitation to role assignments
    for ra_id in role_assignment_ids:
        await InvitationRoleAssignment.create(
            invitation_id=invitation["id"],
            role_assignment_id=ra_id,
        )

    return invitation


async def accept_invitation(tenant: str, code: str) -> bool:
    """Accept invitation: update status and provision linked role assignments to SCIM.

    Args:
        tenant: Tenant identifier
        code: Invitation code

    Returns:
        True if successful
    """
    invitation_store = get_invitation_store(tenant)

    # Find invitation by code
    invitations = await invitation_store.read_items(filter_by={"code": code})
    if not invitations:
        logger.warning(f"accept_invitation: invitation not found for code={code}")
        return False

    invitation = invitations[0]
    if invitation["status"] != "pending":
        logger.warning(f"accept_invitation: invitation {invitation['id']} not pending (status={invitation['status']})")
        return False

    # Update invitation status
    updated = await invitation_store.update_item(
        invitation["id"],
        {
            "status": "accepted",
            "accepted_at": utc_datetime_to_str(now_utc())
        }
    )

    if not updated:
        logger.error(f"accept_invitation: failed to update invitation {invitation['id']}")
        return False

    # Get linked role assignments via junction table
    junctions = await InvitationRoleAssignment.filter(invitation_id=invitation["id"]).all()
    role_assignment_ids = [j.role_assignment_id for j in junctions]         # type: ignore

    # SCIM provisioning for each linked role assignment
    from services.scim_observer import get_scim_observer
    observer = get_scim_observer()
    if observer:
        for ra_id in role_assignment_ids:
            ra = await RoleAssignment.get(id=ra_id)
            await observer.provision_guest_on_first_acceptance(ra.guest_id, ra.role_id)     # type: ignore

    return True


async def resend_invitation(tenant: str, invitation_id: int) -> dict | None:
    """Resend invitation: update invited_at timestamp.

    Args:
        tenant: Tenant identifier
        invitation_id: Invitation ID

    Returns:
        Updated invitation dict, or None if not found
    """
    invitation_store = get_invitation_store(tenant)

    updated = await invitation_store.update_item(
        invitation_id,
        {"invited_at": utc_datetime_to_str(now_utc())}
    )

    return updated


async def delete_invitation(tenant: str, invitation: dict) -> None:
    """Delete an invitation and its junction rows.

    Junction cleanup happens first (FK constraint), then the invitation itself
    is deleted via the store — so observers see a StoreEvent("delete").
    """
    await InvitationRoleAssignment.filter(invitation_id=invitation["id"]).delete()
    await get_invitation_store(tenant).delete_item(invitation)


async def get_invitation_with_roles(tenant: str, code: str) -> dict | None:
    """Get invitation by code with linked role assignments and role details.

    Args:
        tenant: Tenant identifier
        code: Invitation code

    Returns:
        Invitation dict with 'role_assignments' list containing role details, or None
    """
    invitation_store = get_invitation_store(tenant)
    role_assignment_store = get_role_assignment_store(tenant)
    role_store = get_role_store(tenant)

    invitations = await invitation_store.read_items(filter_by={"code": code})
    if not invitations:
        return None

    invitation = invitations[0]

    # Get linked role assignments via junction table
    junctions = await InvitationRoleAssignment.filter(invitation_id=invitation["id"]).all()
    role_assignment_ids = [j.role_assignment_id for j in junctions]       # type: ignore

    # Get full role assignment details with role info
    role_assignments = []
    for ra_id in role_assignment_ids:
        ra_list = await role_assignment_store.read_items(filter_by={"id": ra_id})
        if ra_list:
            ra = ra_list[0]
            # Enrich with role details
            role = await role_store.read_item_by_id(ra["role_id"])
            if role:
                ra["role"] = role
            role_assignments.append(ra)

    invitation["role_assignments"] = role_assignments
    return invitation
