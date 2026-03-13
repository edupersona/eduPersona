"""
Storage layer using ng_loba TortoiseStore with SQLite backend
"""
import uuid
from datetime import date

from tortoise.functions import Count, Max

from ng_loba.models.models import Role, Guest, GuestAttribute, RoleAssignment, Invitation, InvitationRoleAssignment
from ng_loba.store import store_registry
from ng_loba.store.multitenancy import MultitenantTortoiseStore, set_valid_tenants
from ng_loba.store.orm import TortoiseStore
from ng_loba.utils import logger
from ng_loba.utils.helpers import now_utc, utc_datetime_to_str, date_to_str
from services.i18n import _


def _derive_guest_statuses(assignment_count: int, has_accepted: bool, has_pending: bool) -> list[str]:
    """Derive guest statuses from aggregates. Returns list of applicable status strings."""
    statuses = []
    if assignment_count > 0:
        statuses.append("active_roles")
    if has_accepted:
        statuses.append("verified")
    elif has_pending:
        statuses.append("invited")
    return statuses


class EnrichedGuestStore(MultitenantTortoiseStore[Guest]):
    """Guest store enriched with role assignment aggregates and derived status."""

    async def read_items(self, filter_by=None, q=None, join_fields=[]):
        items = await super().read_items(filter_by, q, join_fields)
        if not items:
            return items
        guest_ids = [item['id'] for item in items]

        # Role assignment aggregates
        ra_aggregates = await RoleAssignment.filter(
            guest_id__in=guest_ids
        ).group_by('guest_id').annotate(
            assignment_count=Count('id'),
            max_end_date=Max('end_date'),
        ).values('guest_id', 'assignment_count', 'max_end_date')
        ra_map = {a['guest_id']: a for a in ra_aggregates}

        # Invitation status per guest (compute in Python for simplicity)
        invitations = await Invitation.filter(guest_id__in=guest_ids).values('guest_id', 'status')
        inv_map: dict[int, dict] = {}
        for inv in invitations:
            gid = inv['guest_id']
            if gid not in inv_map:
                inv_map[gid] = {'has_accepted': False, 'has_pending': False}
            if inv['status'] == 'accepted':
                inv_map[gid]['has_accepted'] = True
            elif inv['status'] == 'pending':
                inv_map[gid]['has_pending'] = True

        for item in items:
            guest_id = item['id']
            ra = ra_map.get(guest_id, {})
            inv = inv_map.get(guest_id, {})

            assignment_count = ra.get('assignment_count', 0)
            max_end_date = ra.get('max_end_date')

            item['assignment_count'] = assignment_count
            item['max_end_date'] = date_to_str(max_end_date) if max_end_date else ''
            item['guest_statuses'] = _derive_guest_statuses(
                assignment_count,
                bool(inv.get('has_accepted')),
                bool(inv.get('has_pending')),
            )

        return items


class RoleStore(MultitenantTortoiseStore[Role]):
    """Role store with business logic for cascading end_date caps."""

    async def _update_item(self, id: int, partial_item: dict) -> dict | None:
        new_role_end = partial_item.get('role_end_date')

        if new_role_end:
            old_role = await self.read_item_by_id(id)
            old_role_end = old_role.get('role_end_date') if old_role else None

            # If role_end_date moved earlier, cap assignment end_dates
            if old_role_end and new_role_end < old_role_end:
                await self._cap_assignment_end_dates(id, new_role_end)

        return await super()._update_item(id, partial_item)

    async def _cap_assignment_end_dates(self, role_id: int, new_end: str):
        """Cap all role_assignment end_dates to not exceed new_end."""
        if not self.tenant:
            return
        role_assignment_store = get_role_assignment_store(self.tenant)
        assignments = await role_assignment_store.read_items(filter_by={"role_id": role_id})

        for ra in assignments:
            if ra.get('end_date') and ra['end_date'] > new_end:
                await role_assignment_store.update_item(ra['id'], {"end_date": new_end})


class EnrichedInvitationStore(MultitenantTortoiseStore[Invitation]):
    """Invitation store enriched with role_names from linked role assignments."""

    def __init__(self, model, tenant: str):
        super().__init__(model, tenant=tenant)
        self._role_store: MultitenantTortoiseStore[Role] | None = None

    def set_role_store(self, role_store: MultitenantTortoiseStore[Role]):
        """Set reference to role store for looking up role names."""
        self._role_store = role_store

    async def read_items(self, filter_by=None, q=None, join_fields=[]):
        items = await super().read_items(filter_by, q, join_fields)
        if not items:
            return items

        # Get all junction records for these invitations
        invitation_ids = [item['id'] for item in items]
        junctions = await InvitationRoleAssignment.filter(
            invitation_id__in=invitation_ids
        ).prefetch_related('role_assignment__role').all()

        # Build map: invitation_id -> [role_names]
        inv_roles: dict[int, list[str]] = {inv_id: [] for inv_id in invitation_ids}
        for j in junctions:
            role_name = ""
            if hasattr(j.role_assignment, 'role') and j.role_assignment.role:
                role_name = j.role_assignment.role.name
            elif self._role_store:
                # Fallback: look up role via store
                ra = j.role_assignment
                if ra and ra.role_id:
                    role = await self._role_store.read_item_by_id(ra.role_id)
                    role_name = role.get('name', '') if role else ''
            if role_name:
                inv_roles[j.invitation_id].append(role_name)        # type: ignore

        # Add role_names to each item
        for item in items:
            names = inv_roles.get(item['id'], [])
            item['role_names'] = ", ".join(names) if names else "-"

        return items


def initialize_multitenancy() -> None:
    """Initialize multi-tenancy system - register all configured tenants"""
    from services.settings import config

    # Extract tenant identifiers from settings
    tenants = list(config.tenants.keys()) if hasattr(config, 'tenants') else ["uva"]
    set_valid_tenants(tenants)
    logger.info(f"Registered tenants: {tenants}")


def _ensure_tenant_stores(tenant: str) -> None:
    """Lazy-init stores for tenant if not already initialized

    Args:
        tenant: Tenant identifier

    Note:
        This is called automatically by store getter functions.
        Stores are created on first access per tenant.
    """
    try:
        # Check if stores exist for this tenant
        store_registry.get_store(tenant, 'guest')
        return  # Already initialized
    except:     # noqa
        # Create and register stores for this tenant
        guest_store = EnrichedGuestStore(Guest, tenant=tenant)
        role_store = RoleStore(Role, tenant=tenant)
        role_assignment_store = MultitenantTortoiseStore(RoleAssignment, tenant=tenant)
        invitation_store = EnrichedInvitationStore(Invitation, tenant=tenant)
        invitation_store.set_role_store(role_store)
        guest_attr_store = TortoiseStore(GuestAttribute)  # no tenant field; scoped via guest FK

        guest_store.set_derived_fields(
            derived_fields={
                'display_name': lambda row: ((row.get('given_name') or '') + ' ' + (row.get('family_name') or '')).strip()
            },
        )

        # Configure derived fields for role assignment store
        role_assignment_store.set_derived_fields(
            derived_fields={
                'calc_guest_name': lambda row: ((row.get('guest__given_name') or '') + ' ' + (row.get('guest__family_name') or '')).strip() or row.get('guest__user_id') or ''
            },
            dependencies=['guest__given_name', 'guest__family_name', 'guest__user_id']
        )

        # Configure derived fields for invitation store
        invitation_store.set_derived_fields(
            derived_fields={
                'calc_guest_name': lambda row: ((row.get('guest__given_name') or '') + ' ' + (row.get('guest__family_name') or '')).strip() or row.get('guest__user_id') or ''
            },
            dependencies=['guest__given_name', 'guest__family_name', 'guest__user_id']
        )

        store_registry.register_store(tenant, 'guest', guest_store)
        store_registry.register_store(tenant, 'role', role_store)
        store_registry.register_store(tenant, 'role_assignment', role_assignment_store)
        store_registry.register_store(tenant, 'invitation', invitation_store)
        store_registry.register_store(tenant, 'guest_attribute', guest_attr_store)

        # Initialize SCIM observer for this tenant
        from services.storage.scim_observer import initialize_scim_observer
        initialize_scim_observer(tenant)

        logger.info(f"Initialized stores for tenant: {tenant}")


# Store accessor functions with lazy initialization
def get_guest_store(tenant: str) -> MultitenantTortoiseStore[Guest]:
    _ensure_tenant_stores(tenant)
    return store_registry.get_store(tenant, 'guest')  # type: ignore[return-value]


def get_role_store(tenant: str) -> MultitenantTortoiseStore[Role]:
    _ensure_tenant_stores(tenant)
    return store_registry.get_store(tenant, 'role')  # type: ignore[return-value]


def get_role_assignment_store(tenant: str) -> MultitenantTortoiseStore[RoleAssignment]:
    _ensure_tenant_stores(tenant)
    return store_registry.get_store(tenant, 'role_assignment')  # type: ignore[return-value]


def get_invitation_store(tenant: str) -> MultitenantTortoiseStore[Invitation]:
    _ensure_tenant_stores(tenant)
    return store_registry.get_store(tenant, 'invitation')  # type: ignore[return-value]


def get_guest_attribute_store(tenant: str) -> MultitenantTortoiseStore[GuestAttribute]:
    _ensure_tenant_stores(tenant)
    return store_registry.get_store(tenant, 'guest_attribute')  # type: ignore[return-value]


# Legacy alias for backward compatibility
def get_membership_store(tenant: str) -> MultitenantTortoiseStore[RoleAssignment]:
    """Deprecated: use get_role_assignment_store instead"""
    return get_role_assignment_store(tenant)


# Business logic functions

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
    from services.storage.scim_observer import get_scim_observer
    observer = get_scim_observer()
    if observer:
        for ra_id in role_assignment_ids:
            ra = await RoleAssignment.get(id=ra_id)
            await observer.provision_guest_on_first_acceptance(ra.guest_id, ra.role_id)     # type: ignore

    return True


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
    from services.storage.scim_observer import get_scim_observer
    observer = get_scim_observer()
    if observer:
        await observer.provision_guest_on_first_acceptance(guest_id, role_id)

    return True


async def revoke_role(tenant: str, guest_id: int, role_id: int) -> bool:
    """Revoke role assignment: delete assignment and handle SCIM cleanup.

    Args:
        tenant: Tenant identifier
        guest_id: Guest ID (integer)
        role_id: Role ID (integer)

    Returns:
        True if successful
    """
    role_assignment_store = get_role_assignment_store(tenant)

    # Find role assignment
    assignments = await role_assignment_store.read_items(
        filter_by={"guest_id": guest_id, "role_id": role_id}
    )

    if not assignments:
        logger.warning(f"revoke_role: no role assignment for guest={guest_id}, role={role_id}")
        return False

    assignment = assignments[0]

    # Delete junction records first (foreign key constraint)
    await InvitationRoleAssignment.filter(role_assignment_id=assignment["id"]).delete()

    # Delete role assignment
    await role_assignment_store.delete_item(assignment)

    # Check remaining role assignments for this guest
    remaining = await role_assignment_store.read_items(filter_by={"guest_id": guest_id})

    # SCIM cleanup via observer
    from services.storage.scim_observer import get_scim_observer
    observer = get_scim_observer()
    if observer:
        await observer.cleanup_guest_on_last_revocation(guest_id, role_id, not remaining)

    # Delete guest if no more role assignments
    if not remaining:
        guest_store = get_guest_store(tenant)
        await guest_store.delete_item({"id": guest_id})
        logger.info(f"revoke_role: deleted guest {guest_id} (no more role assignments)")

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
