"""
Storage layer using ng_loba TortoiseStore with SQLite backend
"""
from tortoise.functions import Count, Max

from domain.models import Role, Guest, GuestAttribute, RoleAssignment, Invitation, InvitationRoleAssignment
from ng_rdm import mt_store_registry as store_registry
from ng_rdm.store.multitenancy import MultitenantTortoiseStore, set_valid_tenants
from ng_rdm.store.orm import TortoiseStore
from ng_rdm.utils import logger
from ng_rdm.utils.helpers import date_to_str


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
    tenants = list(config.tenants.keys())
    set_valid_tenants(tenants)
    logger.info(f"Registered tenants: {tenants}")


def _ensure_tenant_stores(tenant: str) -> None:
    """Lazy-init stores for tenant if not already initialized"""
    try:
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
        from services.scim_observer import initialize_scim_observer
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


def get_guest_attribute_store(tenant: str) -> MultitenantTortoiseStore[GuestAttribute]:  # type: ignore
    _ensure_tenant_stores(tenant)
    return store_registry.get_store(tenant, 'guest_attribute')  # type: ignore[return-value]
