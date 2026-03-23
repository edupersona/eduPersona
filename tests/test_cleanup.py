"""
Tests for cleanup service - expired roles, assignments, and invitations.
"""
from datetime import date, timedelta
import pytest
from services.cleanup import (
    cleanup_expired_roles,
    cleanup_expired_role_assignments,
    expire_pending_invitations,
    run_all_cleanup_tasks,
)
from domain.stores import (
    get_guest_store,
    get_role_store,
    get_role_assignment_store,
    get_invitation_store,
)
from domain.invitation_flow import create_role_assignment, create_invitation
from domain.models import Invitation
from ng_rdm.utils.helpers import now_utc


@pytest.mark.storage
async def test_cleanup_expired_role(test_tenant):
    """Expired role and its assignments should be deleted"""
    guest_store = get_guest_store(test_tenant)
    role_store = get_role_store(test_tenant)
    ra_store = get_role_assignment_store(test_tenant)

    # Create guest
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "cleanup-guest@example.com",
        "email": "cleanup-guest@example.com",
    })

    # Create expired role (role_end_date in the past)
    expired_date = (date.today() - timedelta(days=1)).isoformat()
    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Expired Role",
        "redirect_url": "https://example.com",
        "redirect_text": "Go",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test",
        "role_end_date": expired_date,
    })

    # Create role assignment
    await create_role_assignment(test_tenant, guest["id"], role["id"])

    # Run cleanup
    result = await cleanup_expired_roles(test_tenant)

    assert result["roles_deleted"] == 1
    assert result["assignments_deleted"] == 1
    assert result["guests_deleted"] == 1

    # Verify role is gone
    roles = await role_store.read_items(filter_by={"id": role["id"]})
    assert len(roles) == 0

    # Verify guest is gone (had no other assignments)
    guests = await guest_store.read_items(filter_by={"id": guest["id"]})
    assert len(guests) == 0


@pytest.mark.storage
async def test_cleanup_expired_role_keeps_guest_with_other_assignments(test_tenant):
    """Guest should be kept if they have other active role assignments"""
    guest_store = get_guest_store(test_tenant)
    role_store = get_role_store(test_tenant)

    # Create guest
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "multi-role-guest@example.com",
        "email": "multi-role-guest@example.com",
    })

    # Create expired role
    expired_date = (date.today() - timedelta(days=1)).isoformat()
    expired_role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Expired Role",
        "redirect_url": "https://example.com",
        "redirect_text": "Go",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test",
        "role_end_date": expired_date,
    })

    # Create active role
    active_date = (date.today() + timedelta(days=365)).isoformat()
    active_role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Active Role",
        "redirect_url": "https://example.com",
        "redirect_text": "Go",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test",
        "role_end_date": active_date,
    })

    # Create both role assignments
    await create_role_assignment(test_tenant, guest["id"], expired_role["id"])
    await create_role_assignment(test_tenant, guest["id"], active_role["id"])

    # Run cleanup
    result = await cleanup_expired_roles(test_tenant)

    assert result["roles_deleted"] == 1
    assert result["assignments_deleted"] == 1
    assert result["guests_deleted"] == 0  # Guest kept due to active role

    # Verify guest still exists
    guests = await guest_store.read_items(filter_by={"id": guest["id"]})
    assert len(guests) == 1


@pytest.mark.storage
async def test_cleanup_expired_assignment(test_tenant, sample_guest, sample_role):
    """Expired role assignment should be deleted"""
    ra_store = get_role_assignment_store(test_tenant)
    guest_store = get_guest_store(test_tenant)

    # Create assignment with expired end_date
    expired_date = (date.today() - timedelta(days=1)).isoformat()
    assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        sample_role["id"],
        end_date=expired_date,
    )

    # Run cleanup
    result = await cleanup_expired_role_assignments(test_tenant)

    assert result["assignments_deleted"] == 1
    assert result["guests_deleted"] == 1  # Guest has no other assignments

    # Verify assignment is gone
    assignments = await ra_store.read_items(filter_by={"id": assignment["id"]})
    assert len(assignments) == 0

    # Verify guest is gone
    guests = await guest_store.read_items(filter_by={"id": sample_guest["id"]})
    assert len(guests) == 0


@pytest.mark.storage
async def test_cleanup_assignment_no_end_date_not_deleted(test_tenant, sample_guest, sample_role):
    """Assignment without end_date should not be deleted"""
    ra_store = get_role_assignment_store(test_tenant)

    # Create assignment without end_date
    assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        sample_role["id"],
    )

    # Run cleanup
    result = await cleanup_expired_role_assignments(test_tenant)

    assert result["assignments_deleted"] == 0

    # Verify assignment still exists
    assignments = await ra_store.read_items(filter_by={"id": assignment["id"]})
    assert len(assignments) == 1


@pytest.mark.storage
async def test_expire_pending_invitation(test_tenant, sample_role_assignment):
    """Old pending invitation should be expired"""
    invitation_store = get_invitation_store(test_tenant)
    guest_id = sample_role_assignment["guest_id"]

    # Create invitation
    invitation = await create_invitation(
        test_tenant,
        guest_id,
        [sample_role_assignment["id"]],
        "test@example.com",
    )

    # Manually backdate invited_at to make it old
    await Invitation.filter(code=invitation["code"]).update(
        invited_at=now_utc() - timedelta(days=31)
    )

    # Run cleanup with 30-day expiration
    result = await expire_pending_invitations(test_tenant, expiration_days=30)

    assert result["invitations_expired"] == 1

    # Verify status changed
    invitations = await invitation_store.read_items(filter_by={"code": invitation["code"]})
    assert invitations[0]["status"] == "expired"


@pytest.mark.storage
async def test_accepted_invitation_not_expired(test_tenant, sample_role_assignment):
    """Accepted invitations should not be expired"""
    invitation_store = get_invitation_store(test_tenant)
    guest_id = sample_role_assignment["guest_id"]

    # Create invitation
    invitation = await create_invitation(
        test_tenant,
        guest_id,
        [sample_role_assignment["id"]],
        "test@example.com",
    )

    # Set status to accepted and backdate
    await Invitation.filter(code=invitation["code"]).update(
        status="accepted",
        invited_at=now_utc() - timedelta(days=31)
    )

    # Run cleanup
    result = await expire_pending_invitations(test_tenant, expiration_days=30)

    assert result["invitations_expired"] == 0

    # Verify status unchanged
    invitations = await invitation_store.read_items(filter_by={"code": invitation["code"]})
    assert invitations[0]["status"] == "accepted"


@pytest.mark.storage
async def test_recent_pending_invitation_not_expired(test_tenant, sample_role_assignment):
    """Recent pending invitations should not be expired"""
    invitation_store = get_invitation_store(test_tenant)
    guest_id = sample_role_assignment["guest_id"]

    # Create invitation (invited_at is auto-set to now)
    invitation = await create_invitation(
        test_tenant,
        guest_id,
        [sample_role_assignment["id"]],
        "test@example.com",
    )

    # Run cleanup with 30-day expiration
    result = await expire_pending_invitations(test_tenant, expiration_days=30)

    assert result["invitations_expired"] == 0

    # Verify status unchanged
    invitations = await invitation_store.read_items(filter_by={"code": invitation["code"]})
    assert invitations[0]["status"] == "pending"


@pytest.mark.storage
async def test_run_all_cleanup_tasks(test_tenant):
    """Run all cleanup tasks for a tenant"""
    result = await run_all_cleanup_tasks(test_tenant)

    assert "tenants_processed" in result
    assert "totals" in result
    assert "errors" in result
    assert len(result["tenants_processed"]) == 1
    assert result["tenants_processed"][0]["tenant"] == test_tenant


@pytest.mark.api
async def test_cleanup_api_requires_key(api_client, monkeypatch):
    """Cleanup API should reject requests without valid key"""
    # Ensure no key is configured
    monkeypatch.setattr("routes.api.cleanup.config", {"cleanup_api_key": ""})
    response = await api_client.post("/api/v1/cleanup")
    # Without cleanup_api_key configured, should return 503
    assert response.status_code == 503


@pytest.mark.api
async def test_cleanup_api_invalid_key(api_client, monkeypatch):
    """Cleanup API should reject invalid API key"""
    # Configure a key
    monkeypatch.setattr("services.cleanup.config", {"cleanup_api_key": "valid-key"})
    monkeypatch.setattr("routes.api.cleanup.config", {"cleanup_api_key": "valid-key"})

    response = await api_client.post("/api/v1/cleanup?api_key=wrong-key")
    assert response.status_code == 401
