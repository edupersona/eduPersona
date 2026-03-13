"""
Integration tests that exercise multiple components together.
"""
import pytest
from nicegui.testing import User


@pytest.mark.integration
async def test_full_invitation_lifecycle(test_tenant, sample_role):
    """Test complete invitation lifecycle from creation to acceptance"""
    from services.storage.storage import (
        create_role_assignment,
        create_invitation,
        get_guest_store,
        get_invitation_store,
        accept_invitation,
    )

    # Step 1: Create guest first
    guest_store = get_guest_store(test_tenant)
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "integration@example.com",
        "email": "integration@example.com",
    })

    # Step 2: Create role assignment
    role_assignment = await create_role_assignment(
        test_tenant,
        guest["id"],         # type: ignore
        sample_role["id"],
    )

    # Step 3: Create invitation linked to role assignment
    invitation = await create_invitation(
        test_tenant,
        guest["id"],         # type: ignore
        [role_assignment["id"]],
        "integration@example.com"
    )
    invitation_code = invitation["code"]

    # Step 4: Verify invitation exists with "pending" status
    invitation_store = get_invitation_store(test_tenant)
    invitations = await invitation_store.read_items(filter_by={"code": invitation_code})
    assert len(invitations) == 1
    assert invitations[0]["status"] == "pending"

    # Step 5: Accept invitation
    await accept_invitation(test_tenant, invitation_code)

    # Step 6: Verify status changed to "accepted"
    accepted_invitations = await invitation_store.read_items(filter_by={"code": invitation_code})
    assert accepted_invitations[0]["status"] == "accepted"
    assert accepted_invitations[0]["accepted_at"] is not None


@pytest.mark.integration
@pytest.mark.slow
async def test_guest_workflow_with_ui(user: User, test_tenant: str, sample_invitation):
    """Test guest workflow through UI (requires mocked OIDC)"""
    # This is a placeholder for full UI integration tests
    # Would require complete OIDC mocking

    await user.open(f'/{test_tenant}/accept/{sample_invitation}')
    await user.should_see('Welkom')  # Dutch: Welcome

    # Full test would include:
    # 1. Mock OIDC login
    # 2. Navigate through all steps
    # 3. Verify final redirect
    # 4. Check database state
