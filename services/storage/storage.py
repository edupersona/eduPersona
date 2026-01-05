import json
import os
import uuid
from datetime import datetime
from abc import ABC, abstractmethod

from services.logging import logger

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_STORAGE_FILE = os.path.join(_MODULE_DIR, 'storage.json')

ENTITY_SCHEMAS = {
    "guests": {"primary_key": "guest_id", "auto_timestamps": True},
    "groups": {"primary_key": "group_id", "auto_timestamps": False},
    "memberships": {"primary_key": "membership_id", "auto_timestamps": True}
}

class StorageProvider(ABC):
    @abstractmethod
    def find(self, entity_type: str, **criteria) -> list[dict]: pass
    @abstractmethod
    def find_one(self, entity_type: str, **criteria) -> dict | None: pass
    @abstractmethod
    def create(self, entity_type: str, entity_data: dict) -> str: pass
    @abstractmethod
    def update(self, entity_type: str, entity_id: str, **updates) -> bool: pass
    @abstractmethod
    def delete(self, entity_type: str, entity_id: str) -> bool: pass
    @abstractmethod
    def upsert(self, entity_type: str, criteria: dict, entity_data: dict) -> tuple[str, bool]: pass

class JSONStorageProvider(StorageProvider):
    def __init__(self, storage_file: str = _STORAGE_FILE):
        self.storage_file = storage_file

    def _load_storage(self) -> dict:
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {entity_type: [] for entity_type in ENTITY_SCHEMAS}

    def _save_storage(self, data: dict) -> None:
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _matches_criteria(self, item: dict, criteria: dict) -> bool:
        return all(item.get(key) == value for key, value in criteria.items())

    def _get_primary_key(self, entity_type: str) -> str:
        return ENTITY_SCHEMAS[entity_type]["primary_key"]

    def find(self, entity_type: str, **criteria) -> list[dict]:
        data = self._load_storage()
        entities = data.get(entity_type, [])
        if not criteria:
            return entities
        return [item for item in entities if self._matches_criteria(item, criteria)]

    def find_one(self, entity_type: str, **criteria) -> dict | None:
        matches = self.find(entity_type, **criteria)
        return matches[0] if matches else None

    def create(self, entity_type: str, entity_data: dict) -> str:
        data = self._load_storage()
        schema = ENTITY_SCHEMAS[entity_type]
        pk_field = schema["primary_key"]

        entity_id = entity_data.get(pk_field) or str(uuid.uuid4())
        if entity_type == "memberships":
            entity_id = entity_id.replace('-', '')

        entity = {pk_field: entity_id, **entity_data}

        if schema.get("auto_timestamps"):
            now = datetime.utcnow().isoformat() + 'Z'
            entity.setdefault("created_at", now)
            entity["updated_at"] = now

        data.setdefault(entity_type, []).append(entity)
        self._save_storage(data)
        return entity_id

    def update(self, entity_type: str, entity_id: str, **updates) -> bool:
        data = self._load_storage()
        pk_field = self._get_primary_key(entity_type)

        for entity in data.get(entity_type, []):
            if entity[pk_field] == entity_id:
                entity.update(updates)
                if ENTITY_SCHEMAS[entity_type].get("auto_timestamps"):
                    entity["updated_at"] = datetime.utcnow().isoformat() + 'Z'
                self._save_storage(data)
                return True
        return False

    def delete(self, entity_type: str, entity_id: str) -> bool:
        data = self._load_storage()
        pk_field = self._get_primary_key(entity_type)
        entities = data.get(entity_type, [])
        original_count = len(entities)

        data[entity_type] = [e for e in entities if e[pk_field] != entity_id]

        if len(data[entity_type]) < original_count:
            self._save_storage(data)
            return True
        return False

    def upsert(self, entity_type: str, criteria: dict, entity_data: dict) -> tuple[str, bool]:
        existing = self.find_one(entity_type, **criteria)
        if existing:
            pk_field = self._get_primary_key(entity_type)
            self.update(entity_type, existing[pk_field], **entity_data)
            return existing[pk_field], False
        else:
            entity_id = self.create(entity_type, {**criteria, **entity_data})
            return entity_id, True


class SCIMStorageProvider:
    """SCIM provisioning provider using scim2-client"""

    def __init__(self, base_url: str, bearer_token: str):
        from httpx import Client
        from scim2_client.engines.httpx import SyncSCIMClient
        from scim2_models import User, Group, SearchRequest

        http_client = Client(base_url=base_url, headers={"Authorization": f"Bearer {bearer_token}"})
        self.client = SyncSCIMClient(http_client, resource_models=[User, Group])
        self.client.register_naive_resource_types()
        self.User = User
        self.Group = Group
        self.SearchRequest = SearchRequest

    def _build_user(self, guest: dict, scim_id: str | None = None):
        """Build SCIM User from guest data"""
        from scim2_models import Name, Email
        emails = guest.get("emails", [])
        return self.User(
            id=scim_id,
            external_id=guest.get("guest_id"),
            user_name=guest.get("upn") or guest.get("guest_id") or "",
            name=Name(
                formatted=guest.get("name") or None,
                family_name=guest.get("family_name") or None,
                given_name=guest.get("given_name") or None
            ),
            display_name=guest.get("name") or None,
            active=True,
            # emails=[Email(value=email, type=None) for email in emails] if emails else None
            emails=[Email(value=email, type=None) for email in emails]
        )

    def _scim_operation(self, operation: str, entity_type: str, entity_id: str, *args) -> str | bool | None:
        """Execute SCIM operation with error handling (using raise_scim_errors=True default)"""
        try:
            response = getattr(self.client, operation)(*args)
            if operation == "create" and hasattr(response, 'id'):
                logger.info(f"SCIM: Created {entity_type} {entity_id} -> SCIM ID: {response.id}")
                return response.id
            else:  # replace, modify
                logger.info(f"SCIM: Updated {entity_type} {entity_id}")
                return True
        except Exception as e:
            from scim2_client import SCIMRequestError, SCIMResponseError
            if isinstance(e, (SCIMRequestError, SCIMResponseError)):
                error_msg = e.message
                logger.error(f"SCIM: {operation} {entity_type} {entity_id} failed: {error_msg}")
            else:
                logger.error(f"SCIM: {operation} {entity_type} {entity_id} exception: {e}")
            return None if operation == "create" else False

    def create_user(self, guest: dict) -> str | None:
        """Create or update SCIM User (upsert), return SCIM ID"""
        guest_id = guest.get("guest_id")

        if not guest_id:
            return None

        # If guest_id == externalId exists in SCIM, update instead
        try:
            search_req = self.SearchRequest(filter=f'externalId eq "{guest_id}"')
            result = self.client.query(self.User, search_request=search_req)
            if result and hasattr(result, 'resources') and result.resources:  # type: ignore
                existing_scim_id = result.resources[0].id  # type: ignore
                logger.info(f"SCIM: User {guest_id} already exists with SCIM ID {existing_scim_id}, updating")
                success = self.update_user({**guest, "scim_id": existing_scim_id})
                return existing_scim_id if success else None
        except Exception as e:
            logger.warning(f"SCIM: User lookup for {guest_id} failed: {e}")

        # Create new user
        user = self._build_user(guest)
        result = self._scim_operation("create", "user", guest_id, user)
        return result if isinstance(result, str) else None

    def update_user(self, guest: dict) -> bool:
        """Update SCIM User"""
        scim_id = guest.get("scim_id")
        guest_id = guest.get("guest_id")
        if not scim_id or not guest_id:
            return False
        user = self._build_user(guest, scim_id)
        result = self._scim_operation("replace", "user", guest_id, user)
        return result if isinstance(result, bool) else False

    def create_group(self, group: dict) -> str | None:
        """Create or update SCIM Group (upsert), return SCIM ID"""
        group_id = group.get("group_id")

        if not group_id:
            return None

        # If group_id == externalId exists in SCIM, update instead
        try:
            search_req = self.SearchRequest(filter=f'externalId eq "{group_id}"')
            result = self.client.query(self.Group, search_request=search_req)
            if result and hasattr(result, 'resources') and result.resources:  # type: ignore
                existing_scim_id = result.resources[0].id  # type: ignore
                logger.info(f"SCIM: Group {group_id} already exists with SCIM ID {existing_scim_id}, updating")
                success = self.update_group({**group, "scim_id": existing_scim_id})
                return existing_scim_id if success else None
        except Exception as e:
            logger.warning(f"SCIM: Group lookup for {group_id} failed: {e}")

        # Create new group
        scim_group = self.Group(external_id=group_id, display_name=group.get("name") or None)
        result = self._scim_operation("create", "group", group_id, scim_group)
        return result if isinstance(result, str) else None

    def update_group(self, group: dict) -> bool:
        """Update SCIM Group"""
        scim_id = group.get("scim_id")
        group_id = group.get("group_id")
        if not scim_id or not group_id:
            return False
        scim_group = self.Group(id=scim_id, external_id=group_id, display_name=group.get("name") or None)
        result = self._scim_operation("replace", "group", group_id, scim_group)
        return result if isinstance(result, bool) else False

    def add_user_to_group(self, guest_scim_id: str, group_scim_id: str, guest_id: str, group_id: str) -> bool:
        """Add user to group via PATCH"""
        if not guest_scim_id or not group_scim_id:
            return False
        from scim2_models import PatchOp, PatchOperation
        patch = PatchOp[self.Group](operations=[PatchOperation(op=PatchOperation.Op.add,
                                    path="members", value=[{"value": guest_scim_id}])])
        result = self._scim_operation("modify", "membership",
                                      f"{guest_id}->{group_id}", self.Group, group_scim_id, patch)
        return result if isinstance(result, bool) else False

    def remove_user_from_group(self, guest_scim_id: str, group_scim_id: str, guest_id: str, group_id: str) -> bool:
        """Remove user from group via PATCH"""
        if not guest_scim_id or not group_scim_id:
            return False
        from scim2_models import PatchOp, PatchOperation
        patch = PatchOp[self.Group](operations=[PatchOperation(op=PatchOperation.Op.remove,
                                    path=f"members[value eq \"{guest_scim_id}\"]")])
        result = self._scim_operation("modify", "membership",
                                      f"{guest_id}<-{group_id}", self.Group, group_scim_id, patch)
        return result if isinstance(result, bool) else False

    def delete_user(self, scim_id: str, guest_id: str) -> bool:
        """Delete SCIM User"""
        if not scim_id:
            return False
        result = self._scim_operation("delete", "user", guest_id, self.User, scim_id)
        return result if isinstance(result, bool) else False


class ChainedStorageProvider(StorageProvider):
    """Coordinates JSON storage with SCIM provisioning"""

    def __init__(self, json_provider: JSONStorageProvider, scim_provider: SCIMStorageProvider | None):
        self.json = json_provider
        self.scim = scim_provider

    def find(self, entity_type: str, **criteria) -> list[dict]:
        return self.json.find(entity_type, **criteria)

    def find_one(self, entity_type: str, **criteria) -> dict | None:
        return self.json.find_one(entity_type, **criteria)

    def create(self, entity_type: str, entity_data: dict) -> str:
        # Create in JSON storage first
        entity_id = self.json.create(entity_type, entity_data)

        # SCIM provisioning for groups only (guests provisioned on first membership acceptance)
        if self.scim and entity_type == "groups":
            # Get the created group to provision to SCIM
            group = self.json.find_one("groups", group_id=entity_id)
            if group:
                scim_id = self.scim.create_group(group)
                if scim_id:
                    # Update with SCIM ID
                    self.json.update("groups", entity_id, scim_id=scim_id)

        return entity_id

    def update(self, entity_type: str, entity_id: str, **updates) -> bool:
        # Update JSON storage
        success = self.json.update(entity_type, entity_id, **updates)

        if not success:
            return False

        # SCIM sync for metadata updates (only if already provisioned)
        if self.scim:
            if entity_type == "groups":
                group = self.json.find_one("groups", group_id=entity_id)
                if group and group.get("scim_id"):
                    self.scim.update_group(group)
            elif entity_type == "guests":
                guest = self.json.find_one("guests", guest_id=entity_id)
                # Only sync if already provisioned (has scim_id from assign_group)
                if guest and guest.get("scim_id"):
                    self.scim.update_user(guest)

        return True

    def delete(self, entity_type: str, entity_id: str) -> bool:
        # For now, just delete from JSON (SCIM delete not implemented)
        return self.json.delete(entity_type, entity_id)

    def upsert(self, entity_type: str, criteria: dict, entity_data: dict) -> tuple[str, bool]:
        existing = self.json.find_one(entity_type, **criteria)

        if existing:
            pk_field = ENTITY_SCHEMAS[entity_type]["primary_key"]
            self.update(entity_type, existing[pk_field], **entity_data)
            return existing[pk_field], False
        else:
            entity_id = self.create(entity_type, {**criteria, **entity_data})
            return entity_id, True


# Initialize storage providers
def _init_storage():
    """Initialize storage with SCIM support if configured"""
    from services.settings import get_tenant_config

    json_provider = JSONStorageProvider()
    scim_provider = None

    try:
        tenant_config = get_tenant_config('uva')
        sc = tenant_config.get('scim', {})

        if sc.scim_enabled:
            if sc.scim_base_url and sc.bearer_token:
                scim_provider = SCIMStorageProvider(sc.scim_base_url, sc.bearer_token)
                logger.info(f"SCIM provisioning enabled: {sc.scim_base_url}")
            else:
                logger.info("SCIM provisioning disabled (missing scim_base_url or bearer_token)")
        else:
            logger.info("SCIM provisioning disabled (scim_enabled=false)")

    except Exception as e:
        logger.warning(f"SCIM configuration not available: {e}")

    return ChainedStorageProvider(json_provider, scim_provider)

# Global storage provider instance
storage = _init_storage()

# Generic API functions with optional relation inclusion
def find(entity_type: str, with_relations: list[str] | None = None, **criteria) -> list[dict]:
    result = storage.find(entity_type, **criteria)
    if not with_relations:
        return result

    # Add related entities for memberships
    if entity_type == "memberships":
        for item in result:
            if "guest" in with_relations:
                item["guest"] = storage.find_one("guests", guest_id=item["guest_id"])
            if "group" in with_relations:
                item["group"] = storage.find_one("groups", group_id=item["group_id"])

            # Add formatted datetime fields
            def format_datetime(iso_string):
                if not iso_string:
                    return ''
                try:
                    dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
                    return dt.strftime('%d-%m-%Y %H:%M')
                except:     # noqa
                    return iso_string

            item["datetime_invited_formatted"] = format_datetime(item.get("invited_at", ""))
            item["datetime_accepted_formatted"] = format_datetime(item.get("accepted_at", ""))

    return result

def find_one(entity_type: str, with_relations: list[str] | None = None, **criteria) -> dict | None:
    result = storage.find_one(entity_type, **criteria)
    if not result or not with_relations:
        return result

    # Add related entities for memberships
    if entity_type == "memberships":
        if "guest" in with_relations:
            result["guest"] = storage.find_one("guests", guest_id=result["guest_id"])
        if "group" in with_relations:
            result["group"] = storage.find_one("groups", group_id=result["group_id"])

    return result

def create(entity_type: str, entity_data: dict) -> str:
    return storage.create(entity_type, entity_data)

def update(entity_type: str, entity_id: str, **updates) -> bool:
    return storage.update(entity_type, entity_id, **updates)

def delete(entity_type: str, entity_id: str) -> bool:
    return storage.delete(entity_type, entity_id)

def upsert(entity_type: str, criteria: dict, entity_data: dict) -> tuple[str, bool]:
    return storage.upsert(entity_type, criteria, entity_data)


# Helper function for invitation creation
def create_invitation(guest_id: str, group_id: str, invitation_mail_address: str) -> str:
    """Create an invitation, ensuring the guest exists first"""
    if not find_one("guests", guest_id=guest_id):
        create("guests", {"guest_id": guest_id})
    return create("memberships", {
        "guest_id": guest_id,
        "group_id": group_id,
        "invitation_email": invitation_mail_address,
        "status": "invited"
    })


def assign_group(guest_id: str, group_id: str) -> bool:
    """Accept membership: update JSON + provision to SCIM if needed"""
    # Find membership
    membership = find_one("memberships", guest_id=guest_id, group_id=group_id)
    if not membership:
        logger.warning(f"assign_group: membership not found for guest={guest_id}, group={group_id}")
        return False

    # Update status in JSON
    if not update("memberships", membership["membership_id"],
                  status="accepted", accepted_at=datetime.utcnow().isoformat() + 'Z'):
        logger.error(f"assign_group: failed to update membership {membership['membership_id']}")
        return False

    # SCIM provisioning
    if storage.scim:
        guest = find_one("guests", guest_id=guest_id)
        group = find_one("groups", group_id=group_id)

        if guest and group:
            # Provision guest if first acceptance
            if not guest.get("scim_id"):
                scim_id = storage.scim.create_user(guest)
                if scim_id:
                    update("guests", guest_id, scim_id=scim_id)
                    guest["scim_id"] = scim_id
                else:
                    logger.error(f"assign_group: failed to provision guest {guest_id} to SCIM")

            # Add to group
            if guest.get("scim_id") and group.get("scim_id"):
                storage.scim.add_user_to_group(
                    guest["scim_id"], group["scim_id"], guest_id, group_id
                )

    return True


def revoke_group(guest_id: str, group_id: str) -> bool:
    """Revoke membership: delete membership from JSON and remove from SCIM group"""
    # Find membership
    membership = find_one("memberships", guest_id=guest_id, group_id=group_id)
    if not membership or membership.get("status") != "accepted":
        logger.warning(f"revoke_group: no accepted membership for guest={guest_id}, group={group_id}")
        return False

    # Get guest and group info before deletion
    guest = find_one("guests", guest_id=guest_id)
    group = find_one("groups", group_id=group_id)

    # Delete membership from JSON
    if not delete("memberships", membership["membership_id"]):
        logger.error(f"revoke_group: failed to delete membership {membership['membership_id']}")
        return False

    # Check remaining memberships for this guest
    remaining = find("memberships", guest_id=guest_id, status="accepted")

    if storage.scim and guest and group:
        if remaining:
            # Guest still has memberships - just remove from this group in SCIM
            if guest.get("scim_id") and group.get("scim_id"):
                storage.scim.remove_user_from_group(
                    guest["scim_id"], group["scim_id"], guest_id, group_id
                )
                logger.info(f"revoke_group: removed guest {guest_id} from SCIM group {group_id}")
        else:
            # No more memberships - delete user from SCIM and JSON
            if guest.get("scim_id"):
                storage.scim.delete_user(guest["scim_id"], guest_id)
                logger.info(f"revoke_group: deleted guest {guest_id} from SCIM")

            # Delete guest from JSON storage
            delete("guests", guest_id)
            logger.info(f"revoke_group: deleted guest {guest_id} from storage (no more memberships)")

    return True


def sync_all_to_scim() -> dict:
    """Bulk sync all existing data to SCIM server (bypassing ChainedStorageProvider)"""
    from services.settings import get_tenant_config

    results = {
        'guests': {'created': 0, 'failed': 0},
        'groups': {'created': 0, 'failed': 0},
        'memberships': {'created': 0, 'failed': 0},
        'error': None
    }

    try:
        # Initialize providers directly
        json_provider = JSONStorageProvider()

        # Load SCIM config from settings
        tenant_config = get_tenant_config('uva')
        sc = tenant_config.scim

        if not sc.scim_enabled or not sc.scim_base_url or not sc.bearer_token:
            results['error'] = "SCIM not configured or disabled"
            return results

        scim_provider = SCIMStorageProvider(sc.scim_base_url, sc.bearer_token)

        # 1. Sync all guests to SCIM Users
        guests = json_provider.find("guests")
        for guest in guests:
            guest_id = guest.get("guest_id")
            if not guest_id:
                continue

            scim_id = scim_provider.create_user(guest)
            if scim_id:
                json_provider.update("guests", guest_id, scim_id=scim_id)
                results['guests']['created'] += 1
            else:
                results['guests']['failed'] += 1
                results['error'] = f"Failed to sync guest {guest_id}"
                return results

        # 2. Sync all groups to SCIM Groups
        groups = json_provider.find("groups")
        for group in groups:
            group_id = group.get("group_id")
            if not group_id:
                continue

            scim_id = scim_provider.create_group(group)
            if scim_id:
                json_provider.update("groups", group_id, scim_id=scim_id)
                results['groups']['created'] += 1
            else:
                results['groups']['failed'] += 1
                results['error'] = f"Failed to sync group {group_id}"
                return results

        # 3. Sync accepted memberships to SCIM
        memberships = json_provider.find("memberships", status="accepted")
        for membership in memberships:
            guest = json_provider.find_one("guests", guest_id=membership["guest_id"])
            group = json_provider.find_one("groups", group_id=membership["group_id"])

            if guest and group and guest.get("scim_id") and group.get("scim_id"):
                success = scim_provider.add_user_to_group(
                    guest["scim_id"],
                    group["scim_id"],
                    guest["guest_id"],
                    group["group_id"]
                )
                if success:
                    results['memberships']['created'] += 1
                else:
                    results['memberships']['failed'] += 1
                    results['error'] = f"Failed to sync membership {membership['membership_id']}"
                    return results

        logger.info(f"SCIM sync completed: {results}")
        return results

    except Exception as e:
        logger.error(f"SCIM sync failed: {e}")
        results['error'] = str(e)
        return results
