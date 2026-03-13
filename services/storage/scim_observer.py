"""
SCIM observer for automatic provisioning when store events occur
"""
from ng_loba.store.base import StoreEvent
from ng_loba.utils import logger
from services.settings import get_tenant_config


class SCIMClient:
    """SCIM client wrapper using scim2-client"""

    def __init__(self, base_url: str, bearer_token: str):
        from httpx import Client
        from scim2_client.engines.httpx import SyncSCIMClient
        from scim2_models import PatchOp, PatchOperation, SearchRequest

        http_client = Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {bearer_token}"}
        )
        self.client = SyncSCIMClient(http_client)
        self.client.discover()  # Auto-discover server schemas including Enterprise extensions
        self.User = self.client.get_resource_model("User")
        self.Group = self.client.get_resource_model("Group")
        self.SearchRequest = SearchRequest
        self.PatchOp = PatchOp
        self.PatchOperation = PatchOperation

    def _build_user(self, guest: dict, scim_id: str | None = None):
        """Build SCIM User from guest data.

        Uses dicts for nested objects because discover() creates model-specific
        Name and Email classes that differ from scim2_models defaults.
        """
        display_name = (
            guest.get("display_name")  # derived field if read through store
            or ((guest.get("given_name") or '') + ' ' + (guest.get("family_name") or '')).strip()
            or None
        )
        email = guest.get("email", "")
        return self.User(
            id=scim_id,  # type: ignore
            external_id=guest.get("user_id"),  # type: ignore
            user_name=guest.get("user_id") or "",  # type: ignore
            name={  # type: ignore
                "formatted": display_name,
                "familyName": guest.get("family_name"),
                "givenName": guest.get("given_name"),
            },
            display_name=display_name,  # type: ignore
            active=True,  # type: ignore
            emails=[{"value": email}] if email else []  # type: ignore
        )

    def _scim_operation(self, operation: str, entity_type: str, entity_id: str, *args) -> str | bool | None:
        """Execute SCIM operation with error handling"""
        try:
            response = getattr(self.client, operation)(*args)
            if operation == "create" and hasattr(response, 'id'):
                logger.info(f"SCIM: Created {entity_type} {entity_id} -> SCIM ID: {response.id}")
                return response.id
            else:  # replace, modify, delete
                logger.info(f"SCIM: {operation} {entity_type} {entity_id}")
                return True
        except Exception as e:
            from scim2_client import SCIMRequestError, SCIMResponseError
            if isinstance(e, (SCIMRequestError, SCIMResponseError)):
                error_msg = e.message
                logger.error(f"SCIM: {operation} {entity_type} {entity_id} failed: {error_msg}")
            else:
                logger.error(f"SCIM: {operation} {entity_type} {entity_id} exception: {e}")
            return None if operation == "create" else False

    def create_or_update_user(self, guest: dict) -> str | None:
        """Create or update SCIM User (upsert), return SCIM ID"""
        user_id = guest.get("user_id")
        if not user_id:
            return None

        # Check if user exists by external_id
        try:
            search_req = self.SearchRequest(filter=f'externalId eq "{user_id}"')  # type: ignore
            result = self.client.query(self.User, search_request=search_req)
            if result and hasattr(result, 'resources') and result.resources:    # type: ignore
                existing_scim_id = result.resources[0].id       # type: ignore
                logger.info(f"SCIM: User {user_id} exists with SCIM ID {existing_scim_id}, updating")
                # Update existing user
                user = self._build_user(guest, existing_scim_id)
                self._scim_operation("replace", "user", user_id, user)
                return existing_scim_id
        except Exception as e:
            logger.warning(f"SCIM: User lookup for {user_id} failed: {e}")

        # Create new user
        user = self._build_user(guest)
        result = self._scim_operation("create", "user", user_id, user)
        return result if isinstance(result, str) else None

    def update_user(self, guest: dict) -> bool:
        """Update existing SCIM User"""
        scim_id = guest.get("scim_id")
        user_id = guest.get("user_id")
        if not scim_id or not user_id:
            return False
        user = self._build_user(guest, scim_id)
        result = self._scim_operation("replace", "user", user_id, user)
        return result if isinstance(result, bool) else False

    def delete_user(self, scim_id: str, user_id: str) -> bool:
        """Delete SCIM User"""
        if not scim_id:
            return False
        result = self._scim_operation("delete", "user", user_id, self.User, scim_id)
        return result if isinstance(result, bool) else False

    def create_or_update_role(self, role: dict) -> str | None:
        """Create or update SCIM Group (upsert), return SCIM ID"""
        role_name = role.get("name")
        role_id = str(role.get("id", ""))

        if not role_name:
            return None

        # Check if role exists by external_id (using role UUID as external_id)
        try:
            search_req = self.SearchRequest(filter=f'externalId eq "{role_id}"')  # type: ignore
            result = self.client.query(self.Group, search_request=search_req)
            if result and hasattr(result, 'resources') and result.resources:    # type: ignore
                existing_scim_id = result.resources[0].id   # type: ignore
                logger.info(f"SCIM: Role {role_name} exists with SCIM ID {existing_scim_id}, updating")
                # Update existing role
                scim_group = self.Group(
                    id=existing_scim_id,  # type: ignore
                    external_id=role_id,  # type: ignore
                    display_name=role_name  # type: ignore
                )
                self._scim_operation("replace", "group", role_name, scim_group)
                return existing_scim_id
        except Exception as e:
            logger.warning(f"SCIM: Role lookup for {role_name} failed: {e}")

        # Create new role
        scim_group = self.Group(
            external_id=role_id,  # type: ignore
            display_name=role_name  # type: ignore
        )
        result = self._scim_operation("create", "group", role_name, scim_group)
        return result if isinstance(result, str) else None

    def update_role(self, role: dict) -> bool:
        """Update existing SCIM Group"""
        scim_id = role.get("scim_id")
        role_name = role.get("name")
        role_id = str(role.get("id", ""))
        if not scim_id or not role_name:
            return False
        scim_group = self.Group(
            id=scim_id,  # type: ignore
            external_id=role_id,  # type: ignore
            display_name=role_name  # type: ignore
        )
        result = self._scim_operation("replace", "group", role_name, scim_group)
        return result if isinstance(result, bool) else False

    def add_user_to_group(self, guest_scim_id: str, group_scim_id: str, user_id: str, group_name: str) -> bool:
        """Add user to group via PATCH"""
        if not guest_scim_id or not group_scim_id:
            return False
        patch = self.PatchOp[self.Group](   # type: ignore
            operations=[  # type: ignore
                self.PatchOperation(
                    op=self.PatchOperation.Op.add,
                    path="members",  # type: ignore
                    value=[{"value": guest_scim_id}]
                )
            ]
        )
        result = self._scim_operation(
            "modify", "membership",
            f"{user_id}->{group_name}",
            self.Group, group_scim_id, patch
        )
        return result if isinstance(result, bool) else False

    def remove_user_from_group(self, guest_scim_id: str, group_scim_id: str, user_id: str, group_name: str) -> bool:
        """Remove user from group via PATCH"""
        if not guest_scim_id or not group_scim_id:
            return False
        patch = self.PatchOp[self.Group](   # type: ignore
            operations=[  # type: ignore
                self.PatchOperation(
                    op=self.PatchOperation.Op.remove,
                    path=f'members[value eq "{guest_scim_id}"]'  # type: ignore
                )
            ]
        )
        result = self._scim_operation(
            "modify", "membership",
            f"{user_id}<-{group_name}",
            self.Group, group_scim_id, patch
        )
        return result if isinstance(result, bool) else False


class SCIMObserver:
    """Observer that provisions entities to SCIM on store events"""

    def __init__(self, tenant: str):
        self.tenant = tenant
        self.scim_client = None
        self._init_scim_client()

    def _init_scim_client(self):
        """Initialize SCIM client if enabled"""
        try:
            tc = get_tenant_config(self.tenant)
            sc = tc.get('scim', {})

            if sc.get('scim_enabled') and sc.get('scim_base_url') and sc.get('bearer_token'):
                self.scim_client = SCIMClient(sc['scim_base_url'], sc['bearer_token'])
                logger.info(f"SCIM observer initialized for tenant {self.tenant}: {sc['scim_base_url']}")
            else:
                logger.info(f"SCIM observer disabled for tenant {self.tenant}")
        except Exception as e:
            logger.warning(f"Failed to initialize SCIM observer: {e}")

    async def on_guest_event(self, event: StoreEvent):
        """Handle guest store events"""
        if not self.scim_client:
            return

        item = event.item
        verb = event.verb

        if verb == "create":
            # Guest creation happens on invitation - don't provision yet
            # Provision happens on first membership acceptance (see assign_group)
            logger.debug(f"Guest created: {item.get('user_id')}, not provisioning yet")

        elif verb == "update":
            # Only sync if already provisioned (has scim_id)
            if item.get("scim_id"):
                self.scim_client.update_user(item)

        elif verb == "delete":
            # Clean up SCIM user if provisioned
            if item.get("scim_id"):
                self.scim_client.delete_user(item["scim_id"], item.get("user_id", ""))

    async def on_role_event(self, event: StoreEvent):
        """Handle role store events"""
        if not self.scim_client:
            return

        item = event.item
        verb = event.verb

        if verb == "create":
            # Provision role immediately on creation
            scim_id = self.scim_client.create_or_update_role(item)
            if scim_id:
                # Update role with scim_id
                from services.storage.storage import get_role_store
                role_store = get_role_store(self.tenant)
                await role_store.update_item(item["id"], {"scim_id": scim_id})

        elif verb == "update":
            # Sync metadata updates if already provisioned
            if item.get("scim_id"):
                self.scim_client.update_role(item)

        elif verb == "delete":
            # Note: Role deletion from SCIM not implemented
            # Roles are typically kept in SCIM for audit/history
            logger.debug(f"Role deleted: {item.get('name')}, SCIM cleanup not implemented")

    async def provision_guest_on_first_acceptance(self, guest_id, role_id):
        """Called by assign_role to provision guest on first role assignment acceptance"""
        if not self.scim_client:
            return

        from services.storage.storage import (
            get_role_store,
            get_guest_store,
        )

        guest_store = get_guest_store(self.tenant)
        role_store = get_role_store(self.tenant)

        # Get guest and role (filter by primary key 'id')
        guests = await guest_store.read_items(filter_by={"id": guest_id})
        roles = await role_store.read_items(filter_by={"id": role_id})

        if not guests or not roles:
            logger.warning("provision_guest: guest or role not found")
            return

        guest = guests[0]
        role = roles[0]

        # Provision guest if not already provisioned
        if not guest.get("scim_id"):
            scim_id = self.scim_client.create_or_update_user(guest)
            if scim_id:
                await guest_store.update_item(guest_id, {"scim_id": scim_id})
                guest["scim_id"] = scim_id
            else:
                logger.error(f"Failed to provision guest {guest.get('user_id')} to SCIM")
                return

        # Add to SCIM group
        if guest.get("scim_id") and role.get("scim_id"):
            self.scim_client.add_user_to_group(
                guest["scim_id"],
                role["scim_id"],
                guest.get("user_id", ""),
                role.get("name", "")
            )

    async def cleanup_guest_on_last_revocation(self, guest_id, role_id, is_last_membership: bool):
        """Called by revoke_role to handle SCIM cleanup"""
        if not self.scim_client:
            return

        from services.storage.storage import get_role_store, get_guest_store

        guest_store = get_guest_store(self.tenant)
        role_store = get_role_store(self.tenant)

        # Get guest and role (filter by primary key 'id')
        guests = await guest_store.read_items(filter_by={"id": guest_id})
        roles = await role_store.read_items(filter_by={"id": role_id})

        if not guests or not roles:
            return

        guest = guests[0]
        role = roles[0]

        if is_last_membership:
            # Delete user from SCIM
            if guest.get("scim_id"):
                self.scim_client.delete_user(guest["scim_id"], guest.get("user_id", ""))
                logger.info(f"Deleted guest {guest.get('user_id')} from SCIM (last membership)")
        else:
            # Just remove from this role
            if guest.get("scim_id") and role.get("scim_id"):
                self.scim_client.remove_user_from_group(
                    guest["scim_id"],
                    role["scim_id"],
                    guest.get("user_id", ""),
                    role.get("name", "")
                )
                logger.info(f"Removed guest {guest.get('user_id')} from SCIM role {role.get('name')}")


# Global SCIM observer instance (will be set by initialize_scim_observer)
scim_observer: SCIMObserver | None = None


def initialize_scim_observer(tenant: str):
    """Initialize and attach SCIM observer to stores"""
    global scim_observer

    from services.storage.storage import get_role_store, get_guest_store

    scim_observer = SCIMObserver(tenant)

    # Attach observers to stores
    guest_store = get_guest_store(tenant)
    role_store = get_role_store(tenant)

    guest_store.add_observer(scim_observer.on_guest_event)
    role_store.add_observer(scim_observer.on_role_event)

    logger.info(f"SCIM observer attached to guest and role stores for tenant {tenant}")


def get_scim_observer() -> SCIMObserver | None:
    """Get the global SCIM observer instance"""
    return scim_observer


async def bulk_sync_to_scim(tenant: str = "uva") -> dict:
    """Bulk sync all existing data to SCIM server

    Useful for initial setup or re-syncing after SCIM server issues.
    Syncs roles, guests with accepted invitations, and their role assignments.

    Returns:
        dict with sync statistics and any error message
    """
    from services.settings import get_tenant_config
    from services.storage.storage import (
        get_role_store,
        get_guest_store,
        get_invitation_store,
        get_role_assignment_store,
    )
    from ng_loba.models.models import InvitationRoleAssignment

    results = {
        'guests': {'synced': 0, 'failed': 0},
        'roles': {'synced': 0, 'failed': 0},
        'role_assignments': {'synced': 0, 'failed': 0},
        'error': None
    }

    try:
        # Check SCIM configuration
        tc = get_tenant_config(tenant)
        sc = tc.get('scim', {})

        if not sc.get('scim_enabled') or not sc.get('scim_base_url') or not sc.get('bearer_token'):
            results['error'] = "SCIM not configured or disabled"
            return results

        # Initialize SCIM client
        scim_client = SCIMClient(sc['scim_base_url'], sc['bearer_token'])

        # Get stores
        guest_store = get_guest_store(tenant)
        role_store = get_role_store(tenant)
        invitation_store = get_invitation_store(tenant)
        ra_store = get_role_assignment_store(tenant)

        # 1. Sync all roles to SCIM
        logger.info("Bulk sync: Starting role sync...")
        roles = await role_store.read_items()
        for role in roles:
            scim_id = scim_client.create_or_update_role(role)
            if scim_id:
                await role_store.update_item(role["id"], {"scim_id": scim_id})
                results['roles']['synced'] += 1
            else:
                results['roles']['failed'] += 1
                results['error'] = f"Failed to sync role {role.get('name')}"
                return results

        # 2. Sync all guests with accepted invitations to SCIM
        logger.info("Bulk sync: Starting guest sync...")
        # Only sync guests that have at least one accepted invitation
        invitations = await invitation_store.read_items(filter_by={"status": "accepted"})
        guest_ids_with_accepted = set(inv["guest_id"] for inv in invitations)

        for guest_id in guest_ids_with_accepted:
            guests = await guest_store.read_items(filter_by={"id": guest_id})
            if not guests:
                continue
            guest = guests[0]

            scim_id = scim_client.create_or_update_user(guest)
            if scim_id:
                await guest_store.update_item(guest_id, {"scim_id": scim_id})
                results['guests']['synced'] += 1
            else:
                results['guests']['failed'] += 1
                results['error'] = f"Failed to sync guest {guest.get('user_id')}"
                return results

        # 3. Sync role assignments for accepted invitations (add guests to roles in SCIM)
        logger.info("Bulk sync: Starting role assignment sync...")
        for invitation in invitations:
            # Get linked role assignments via junction table
            junctions = await InvitationRoleAssignment.filter(invitation_id=invitation["id"]).all()

            for junction in junctions:
                # Get role assignment
                ra_list = await ra_store.read_items(filter_by={"id": junction.role_assignment_id})
                if not ra_list:
                    continue
                ra = ra_list[0]

                # Get guest and role with scim_ids
                guests = await guest_store.read_items(filter_by={"id": invitation["guest_id"]})
                roles = await role_store.read_items(filter_by={"id": ra["role_id"]})

                if not guests or not roles:
                    continue

                guest = guests[0]
                role = roles[0]

                if guest.get("scim_id") and role.get("scim_id"):
                    success = scim_client.add_user_to_group(
                        guest["scim_id"],
                        role["scim_id"],
                        guest.get("user_id", ""),
                        role.get("name", "")
                    )
                    if success:
                        results['role_assignments']['synced'] += 1
                    else:
                        results['role_assignments']['failed'] += 1
                        results['error'] = f"Failed to sync role assignment for {guest.get('user_id')}"
                        return results

        logger.info(f"Bulk SCIM sync completed: {results}")
        return results

    except Exception as e:
        logger.error(f"Bulk SCIM sync failed: {e}")
        results['error'] = str(e)
        return results
