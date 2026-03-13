"""
Cleanup service for expired roles, role assignments, and invitations.
Triggered via API endpoint by external scheduler/cron.
"""
from datetime import date, timedelta

from ng_loba.models.models import Role, RoleAssignment, Invitation, InvitationRoleAssignment
from ng_loba.utils import logger
from ng_loba.utils.helpers import now_utc
from services.settings import config
from services.storage.storage import (
    get_role_store,
    get_role_assignment_store,
    get_invitation_store,
    get_guest_store,
)
from services.storage.scim_observer import get_scim_observer
from services.tenant import get_available_tenants


async def cleanup_expired_roles(tenant: str) -> dict:
    """Delete roles where role_end_date < today, with cascade.

    Returns:
        dict with roles_deleted, assignments_deleted, guests_deleted counts
    """
    today = date.today()
    role_store = get_role_store(tenant)
    role_assignment_store = get_role_assignment_store(tenant)
    guest_store = get_guest_store(tenant)
    observer = get_scim_observer()

    expired_roles = await Role.filter(tenant=tenant, role_end_date__lt=today)
    roles_deleted = 0
    assignments_deleted = 0
    guests_deleted = 0

    for role in expired_roles:
        role_id = role.id
        # Get all assignments for this role
        assignments = await RoleAssignment.filter(role_id=role_id)

        for assignment in assignments:
            guest_id = assignment.guest_id  # type: ignore[attr-defined]
            # Delete junction records first (FK constraint)
            await InvitationRoleAssignment.filter(role_assignment_id=assignment.id).delete()
            # Delete assignment via store (triggers observer)
            await role_assignment_store.delete_item({"id": assignment.id})
            assignments_deleted += 1

            # SCIM cleanup
            remaining = await role_assignment_store.read_items(filter_by={"guest_id": guest_id})
            if observer:
                await observer.cleanup_guest_on_last_revocation(guest_id, role_id, not remaining)

            # Delete guest if no more assignments
            if not remaining:
                await guest_store.delete_item({"id": guest_id})
                guests_deleted += 1
                logger.info(f"cleanup: deleted guest {guest_id} (no more role assignments)")

        # Delete the role itself
        await role_store.delete_item({"id": role_id})
        roles_deleted += 1
        logger.info(f"cleanup: deleted expired role {role_id}")

    return {
        "roles_deleted": roles_deleted,
        "assignments_deleted": assignments_deleted,
        "guests_deleted": guests_deleted,
    }


async def cleanup_expired_role_assignments(tenant: str) -> dict:
    """Delete role assignments where end_date < today.

    Returns:
        dict with assignments_deleted, guests_deleted counts
    """
    today = date.today()
    role_assignment_store = get_role_assignment_store(tenant)
    guest_store = get_guest_store(tenant)
    observer = get_scim_observer()

    expired_assignments = await RoleAssignment.filter(
        tenant=tenant, end_date__lt=today, end_date__isnull=False
    )
    assignments_deleted = 0
    guests_deleted = 0

    for assignment in expired_assignments:
        guest_id = assignment.guest_id  # type: ignore[attr-defined]
        role_id = assignment.role_id  # type: ignore[attr-defined]

        # Delete junction records first (FK constraint)
        await InvitationRoleAssignment.filter(role_assignment_id=assignment.id).delete()
        # Delete assignment via store
        await role_assignment_store.delete_item({"id": assignment.id})
        assignments_deleted += 1

        # SCIM cleanup
        remaining = await role_assignment_store.read_items(filter_by={"guest_id": guest_id})
        if observer:
            await observer.cleanup_guest_on_last_revocation(guest_id, role_id, not remaining)

        # Delete guest if no more assignments
        if not remaining:
            await guest_store.delete_item({"id": guest_id})
            guests_deleted += 1
            logger.info(f"cleanup: deleted guest {guest_id} (no more role assignments)")

    return {
        "assignments_deleted": assignments_deleted,
        "guests_deleted": guests_deleted,
    }


async def expire_pending_invitations(tenant: str, expiration_days: int | None = None) -> dict:
    """Set status='expired' for stale pending invitations.

    Args:
        tenant: Tenant identifier
        expiration_days: Days after which pending invitations expire (default from config)

    Returns:
        dict with invitations_expired count
    """
    if expiration_days is None:
        expiration_days = int(config.get("invitation_expiration_days") or 30)

    cutoff = now_utc() - timedelta(days=expiration_days)
    invitation_store = get_invitation_store(tenant)

    pending_invitations = await Invitation.filter(
        tenant=tenant, status="pending", invited_at__lt=cutoff
    )
    invitations_expired = 0

    for invitation in pending_invitations:
        await invitation_store.update_item(invitation.id, {"status": "expired"})
        invitations_expired += 1
        logger.info(f"cleanup: expired invitation {invitation.code}")

    return {"invitations_expired": invitations_expired}


async def run_all_cleanup_tasks(tenant: str | None = None) -> dict:
    """Run all cleanup tasks for one or all tenants.

    Args:
        tenant: Specific tenant to clean up, or None for all tenants

    Returns:
        dict with tenants_processed, totals, and errors
    """
    tenants = [tenant] if tenant else get_available_tenants()
    results = []
    errors = []
    totals = {
        "roles_deleted": 0,
        "assignments_deleted": 0,
        "guests_deleted": 0,
        "invitations_expired": 0,
    }

    for t in tenants:
        try:
            logger.info(f"cleanup: starting cleanup for tenant {t}")

            # Run all cleanup tasks
            roles_result = await cleanup_expired_roles(t)
            assignments_result = await cleanup_expired_role_assignments(t)
            invitations_result = await expire_pending_invitations(t)

            tenant_result = {
                "tenant": t,
                **roles_result,
                **assignments_result,
                **invitations_result,
            }
            results.append(tenant_result)

            # Accumulate totals
            totals["roles_deleted"] += roles_result["roles_deleted"]
            totals["assignments_deleted"] += (
                roles_result["assignments_deleted"] + assignments_result["assignments_deleted"]
            )
            totals["guests_deleted"] += (
                roles_result["guests_deleted"] + assignments_result["guests_deleted"]
            )
            totals["invitations_expired"] += invitations_result["invitations_expired"]

            logger.info(f"cleanup: completed for tenant {t}")

        except Exception as e:
            logger.error(f"cleanup: error for tenant {t}: {e}")
            errors.append({"tenant": t, "error": str(e)})

    return {
        "tenants_processed": results,
        "totals": totals,
        "errors": errors,
    }
