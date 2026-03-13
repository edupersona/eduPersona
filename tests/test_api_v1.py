"""
Tests for RESTful API v1 endpoints.

Uses fixtures from conftest.py: test_tenant, api_client, sample_guest, sample_role
Note: sample_guest and sample_role fixtures return dicts (from stores), not model instances.
"""
import pytest
from ng_loba.models.models import Guest, Role, RoleAssignment, Invitation, InvitationRoleAssignment


class TestGuestsAPI:
    """Tests for /api/v1/guests endpoints."""

    @pytest.mark.api
    async def test_list_guests_empty(self, api_client, test_tenant):
        """GET /api/v1/guests returns empty list when no guests."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] == 0

    @pytest.mark.api
    async def test_list_guests(self, api_client, test_tenant, sample_guest):
        """GET /api/v1/guests returns guests with enriched data."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests")
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["total"] >= 1
        guest = next((g for g in data["data"] if g["user_id"] == sample_guest["user_id"]), None)
        assert guest is not None
        assert "guest_statuses" in guest
        assert "assignment_count" in guest

    @pytest.mark.api
    async def test_get_guest(self, api_client, test_tenant, sample_guest):
        """GET /api/v1/guests/{id} returns single guest."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/{sample_guest['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["user_id"] == sample_guest["user_id"]

    @pytest.mark.api
    async def test_get_guest_not_found(self, api_client, test_tenant):
        """GET /api/v1/guests/{id} returns 404 for non-existent guest."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/99999")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_create_guest(self, api_client, test_tenant):
        """POST /api/v1/guests creates new guest."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/guests",
            json={
                "user_id": "new.user.v1@example.edu",
                "email": "new.v1@gmail.com",
                "given_name": "New",
                "family_name": "Guest",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["user_id"] == "new.user.v1@example.edu"

        # Cleanup
        await Guest.filter(user_id="new.user.v1@example.edu").delete()

    @pytest.mark.api
    async def test_create_guest_conflict(self, api_client, test_tenant, sample_guest):
        """POST /api/v1/guests returns 409 for duplicate user_id."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/guests",
            json={
                "user_id": sample_guest["user_id"],
                "email": "duplicate@gmail.com",
            },
        )
        assert response.status_code == 409

    @pytest.mark.api
    async def test_update_guest(self, api_client, test_tenant, sample_guest):
        """PATCH /api/v1/guests/{id} updates guest fields."""
        response = await api_client.patch(
            f"/{test_tenant}/api/v1/guests/{sample_guest['id']}",
            json={"given_name": "Updated"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["given_name"] == "Updated"

    @pytest.mark.api
    async def test_delete_guest(self, api_client, test_tenant):
        """DELETE /api/v1/guests/{id} deletes guest."""
        guest = await Guest.create(
            tenant=test_tenant,
            user_id="to.delete.v1@example.edu",
            email="delete@gmail.com",
        )
        response = await api_client.delete(f"/{test_tenant}/api/v1/guests/{guest.id}")
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True


class TestRolesAPI:
    """Tests for /api/v1/roles endpoints."""

    @pytest.mark.api
    async def test_list_roles(self, api_client, test_tenant, sample_role):
        """GET /api/v1/roles returns roles."""
        response = await api_client.get(f"/{test_tenant}/api/v1/roles")
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["total"] >= 1

    @pytest.mark.api
    async def test_get_role(self, api_client, test_tenant, sample_role):
        """GET /api/v1/roles/{id} returns single role."""
        response = await api_client.get(f"/{test_tenant}/api/v1/roles/{sample_role['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == sample_role["name"]

    @pytest.mark.api
    async def test_create_role(self, api_client, test_tenant):
        """POST /api/v1/roles creates new role."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/roles",
            json={
                "name": "New Role v1",
                "mail_sender_email": "sender@example.com",
                "mail_sender_name": "Sender",
                "redirect_url": "https://example.com",
                "redirect_text": "Go",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "New Role v1"
        # Should have default role_end_date
        assert data["data"]["role_end_date"] is not None

        # Cleanup
        await Role.filter(name="New Role v1").delete()


class TestRoleAssignmentsAPI:
    """Tests for /api/v1/role-assignments endpoints."""

    @pytest.mark.api
    async def test_create_role_assignment(self, api_client, test_tenant, sample_guest, sample_role):
        """POST /api/v1/role-assignments creates assignment."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/role-assignments",
            json={
                "guest_id": sample_guest["id"],
                "role_id": sample_role["id"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["guest_id"] == sample_guest["id"]
        assert data["data"]["role_id"] == sample_role["id"]

        # Cleanup
        await RoleAssignment.filter(id=data["data"]["id"]).delete()

    @pytest.mark.api
    async def test_list_role_assignments_with_expand(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /api/v1/role-assignments?expand=guest,role includes expanded objects."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(
                f"/{test_tenant}/api/v1/role-assignments?expand=guest,role"
            )
            assert response.status_code == 200
            data = response.json()
            item = next((i for i in data["data"] if i["id"] == ra.id), None)
            assert item is not None
            assert "guest" in item
            assert "role" in item
            assert item["guest"]["user_id"] == sample_guest["user_id"]
        finally:
            await ra.delete()


class TestInvitationsAPI:
    """Tests for /api/v1/invitations endpoints."""

    @pytest.mark.api
    async def test_create_invitation(self, api_client, test_tenant, sample_guest, sample_role):
        """POST /api/v1/invitations creates invitation."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.post(
                f"/{test_tenant}/api/v1/invitations",
                json={
                    "guest_id": sample_guest["id"],
                    "role_assignment_ids": [ra.id],
                    "invitation_email": "invite@example.com",
                    "personal_message": "Welcome!",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "pending"
            assert "code" in data["data"]

            # Cleanup
            await InvitationRoleAssignment.filter(invitation_id=data["data"]["id"]).delete()
            await Invitation.filter(id=data["data"]["id"]).delete()
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_get_invitation_by_code(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /api/v1/invitations/code/{code} returns invitation."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="testcode123v1",
            guest_id=sample_guest["id"],
            invitation_email="test@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(
            invitation_id=inv.id,
            role_assignment_id=ra.id,
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/invitations/code/testcode123v1")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["code"] == "testcode123v1"
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()


class TestQuickInvite:
    """Tests for /api/v1/quick-invite convenience endpoint."""

    @pytest.mark.api
    async def test_quick_invite_new_guest(self, api_client, test_tenant, sample_role):
        """POST /api/v1/quick-invite creates guest, assignment, and invitation."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/quick-invite",
            json={
                "user_id": "quick.invite.v1@example.edu",
                "email": "quick@gmail.com",
                "given_name": "Quick",
                "family_name": "Invite",
                "role_id": sample_role["id"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["guest_created"] is True
        assert "guest" in data["data"]
        assert "role_assignment" in data["data"]
        assert "invitation" in data["data"]

        # Cleanup
        guest_id = data["data"]["guest"]["id"]
        inv_id = data["data"]["invitation"]["id"]
        ra_id = data["data"]["role_assignment"]["id"]
        await InvitationRoleAssignment.filter(invitation_id=inv_id).delete()
        await Invitation.filter(id=inv_id).delete()
        await RoleAssignment.filter(id=ra_id).delete()
        await Guest.filter(id=guest_id).delete()

    @pytest.mark.api
    async def test_quick_invite_existing_guest(self, api_client, test_tenant, sample_guest, sample_role):
        """POST /api/v1/quick-invite uses existing guest."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/quick-invite",
            json={
                "user_id": sample_guest["user_id"],
                "email": sample_guest["email"],
                "role_id": sample_role["id"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["guest_created"] is False
        assert data["data"]["guest"]["id"] == sample_guest["id"]

        # Cleanup
        inv_id = data["data"]["invitation"]["id"]
        ra_id = data["data"]["role_assignment"]["id"]
        await InvitationRoleAssignment.filter(invitation_id=inv_id).delete()
        await Invitation.filter(id=inv_id).delete()
        await RoleAssignment.filter(id=ra_id).delete()

    @pytest.mark.api
    async def test_quick_invite_by_role_name(self, api_client, test_tenant, sample_role):
        """POST /api/v1/quick-invite accepts role_name instead of role_id."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/quick-invite",
            json={
                "user_id": "quick.name.v1@example.edu",
                "email": "quick.name@gmail.com",
                "role_name": sample_role["name"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["role_assignment"]["role_id"] == sample_role["id"]

        # Cleanup
        guest_id = data["data"]["guest"]["id"]
        inv_id = data["data"]["invitation"]["id"]
        ra_id = data["data"]["role_assignment"]["id"]
        await InvitationRoleAssignment.filter(invitation_id=inv_id).delete()
        await Invitation.filter(id=inv_id).delete()
        await RoleAssignment.filter(id=ra_id).delete()
        await Guest.filter(id=guest_id).delete()

    @pytest.mark.api
    async def test_quick_invite_missing_role(self, api_client, test_tenant):
        """POST /api/v1/quick-invite fails without role_id or role_name."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/quick-invite",
            json={
                "user_id": "no.role@example.edu",
                "email": "no.role@gmail.com",
            },
        )
        assert response.status_code == 400


class TestPagination:
    """Tests for pagination in list endpoints."""

    @pytest.mark.api
    async def test_pagination_params(self, api_client, test_tenant):
        """List endpoints respect limit and offset."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["limit"] == 5
        assert data["meta"]["offset"] == 0


class TestResponseFormat:
    """Tests for consistent API response format."""

    @pytest.mark.api
    async def test_success_response_format(self, api_client, test_tenant):
        """Successful responses have data and meta fields."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert "timestamp" in data["meta"]

    @pytest.mark.api
    async def test_error_response_format(self, api_client, test_tenant):
        """Error responses have error field with code and message."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/99999")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert "code" in data["detail"]["error"]
        assert "message" in data["detail"]["error"]


class TestGuestsNestedEndpoints:
    """Tests for guest nested resource endpoints."""

    @pytest.mark.api
    async def test_get_guest_attributes_empty(self, api_client, test_tenant, sample_guest):
        """GET /guests/{id}/attributes returns empty list when no attributes."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/{sample_guest['id']}/attributes")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["meta"]["total"] == 0

    @pytest.mark.api
    async def test_get_guest_attributes_not_found(self, api_client, test_tenant):
        """GET /guests/{id}/attributes returns 404 for non-existent guest."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/99999/attributes")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_get_guest_role_assignments_empty(self, api_client, test_tenant, sample_guest):
        """GET /guests/{id}/role-assignments returns empty list when no assignments."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/{sample_guest['id']}/role-assignments")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.api
    async def test_get_guest_role_assignments_with_data(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /guests/{id}/role-assignments returns assignments."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/guests/{sample_guest['id']}/role-assignments")
            assert response.status_code == 200
            data = response.json()
            assert data["meta"]["total"] == 1
            assert data["data"][0]["role_id"] == sample_role["id"]
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_get_guest_role_assignments_not_found(self, api_client, test_tenant):
        """GET /guests/{id}/role-assignments returns 404 for non-existent guest."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/99999/role-assignments")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_get_guest_invitations_empty(self, api_client, test_tenant, sample_guest):
        """GET /guests/{id}/invitations returns empty list when no invitations."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/{sample_guest['id']}/invitations")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.api
    async def test_get_guest_invitations_not_found(self, api_client, test_tenant):
        """GET /guests/{id}/invitations returns 404 for non-existent guest."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests/99999/invitations")
        assert response.status_code == 404


class TestRolesAPIExtended:
    """Extended tests for /api/v1/roles endpoints."""

    @pytest.mark.api
    async def test_update_role(self, api_client, test_tenant, sample_role):
        """PATCH /roles/{id} updates role fields."""
        response = await api_client.patch(
            f"/{test_tenant}/api/v1/roles/{sample_role['id']}",
            json={"name": "Updated Role Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "Updated Role Name"

    @pytest.mark.api
    async def test_update_role_not_found(self, api_client, test_tenant):
        """PATCH /roles/{id} returns 404 for non-existent role."""
        response = await api_client.patch(
            f"/{test_tenant}/api/v1/roles/99999",
            json={"name": "New Name"},
        )
        assert response.status_code == 404

    @pytest.mark.api
    async def test_update_role_empty_body(self, api_client, test_tenant, sample_role):
        """PATCH /roles/{id} returns 400 when no fields to update."""
        response = await api_client.patch(
            f"/{test_tenant}/api/v1/roles/{sample_role['id']}",
            json={},
        )
        assert response.status_code == 400

    @pytest.mark.api
    async def test_delete_role(self, api_client, test_tenant):
        """DELETE /roles/{id} deletes role."""
        role = await Role.create(
            tenant=test_tenant,
            name="Role to Delete",
            redirect_url="https://example.com",
            redirect_text="Go",
            mail_sender_email="test@example.com",
            mail_sender_name="Test",
            role_end_date="2030-01-01",
        )
        response = await api_client.delete(f"/{test_tenant}/api/v1/roles/{role.id}")
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True

    @pytest.mark.api
    async def test_delete_role_not_found(self, api_client, test_tenant):
        """DELETE /roles/{id} returns 404 for non-existent role."""
        response = await api_client.delete(f"/{test_tenant}/api/v1/roles/99999")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_get_role_assignments(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /roles/{id}/assignments returns role's assignments."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/roles/{sample_role['id']}/assignments")
            assert response.status_code == 200
            data = response.json()
            assert data["meta"]["total"] == 1
            assert data["data"][0]["guest_id"] == sample_guest["id"]
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_get_role_assignments_empty(self, api_client, test_tenant, sample_role):
        """GET /roles/{id}/assignments returns empty list when no assignments."""
        response = await api_client.get(f"/{test_tenant}/api/v1/roles/{sample_role['id']}/assignments")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    @pytest.mark.api
    async def test_get_role_assignments_not_found(self, api_client, test_tenant):
        """GET /roles/{id}/assignments returns 404 for non-existent role."""
        response = await api_client.get(f"/{test_tenant}/api/v1/roles/99999/assignments")
        assert response.status_code == 404


class TestRoleAssignmentsAPIExtended:
    """Extended tests for /api/v1/role-assignments endpoints."""

    @pytest.mark.api
    async def test_get_role_assignment(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /role-assignments/{id} returns single assignment."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/role-assignments/{ra.id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == ra.id
            assert data["data"]["guest_id"] == sample_guest["id"]
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_get_role_assignment_with_expand(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /role-assignments/{id}?expand=guest,role includes expanded objects."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/role-assignments/{ra.id}?expand=guest,role")
            assert response.status_code == 200
            data = response.json()
            assert "guest" in data["data"]
            assert "role" in data["data"]
            assert data["data"]["guest"]["user_id"] == sample_guest["user_id"]
            assert data["data"]["role"]["name"] == sample_role["name"]
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_get_role_assignment_not_found(self, api_client, test_tenant):
        """GET /role-assignments/{id} returns 404 for non-existent assignment."""
        response = await api_client.get(f"/{test_tenant}/api/v1/role-assignments/99999")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_create_role_assignment_invalid_guest(self, api_client, test_tenant, sample_role):
        """POST /role-assignments returns 404 for non-existent guest."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/role-assignments",
            json={"guest_id": 99999, "role_id": sample_role["id"]},
        )
        assert response.status_code == 404

    @pytest.mark.api
    async def test_create_role_assignment_invalid_role(self, api_client, test_tenant, sample_guest):
        """POST /role-assignments returns 404 for non-existent role."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/role-assignments",
            json={"guest_id": sample_guest["id"], "role_id": 99999},
        )
        assert response.status_code == 404

    @pytest.mark.api
    async def test_update_role_assignment(self, api_client, test_tenant, sample_guest, sample_role):
        """PATCH /role-assignments/{id} updates dates."""
        from datetime import date, timedelta
        # Use an end_date within the role's role_end_date (sample_role is 1 year from now)
        valid_end_date = (date.today() + timedelta(days=30)).isoformat()
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.patch(
                f"/{test_tenant}/api/v1/role-assignments/{ra.id}",
                json={"end_date": valid_end_date},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["end_date"] == valid_end_date
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_update_role_assignment_not_found(self, api_client, test_tenant):
        """PATCH /role-assignments/{id} returns 404 for non-existent assignment."""
        response = await api_client.patch(
            f"/{test_tenant}/api/v1/role-assignments/99999",
            json={"end_date": "2030-12-31"},
        )
        assert response.status_code == 404

    @pytest.mark.api
    async def test_delete_role_assignment(self, api_client, test_tenant, sample_guest, sample_role):
        """DELETE /role-assignments/{id} deletes assignment."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        response = await api_client.delete(f"/{test_tenant}/api/v1/role-assignments/{ra.id}")
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] is True

    @pytest.mark.api
    async def test_delete_role_assignment_not_found(self, api_client, test_tenant):
        """DELETE /role-assignments/{id} returns 404 for non-existent assignment."""
        response = await api_client.delete(f"/{test_tenant}/api/v1/role-assignments/99999")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_list_role_assignments_filter_by_guest(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /role-assignments?guest_id=X filters by guest."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/role-assignments?guest_id={sample_guest['id']}")
            assert response.status_code == 200
            data = response.json()
            assert all(item["guest_id"] == sample_guest["id"] for item in data["data"])
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_list_role_assignments_filter_by_role(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /role-assignments?role_id=X filters by role."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/role-assignments?role_id={sample_role['id']}")
            assert response.status_code == 200
            data = response.json()
            assert all(item["role_id"] == sample_role["id"] for item in data["data"])
        finally:
            await ra.delete()


class TestInvitationsAPIExtended:
    """Extended tests for /api/v1/invitations endpoints."""

    @pytest.mark.api
    async def test_list_invitations(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /invitations returns all invitations."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="listtest123",
            guest_id=sample_guest["id"],
            invitation_email="list@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/invitations")
            assert response.status_code == 200
            data = response.json()
            assert data["meta"]["total"] >= 1
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_list_invitations_filter_by_status(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /invitations?status=pending filters by status."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="statustest123",
            guest_id=sample_guest["id"],
            invitation_email="status@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/invitations?status=pending")
            assert response.status_code == 200
            data = response.json()
            assert all(item["status"] == "pending" for item in data["data"])
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_list_invitations_filter_by_guest(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /invitations?guest_id=X filters by guest."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="guestfilter123",
            guest_id=sample_guest["id"],
            invitation_email="guestfilter@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/invitations?guest_id={sample_guest['id']}")
            assert response.status_code == 200
            data = response.json()
            assert all(item["guest_id"] == sample_guest["id"] for item in data["data"])
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_list_invitations_with_expand(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /invitations?expand=guest includes guest data."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="expandtest123",
            guest_id=sample_guest["id"],
            invitation_email="expand@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/invitations?expand=guest")
            assert response.status_code == 200
            data = response.json()
            for item in data["data"]:
                assert "guest" in item
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_get_invitation_by_id(self, api_client, test_tenant, sample_guest, sample_role):
        """GET /invitations/{id} returns single invitation."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="getbyid123",
            guest_id=sample_guest["id"],
            invitation_email="getbyid@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.get(f"/{test_tenant}/api/v1/invitations/{inv.id}")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == inv.id
            assert data["data"]["code"] == "getbyid123"
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_get_invitation_by_id_not_found(self, api_client, test_tenant):
        """GET /invitations/{id} returns 404 for non-existent invitation."""
        response = await api_client.get(f"/{test_tenant}/api/v1/invitations/99999")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_get_invitation_by_code_not_found(self, api_client, test_tenant):
        """GET /invitations/code/{code} returns 404 for non-existent code."""
        response = await api_client.get(f"/{test_tenant}/api/v1/invitations/code/nonexistent")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_update_invitation_status(self, api_client, test_tenant, sample_guest, sample_role):
        """PATCH /invitations/{id} updates status."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="patchtest123",
            guest_id=sample_guest["id"],
            invitation_email="patch@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.patch(
                f"/{test_tenant}/api/v1/invitations/{inv.id}",
                json={"status": "accepted"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["status"] == "accepted"
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_update_invitation_invalid_status(self, api_client, test_tenant, sample_guest, sample_role):
        """PATCH /invitations/{id} returns 400 for invalid status."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="invalidstatus",
            guest_id=sample_guest["id"],
            invitation_email="invalid@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.patch(
                f"/{test_tenant}/api/v1/invitations/{inv.id}",
                json={"status": "invalid_status"},
            )
            assert response.status_code == 400
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_update_invitation_not_found(self, api_client, test_tenant):
        """PATCH /invitations/{id} returns 404 for non-existent invitation."""
        response = await api_client.patch(
            f"/{test_tenant}/api/v1/invitations/99999",
            json={"status": "accepted"},
        )
        assert response.status_code == 404

    @pytest.mark.api
    async def test_update_invitation_empty_body(self, api_client, test_tenant, sample_guest, sample_role):
        """PATCH /invitations/{id} returns 400 when no fields to update."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="emptybody123",
            guest_id=sample_guest["id"],
            invitation_email="empty@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.patch(
                f"/{test_tenant}/api/v1/invitations/{inv.id}",
                json={},
            )
            assert response.status_code == 400
        finally:
            await InvitationRoleAssignment.filter(invitation_id=inv.id).delete()
            await inv.delete()
            await ra.delete()

    @pytest.mark.api
    async def test_delete_invitation(self, api_client, test_tenant, sample_guest, sample_role):
        """DELETE /invitations/{id} deletes invitation."""
        ra = await RoleAssignment.create(
            tenant=test_tenant,
            guest_id=sample_guest["id"],
            role_id=sample_role["id"],
        )
        inv = await Invitation.create(
            tenant=test_tenant,
            code="deletetest123",
            guest_id=sample_guest["id"],
            invitation_email="delete@example.com",
            status="pending",
        )
        await InvitationRoleAssignment.create(invitation_id=inv.id, role_assignment_id=ra.id)
        try:
            response = await api_client.delete(f"/{test_tenant}/api/v1/invitations/{inv.id}")
            assert response.status_code == 200
            assert response.json()["data"]["deleted"] is True
        finally:
            await ra.delete()

    @pytest.mark.api
    async def test_delete_invitation_not_found(self, api_client, test_tenant):
        """DELETE /invitations/{id} returns 404 for non-existent invitation."""
        response = await api_client.delete(f"/{test_tenant}/api/v1/invitations/99999")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_create_invitation_invalid_guest(self, api_client, test_tenant, sample_role):
        """POST /invitations returns 404 for non-existent guest."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/invitations",
            json={
                "guest_id": 99999,
                "role_assignment_ids": [1],
                "invitation_email": "test@example.com",
            },
        )
        assert response.status_code == 404

    @pytest.mark.api
    async def test_create_invitation_invalid_role_assignment(self, api_client, test_tenant, sample_guest):
        """POST /invitations returns 404 for non-existent role assignment."""
        response = await api_client.post(
            f"/{test_tenant}/api/v1/invitations",
            json={
                "guest_id": sample_guest["id"],
                "role_assignment_ids": [99999],
                "invitation_email": "test@example.com",
            },
        )
        assert response.status_code == 404


class TestInvalidTenant:
    """Tests for invalid tenant handling."""

    @pytest.mark.api
    async def test_invalid_tenant_guests(self, api_client):
        """API returns 404 for invalid tenant."""
        response = await api_client.get("/invalid_tenant/api/v1/guests")
        assert response.status_code == 404

    @pytest.mark.api
    async def test_invalid_tenant_roles(self, api_client):
        """API returns 404 for invalid tenant."""
        response = await api_client.get("/invalid_tenant/api/v1/roles")
        assert response.status_code == 404
