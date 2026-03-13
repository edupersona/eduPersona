"""
Tests for storage layer and Tortoise ORM operations.
"""
from datetime import date, timedelta
import pytest
from services.storage.storage import (
    get_guest_store,
    get_role_store,
    get_role_assignment_store,
    get_invitation_store,
    create_role_assignment,
    create_invitation,
    accept_invitation,
    assign_role,
    revoke_role,
    update_role_assignment,
    validate_assignment_end_date,
)


@pytest.mark.storage
async def test_create_guest(test_tenant):
    """Test creating a guest"""
    guest_store = get_guest_store(test_tenant)

    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "newguest@example.com",
        "given_name": "New",
        "family_name": "Guest",
        "email": "newguest@example.com",
    })

    assert guest
    assert guest["user_id"] == "newguest@example.com"
    assert "id" in guest

    # Verify derived field via read (display_name is computed on read)
    guests = await guest_store.read_items(filter_by={"id": guest["id"]})
    assert guests[0]["display_name"] == "New Guest"


@pytest.mark.storage
async def test_create_role(test_tenant):
    """Test creating a role"""
    role_store = get_role_store(test_tenant)
    role_end = (date.today() + timedelta(days=365)).isoformat()

    role = await role_store.create_item({
        "tenant": test_tenant,
        "scim_id": "test-scim-123",
        "name": "Test Role",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test Sender",
        "redirect_url": "https://example.com",
        "redirect_text": "Go to Example",
        "role_end_date": role_end,
    })

    assert role
    assert role["name"] == "Test Role"
    assert role["scim_id"] == "test-scim-123"
    assert role["redirect_url"] == "https://example.com"
    assert role["role_end_date"] == role_end


@pytest.mark.storage
async def test_create_role_assignment(test_tenant, sample_guest, sample_role):
    """Test creating a role assignment"""
    role_assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        sample_role["id"],
    )

    assert isinstance(role_assignment, dict)
    assert role_assignment["guest_id"] == sample_guest["id"]
    assert role_assignment["role_id"] == sample_role["id"]

    # Verify in database
    ra_store = get_role_assignment_store(test_tenant)
    assignments = await ra_store.read_items(filter_by={"id": role_assignment["id"]})
    assert len(assignments) == 1


@pytest.mark.storage
async def test_create_invitation(test_tenant, sample_role_assignment):
    """Test creating an invitation linked to role assignment"""
    guest_id = sample_role_assignment["guest_id"]

    invitation = await create_invitation(
        test_tenant,
        guest_id,
        [sample_role_assignment["id"]],  # list of role_assignment_ids
        "test@example.com",
    )

    # Should return invitation dict with 32-character hex code
    assert isinstance(invitation, dict)
    assert len(invitation["code"]) == 32
    assert invitation["status"] == "pending"

    # Verify invitation was created in database
    invitation_store = get_invitation_store(test_tenant)
    invitations = await invitation_store.read_items(filter_by={"code": invitation["code"]})

    assert len(invitations) == 1
    assert invitations[0]["status"] == "pending"
    assert invitations[0]["guest_id"] == guest_id


@pytest.mark.storage
async def test_accept_invitation(test_tenant, sample_invitation):
    """Test accepting an invitation"""
    invitation_store = get_invitation_store(test_tenant)

    # Get the invitation before acceptance
    invitations_before = await invitation_store.read_items(filter_by={"code": sample_invitation})
    assert invitations_before[0]["status"] == "pending"

    # Accept the invitation
    result = await accept_invitation(test_tenant, sample_invitation)
    assert result is True

    # Verify status changed to accepted
    invitations_after = await invitation_store.read_items(filter_by={"code": sample_invitation})
    assert invitations_after[0]["status"] == "accepted"
    assert invitations_after[0]["accepted_at"] is not None


@pytest.mark.storage
async def test_assign_role(test_tenant, sample_role_assignment):
    """Test assigning a role (legacy function for SCIM provisioning)"""
    guest_id = sample_role_assignment["guest_id"]
    role_id = sample_role_assignment["role_id"]

    # assign_role should succeed when role assignment exists
    result = await assign_role(test_tenant, guest_id, role_id)
    assert result is True


@pytest.mark.storage
async def test_revoke_role(test_tenant, sample_role_assignment):
    """Test revoking role assignment"""
    guest_id = sample_role_assignment["guest_id"]
    role_id = sample_role_assignment["role_id"]
    ra_store = get_role_assignment_store(test_tenant)

    # Verify role assignment exists before revocation
    assignments_before = await ra_store.read_items(
        filter_by={"guest_id": guest_id, "role_id": role_id}
    )
    assert len(assignments_before) == 1

    # Revoke the role
    await revoke_role(test_tenant, guest_id, role_id)

    # Verify role assignment was deleted
    assignments_after = await ra_store.read_items(
        filter_by={"guest_id": guest_id, "role_id": role_id}
    )
    assert len(assignments_after) == 0


@pytest.mark.storage
async def test_read_with_join_fields(test_tenant, sample_role_assignment):
    """Test reading role assignments with joined guest and role data"""
    ra_store = get_role_assignment_store(test_tenant)

    assignments = await ra_store.read_items(
        join_fields=["guest__user_id", "guest__given_name", "guest__family_name", "role__name", "role__redirect_url"]
    )

    assert len(assignments) > 0
    assignment = assignments[0]

    # Verify join fields are present (flat dict with __ keys)
    assert "guest__user_id" in assignment
    assert "guest__given_name" in assignment
    assert "role__name" in assignment
    assert "role__redirect_url" in assignment

    # Verify derived field calc_guest_name is computed
    assert "calc_guest_name" in assignment

    # Verify values
    assert assignment["guest__user_id"] == "testguest@example.com"
    assert assignment["role__name"] == "Test Role"


@pytest.mark.storage
async def test_multitenancy_isolation(test_tenant):
    """Test that tenants are isolated from each other"""
    guest_store_uva = get_guest_store("uva")
    guest_store_vu = get_guest_store("vu")

    # Create guest in UVA tenant
    await guest_store_uva.create_item({
        "tenant": "uva",
        "user_id": "uva@example.com",
        "email": "uva@example.com",
    })

    # Create guest in VU tenant
    await guest_store_vu.create_item({
        "tenant": "vu",
        "user_id": "vu@example.com",
        "email": "vu@example.com",
    })

    # Verify UVA store only sees UVA guests
    uva_guests = await guest_store_uva.read_items()
    assert len(uva_guests) == 1
    assert uva_guests[0]["user_id"] == "uva@example.com"

    # Verify VU store only sees VU guests
    vu_guests = await guest_store_vu.read_items()
    assert len(vu_guests) == 1
    assert vu_guests[0]["user_id"] == "vu@example.com"


# --- Role date validation and capping tests ---

@pytest.mark.storage
async def test_validate_assignment_end_date_valid():
    """Validation passes when end_date <= role_end_date"""
    # Should not raise
    validate_assignment_end_date("2026-06-01", "2026-12-31")
    validate_assignment_end_date("2026-12-31", "2026-12-31")  # equal is valid


@pytest.mark.storage
async def test_validate_assignment_end_date_invalid():
    """Validation raises ValueError when end_date > role_end_date"""
    with pytest.raises(ValueError, match="End date cannot be later"):
        validate_assignment_end_date("2027-01-01", "2026-12-31")


@pytest.mark.storage
async def test_create_role_assignment_with_valid_dates(test_tenant, sample_guest, sample_role):
    """Create assignment with end_date within role_end_date succeeds"""
    role_end = sample_role["role_end_date"]
    assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        sample_role["id"],
        start_date="2026-01-01",
        end_date=role_end,  # exactly at limit
    )
    assert assignment["end_date"] == role_end


@pytest.mark.storage
async def test_create_role_assignment_end_date_exceeds_role(test_tenant, sample_guest, sample_role):
    """Create assignment with end_date > role_end_date raises ValueError"""
    role_end = date.fromisoformat(sample_role["role_end_date"])
    too_late = (role_end + timedelta(days=1)).isoformat()

    with pytest.raises(ValueError, match="End date cannot be later"):
        await create_role_assignment(
            test_tenant,
            sample_guest["id"],
            sample_role["id"],
            end_date=too_late,
        )


@pytest.mark.storage
async def test_update_role_assignment_with_valid_dates(test_tenant, sample_role_assignment, sample_role):
    """Update assignment dates within role_end_date succeeds"""
    updated = await update_role_assignment(
        test_tenant,
        sample_role_assignment["id"],
        start_date="2026-02-01",
        end_date=sample_role["role_end_date"],
    )
    assert updated["start_date"] == "2026-02-01"
    assert updated["end_date"] == sample_role["role_end_date"]


@pytest.mark.storage
async def test_update_role_assignment_end_date_exceeds_role(test_tenant, sample_role_assignment, sample_role):
    """Update assignment with end_date > role_end_date raises ValueError"""
    role_end = date.fromisoformat(sample_role["role_end_date"])
    too_late = (role_end + timedelta(days=1)).isoformat()

    with pytest.raises(ValueError, match="End date cannot be later"):
        await update_role_assignment(
            test_tenant,
            sample_role_assignment["id"],
            start_date="2026-01-01",
            end_date=too_late,
        )


@pytest.mark.storage
async def test_role_end_date_caps_assignment_end_dates(test_tenant, sample_guest):
    """When role_end_date moves earlier, assignment end_dates are capped"""
    role_store = get_role_store(test_tenant)
    ra_store = get_role_assignment_store(test_tenant)

    # Create role with end date far in future
    original_role_end = (date.today() + timedelta(days=730)).isoformat()
    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "Capping Test Role",
        "redirect_url": "https://example.com",
        "redirect_text": "Go",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test",
        "role_end_date": original_role_end,
    })

    # Create assignment with end_date = original role_end
    assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        role["id"],         # type: ignore
        end_date=original_role_end,
    )
    assert assignment["end_date"] == original_role_end

    # Move role_end_date earlier
    new_role_end = (date.today() + timedelta(days=365)).isoformat()
    await role_store.update_item(role["id"], {"role_end_date": new_role_end})         # type: ignore

    # Verify assignment end_date was capped
    updated_assignments = await ra_store.read_items(filter_by={"id": assignment["id"]})
    assert updated_assignments[0]["end_date"] == new_role_end


@pytest.mark.storage
async def test_role_end_date_no_cap_when_within_range(test_tenant, sample_guest):
    """Assignment end_date unchanged when already within new role_end_date"""
    role_store = get_role_store(test_tenant)
    ra_store = get_role_assignment_store(test_tenant)

    # Create role with end date far in future
    original_role_end = (date.today() + timedelta(days=730)).isoformat()
    role = await role_store.create_item({
        "tenant": test_tenant,
        "name": "No-Cap Test Role",
        "redirect_url": "https://example.com",
        "redirect_text": "Go",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test",
        "role_end_date": original_role_end,
    })

    # Create assignment with end_date well before role_end
    assignment_end = (date.today() + timedelta(days=180)).isoformat()
    assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        role["id"],         # type: ignore
        end_date=assignment_end,
    )

    # Move role_end_date earlier, but still after assignment end
    new_role_end = (date.today() + timedelta(days=365)).isoformat()
    await role_store.update_item(role["id"], {"role_end_date": new_role_end})         # type: ignore

    # Verify assignment end_date is unchanged
    updated_assignments = await ra_store.read_items(filter_by={"id": assignment["id"]})
    assert updated_assignments[0]["end_date"] == assignment_end
