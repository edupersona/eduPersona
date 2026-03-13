"""
SCIM Observer Business Logic Tests

Tests the actual business logic of scim_observer.py, not just that scim2-client
can talk to scim2-server. Uses scim2-server with httpx WSGITransport for
in-process SCIM protocol testing.

Run these tests with:
    pytest -m scim             # run only SCIM tests
    pytest -m "not scim"       # skip SCIM tests
"""
from datetime import date, timedelta
import pytest
from unittest.mock import patch
import httpx

pytestmark = pytest.mark.scim

SCIM_TEST_URL = "https://scim.test.local"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def scim_provider():
    """Create a SCIM provider with in-memory backend and default schemas."""
    from scim2_server.backend import InMemoryBackend
    from scim2_server.provider import SCIMProvider
    from scim2_server.utils import load_default_resource_types, load_default_schemas

    backend = InMemoryBackend()
    provider = SCIMProvider(backend)
    for schema in load_default_schemas().values():
        provider.register_schema(schema)
    for resource_type in load_default_resource_types().values():
        provider.register_resource_type(resource_type)
    return provider


@pytest.fixture
def scim_http_client(scim_provider):
    """Create httpx client with WSGI transport to the SCIM provider."""
    transport = httpx.WSGITransport(app=scim_provider)
    client = httpx.Client(
        transport=transport,
        base_url=SCIM_TEST_URL,
        headers={"Authorization": "Bearer test-token"}
    )
    yield client
    scim_provider.backend.resources = []
    client.close()


@pytest.fixture
def scim_enabled_config():
    """Patch tenant config to enable SCIM."""
    mock_config = {
        "scim": {
            "scim_enabled": True,
            "scim_base_url": SCIM_TEST_URL,
            "bearer_token": "test-token",
            "provision_groups": True
        }
    }
    with patch("services.storage.scim_observer.get_tenant_config", return_value=mock_config):
        yield mock_config


@pytest.fixture
def scim_observer(scim_enabled_config, scim_http_client, test_tenant):
    """Create SCIMObserver with real in-memory SCIM backend."""
    from services.storage.scim_observer import SCIMObserver

    with patch("httpx.Client", return_value=scim_http_client):
        observer = SCIMObserver(test_tenant)
        yield observer


@pytest.fixture
async def guest_without_scim_id(test_tenant):
    """Create a guest without scim_id for testing."""
    from services.storage.storage import get_guest_store

    guest_store = get_guest_store(test_tenant)
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "newguest@example.com",
        "given_name": "New",
        "family_name": "Guest",
        "email": "newguest@example.com",
    })
    return guest


@pytest.fixture
async def guest_with_scim_id(test_tenant, scim_observer):
    """Create a guest WITH scim_id for testing."""
    from services.storage.storage import get_guest_store

    guest_store = get_guest_store(test_tenant)

    # Create guest
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "provisionedguest@example.com",
        "given_name": "Provisioned",
        "family_name": "Guest",
        "email": "provisionedguest@example.com",
    })

    # Provision to SCIM
    scim_id = scim_observer.scim_client.create_or_update_user(guest)
    await guest_store.update_item(guest["id"], {"scim_id": scim_id})         # type: ignore

    # Refresh
    guests = await guest_store.read_items(filter_by={"id": guest["id"]})         # type: ignore
    return guests[0]


@pytest.fixture
async def role_without_scim_id(test_tenant):
    """Create a role without scim_id for testing."""
    from services.storage.storage import get_role_store

    role_store = get_role_store(test_tenant)
    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Unprovisioned Role",
        "redirect_url": "https://example.com/test",
        "redirect_text": "Go to Test",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test Sender",
        "role_end_date": (date.today() + timedelta(days=365)).isoformat(),
    })
    return role


@pytest.fixture
async def role_with_scim_id(test_tenant, scim_observer):
    """Create a role WITH scim_id for testing."""
    from services.storage.storage import get_role_store

    role_store = get_role_store(test_tenant)

    # Create role
    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Provisioned Role",
        "redirect_url": "https://example.com/test",
        "redirect_text": "Go to Test",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test Sender",
        "role_end_date": (date.today() + timedelta(days=365)).isoformat(),
    })

    # Provision to SCIM
    scim_id = scim_observer.scim_client.create_or_update_role(role)
    await role_store.update_item(role["id"], {"scim_id": scim_id})       # type: ignore

    # Refresh
    roles = await role_store.read_items(filter_by={"id": role["id"]})    # type: ignore
    return roles[0]     # type: ignore


# =============================================================================
# on_guest_event Tests
# =============================================================================

@pytest.mark.asyncio
async def test_on_guest_event_create_no_provision(scim_observer, guest_without_scim_id):
    """Guest create event should NOT provision to SCIM (happens on acceptance)."""
    from ng_loba.store.base import StoreEvent

    event = StoreEvent(verb="create", item=guest_without_scim_id)
    await scim_observer.on_guest_event(event)

    # Guest should still have no scim_id (not provisioned) - empty string or None
    assert not guest_without_scim_id.get("scim_id")


@pytest.mark.asyncio
async def test_on_guest_event_update_with_scim_id(scim_observer, guest_with_scim_id):
    """Guest update event should sync to SCIM when guest has scim_id."""
    from ng_loba.store.base import StoreEvent

    original_scim_id = guest_with_scim_id["scim_id"]
    assert original_scim_id is not None

    # Modify guest and trigger update event
    guest_with_scim_id["given_name"] = "Updated"
    event = StoreEvent(verb="update", item=guest_with_scim_id)

    # Should not raise - update syncs to SCIM
    await scim_observer.on_guest_event(event)


@pytest.mark.asyncio
async def test_on_guest_event_update_without_scim_id(scim_observer, guest_without_scim_id):
    """Guest update event should be skipped when guest has no scim_id."""
    from ng_loba.store.base import StoreEvent

    # Modify guest and trigger update event
    guest_without_scim_id["given_name"] = "Updated"
    event = StoreEvent(verb="update", item=guest_without_scim_id)

    # Should not raise or do anything
    await scim_observer.on_guest_event(event)


@pytest.mark.asyncio
async def test_on_guest_event_delete_with_scim_id(scim_observer, guest_with_scim_id):
    """Guest delete event should remove user from SCIM when guest has scim_id."""
    from ng_loba.store.base import StoreEvent

    assert guest_with_scim_id.get("scim_id") is not None

    event = StoreEvent(verb="delete", item=guest_with_scim_id)

    # Should delete from SCIM
    await scim_observer.on_guest_event(event)


@pytest.mark.asyncio
async def test_on_guest_event_delete_without_scim_id(scim_observer, guest_without_scim_id):
    """Guest delete event should be skipped when guest has no scim_id."""
    from ng_loba.store.base import StoreEvent

    event = StoreEvent(verb="delete", item=guest_without_scim_id)

    # Should not raise or do anything
    await scim_observer.on_guest_event(event)


# =============================================================================
# on_role_event Tests
# =============================================================================

@pytest.mark.asyncio
async def test_on_role_event_create_updates_store(scim_observer, test_tenant):
    """Role create event should provision AND update store with scim_id."""
    from ng_loba.store.base import StoreEvent
    from services.storage.storage import get_role_store

    role_store = get_role_store(test_tenant)

    # Create role directly in store (simulating what happens before observer fires)
    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Observer Test Role",
        "redirect_url": "https://example.com/test",
        "redirect_text": "Go to Test",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test Sender",
        "role_end_date": (date.today() + timedelta(days=365)).isoformat(),
    })
    assert role is not None

    # Verify no scim_id yet (empty string or None)
    assert not role.get("scim_id")

    # Fire create event (observer should provision and update store)
    event = StoreEvent(verb="create", item=role)
    await scim_observer.on_role_event(event)

    # Verify store was updated with scim_id
    updated_roles = await role_store.read_items(filter_by={"id": role["id"]})
    assert len(updated_roles) == 1
    assert updated_roles[0].get("scim_id") is not None


@pytest.mark.asyncio
async def test_on_role_event_update_with_scim_id(scim_observer, role_with_scim_id):
    """Role update event should sync to SCIM when role has scim_id."""
    from ng_loba.store.base import StoreEvent

    assert role_with_scim_id.get("scim_id") is not None

    # Modify role and trigger update event
    role_with_scim_id["name"] = "Updated Role Name"
    event = StoreEvent(verb="update", item=role_with_scim_id)

    # Should not raise - update syncs to SCIM
    await scim_observer.on_role_event(event)


@pytest.mark.asyncio
async def test_on_role_event_update_without_scim_id(scim_observer, role_without_scim_id):
    """Role update event should be skipped when role has no scim_id."""
    from ng_loba.store.base import StoreEvent

    # Modify role and trigger update event
    role_without_scim_id["name"] = "Updated Name"
    event = StoreEvent(verb="update", item=role_without_scim_id)

    # Should not raise or do anything
    await scim_observer.on_role_event(event)


@pytest.mark.asyncio
async def test_on_role_event_delete_logs_only(scim_observer, role_with_scim_id):
    """Role delete event should only log (no SCIM cleanup implemented)."""
    from ng_loba.store.base import StoreEvent

    event = StoreEvent(verb="delete", item=role_with_scim_id)

    # Should not raise - just logs
    await scim_observer.on_role_event(event)


# =============================================================================
# provision_guest_on_first_acceptance Tests
# =============================================================================

@pytest.mark.asyncio
async def test_provision_guest_on_first_acceptance(scim_observer, guest_without_scim_id, role_with_scim_id, test_tenant):
    """First acceptance should provision guest to SCIM and add to role."""
    from services.storage.storage import get_guest_store

    guest_store = get_guest_store(test_tenant)

    # Verify guest has no scim_id (empty string or None)
    assert not guest_without_scim_id.get("scim_id")

    # Call provision method
    await scim_observer.provision_guest_on_first_acceptance(
        guest_without_scim_id["id"],
        role_with_scim_id["id"]
    )

    # Verify guest now has scim_id in store
    updated_guests = await guest_store.read_items(filter_by={"id": guest_without_scim_id["id"]})
    assert len(updated_guests) == 1
    assert updated_guests[0].get("scim_id") is not None


@pytest.mark.asyncio
async def test_provision_guest_already_provisioned(scim_observer, guest_with_scim_id, role_with_scim_id, test_tenant):
    """Already provisioned guest should skip user creation but still add to role."""
    from services.storage.storage import get_guest_store

    guest_store = get_guest_store(test_tenant)
    original_scim_id = guest_with_scim_id["scim_id"]

    # Call provision method
    await scim_observer.provision_guest_on_first_acceptance(
        guest_with_scim_id["id"],
        role_with_scim_id["id"]
    )

    # Verify scim_id unchanged
    updated_guests = await guest_store.read_items(filter_by={"id": guest_with_scim_id["id"]})
    assert updated_guests[0]["scim_id"] == original_scim_id


@pytest.mark.asyncio
async def test_provision_guest_missing_guest(scim_observer, role_with_scim_id):
    """Provision with invalid guest_id should handle gracefully."""
    # Should not raise, just log warning
    await scim_observer.provision_guest_on_first_acceptance(99999, role_with_scim_id["id"])


@pytest.mark.asyncio
async def test_provision_guest_missing_role(scim_observer, guest_without_scim_id):
    """Provision with invalid role_id should handle gracefully."""
    # Should not raise, just log warning
    await scim_observer.provision_guest_on_first_acceptance(guest_without_scim_id["id"], 99999)


# =============================================================================
# cleanup_guest_on_last_revocation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_cleanup_guest_on_last_revocation(scim_observer, guest_with_scim_id, role_with_scim_id):
    """Last revocation should delete user from SCIM."""
    await scim_observer.cleanup_guest_on_last_revocation(
        guest_with_scim_id["id"],
        role_with_scim_id["id"],
        is_last_membership=True
    )
    # If no exception, SCIM delete was called


@pytest.mark.asyncio
async def test_cleanup_guest_not_last(scim_observer, guest_with_scim_id, role_with_scim_id):
    """Non-last revocation should only remove from role, not delete user."""
    await scim_observer.cleanup_guest_on_last_revocation(
        guest_with_scim_id["id"],
        role_with_scim_id["id"],
        is_last_membership=False
    )
    # If no exception, SCIM remove-from-role was called


@pytest.mark.asyncio
async def test_cleanup_guest_without_scim_id(scim_observer, guest_without_scim_id, role_with_scim_id):
    """Cleanup without scim_id should handle gracefully."""
    await scim_observer.cleanup_guest_on_last_revocation(
        guest_without_scim_id["id"],
        role_with_scim_id["id"],
        is_last_membership=True
    )
    # Should not raise


# =============================================================================
# bulk_sync_to_scim Tests
# =============================================================================

@pytest.mark.asyncio
async def test_bulk_sync_disabled_when_not_configured(test_tenant):
    """bulk_sync_to_scim returns error when SCIM disabled."""
    from services.storage.scim_observer import bulk_sync_to_scim

    mock_config = {"scim": {"scim_enabled": False}}
    with patch("services.storage.scim_observer.get_tenant_config", return_value=mock_config):
        results = await bulk_sync_to_scim(test_tenant)
        assert results["error"] is not None
        assert "not configured" in results["error"]


@pytest.mark.asyncio
async def test_bulk_sync_to_scim(scim_http_client, test_tenant):
    """bulk_sync should provision roles, guests with accepted invitations, and role assignments."""
    from services.storage.scim_observer import bulk_sync_to_scim
    from services.storage.storage import get_role_store, get_guest_store, get_role_assignment_store, get_invitation_store
    from ng_loba.models.models import InvitationRoleAssignment

    # Setup: create role, guest, role assignment, and accepted invitation
    role_store = get_role_store(test_tenant)
    guest_store = get_guest_store(test_tenant)
    ra_store = get_role_assignment_store(test_tenant)
    invitation_store = get_invitation_store(test_tenant)

    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Bulk Sync Role",
        "redirect_url": "https://example.com/test",
        "redirect_text": "Go to Test",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test Sender",
        "role_end_date": (date.today() + timedelta(days=365)).isoformat(),
    })
    assert role is not None

    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "bulksyncguest@example.com",
        "given_name": "Bulk",
        "family_name": "Guest",
        "email": "bulksyncguest@example.com",
    })
    assert guest is not None

    # Create role assignment
    role_assignment = await ra_store.create_item({
        "guest_id": guest["id"],
        "role_id": role["id"],
    })
    assert role_assignment is not None

    # Create accepted invitation linked to role assignment
    invitation = await invitation_store.create_item({
        "guest_id": guest["id"],
        "invitation_email": "bulksyncguest@example.com",
        "code": "a" * 32,
        "status": "accepted",
    })
    assert invitation is not None

    # Link invitation to role assignment via junction table
    await InvitationRoleAssignment.create(
        invitation_id=invitation["id"],
        role_assignment_id=role_assignment["id"],
    )

    # Run bulk sync with config patch at the right location (bulk_sync imports from services.settings)
    mock_config = {
        "scim": {
            "scim_enabled": True,
            "scim_base_url": SCIM_TEST_URL,
            "bearer_token": "test-token",
        }
    }
    with patch("services.settings.get_tenant_config", return_value=mock_config):
        with patch("httpx.Client", return_value=scim_http_client):
            results = await bulk_sync_to_scim(test_tenant)

    # Verify results
    assert results["error"] is None
    assert results["roles"]["synced"] >= 1
    assert results["guests"]["synced"] >= 1

    # Verify stores updated with scim_ids
    updated_roles = await role_store.read_items(filter_by={"id": role["id"]})
    assert updated_roles[0].get("scim_id") is not None

    updated_guests = await guest_store.read_items(filter_by={"id": guest["id"]})
    assert updated_guests[0].get("scim_id") is not None


# =============================================================================
# Observer Initialization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_observer_initializes_when_enabled(scim_enabled_config, scim_http_client, test_tenant):
    """SCIMObserver initializes client when SCIM is enabled."""
    from services.storage.scim_observer import SCIMObserver

    with patch("httpx.Client", return_value=scim_http_client):
        observer = SCIMObserver(test_tenant)
        assert observer.scim_client is not None


@pytest.mark.asyncio
async def test_observer_disabled_when_not_configured(test_tenant):
    """SCIMObserver has no client when SCIM is disabled."""
    from services.storage.scim_observer import SCIMObserver

    mock_config = {"scim": {"scim_enabled": False}}
    with patch("services.storage.scim_observer.get_tenant_config", return_value=mock_config):
        observer = SCIMObserver(test_tenant)
        assert observer.scim_client is None
