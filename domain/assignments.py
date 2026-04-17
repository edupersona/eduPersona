"""
Role assignment lifecycle: create, update, delete (incl. junction cleanup), revoke, legacy SCIM assign.
"""
from datetime import date

from domain.models import InvitationRoleAssignment
from domain.stores import get_guest_store, get_role_store, get_role_assignment_store
from ng_rdm.utils import logger
from services.i18n import _


def validate_assignment_end_date(end_date: str, role_end_date: str) -> None:
    """Validate that assignment end_date is not later than role_end_date.
    Raises ValueError with user-friendly message if invalid.
    """
    if not end_date or not role_end_date:
        return
    try:
        end = date.fromisoformat(end_date)
        role_end = date.fromisoformat(role_end_date)
        if end > role_end:
            raise ValueError(_("End date cannot be later than role end date ({date})", date=role_end_date))
    except ValueError as e:
        if "End date cannot be later" in str(e):
            raise
        # Ignore parse errors - let the DB handle invalid date formats


async def create_role_assignment(
    tenant: str, guest_id: int, role_id: int,
    start_date: str = "", end_date: str = "",
) -> dict:
    """Create a role assignment (without invitation).

    For direct admin assignment workflows.
    Returns the created role assignment dict.
    Raises ValueError if end_date > role_end_date.
    """
    role_assignment_store = get_role_assignment_store(tenant)
    role_store = get_role_store(tenant)

    role = await role_store.read_item_by_id(role_id)
    if not role:
        raise ValueError(f"Role with id {role_id} not found")

    # Use provided dates or fall back to role defaults
    final_end_date = end_date or role.get('default_end_date', '')

    # Validate end_date against role_end_date
    validate_assignment_end_date(final_end_date, role.get('role_end_date', ''))

    assignment_data = {
        "guest_id": guest_id,
        "role_id": role_id,
        "start_date": start_date or role.get('default_start_date', ''),
        "end_date": final_end_date,
    }

    role_assignment = await role_assignment_store.create_item(assignment_data)
    if not role_assignment:
        raise ValueError("Failed to create role assignment")
    return role_assignment


async def update_role_assignment(
    tenant: str, assignment_id: int, start_date: str, end_date: str
) -> dict:
    """Update role assignment dates with validation.

    Raises ValueError if end_date > role_end_date.
    Returns updated assignment dict.
    """
    role_assignment_store = get_role_assignment_store(tenant)
    role_store = get_role_store(tenant)

    # Fetch the assignment to get role_id
    assignment = await role_assignment_store.read_item_by_id(assignment_id)
    if not assignment:
        raise ValueError(f"Role assignment with id {assignment_id} not found")

    # Fetch the role to get role_end_date
    role = await role_store.read_item_by_id(assignment['role_id'])
    if not role:
        raise ValueError(f"Role with id {assignment['role_id']} not found")

    # Validate end_date against role_end_date
    validate_assignment_end_date(end_date, role.get('role_end_date', ''))

    updated = await role_assignment_store.update_item(assignment_id, {
        "start_date": start_date or None,
        "end_date": end_date or None,
    })
    if not updated:
        raise ValueError("Failed to update role assignment")
    return updated


async def delete_role_assignment(tenant: str, assignment: dict) -> None:
    """Delete a role assignment and its invitation junction rows.

    Junction cleanup happens first (FK constraint), then the assignment itself
    is deleted via the store — so observers see a StoreEvent("delete").
    """
    await InvitationRoleAssignment.filter(role_assignment_id=assignment["id"]).delete()
    await get_role_assignment_store(tenant).delete_item(assignment)


async def assign_role(tenant: str, guest_id: int, role_id: int) -> bool:
    """Accept role assignment: update status and provision to SCIM if needed.

    Legacy function for backward compatibility - works with role assignments.

    Args:
        tenant: Tenant identifier
        guest_id: Guest ID (integer)
        role_id: Role ID (integer)

    Returns:
        True if successful
    """
    # Find role assignment
    role_assignment_store = get_role_assignment_store(tenant)
    assignments = await role_assignment_store.read_items(
        filter_by={"guest_id": guest_id, "role_id": role_id}
    )

    if not assignments:
        logger.warning(f"assign_role: role assignment not found for guest={guest_id}, role={role_id}")
        return False

    # SCIM provisioning
    from services.scim_observer import get_scim_observer
    observer = get_scim_observer()
    if observer:
        await observer.provision_guest_on_first_acceptance(guest_id, role_id)

    return True


async def revoke_role(tenant: str, guest_id: int, role_id: int) -> bool:
    """Revoke role assignment: delete assignment (+ junctions) and handle SCIM cleanup.

    Args:
        tenant: Tenant identifier
        guest_id: Guest ID (integer)
        role_id: Role ID (integer)

    Returns:
        True if successful
    """
    role_assignment_store = get_role_assignment_store(tenant)

    assignments = await role_assignment_store.read_items(
        filter_by={"guest_id": guest_id, "role_id": role_id}
    )
    if not assignments:
        logger.warning(f"revoke_role: no role assignment for guest={guest_id}, role={role_id}")
        return False

    await delete_role_assignment(tenant, assignments[0])

    # Check remaining role assignments for this guest
    remaining = await role_assignment_store.read_items(filter_by={"guest_id": guest_id})

    # SCIM cleanup via observer
    from services.scim_observer import get_scim_observer
    observer = get_scim_observer()
    if observer:
        await observer.cleanup_guest_on_last_revocation(guest_id, role_id, not remaining)

    # Delete guest if no more role assignments
    if not remaining:
        guest_store = get_guest_store(tenant)
        await guest_store.delete_item({"id": guest_id})
        logger.info(f"revoke_role: deleted guest {guest_id} (no more role assignments)")

    return True
