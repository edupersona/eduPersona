"""
Tests for SURF Invite API compatibility endpoint.
Tests for generic v1 REST API are in test_api_v1.py.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from nicegui import app


class TestAPIKeyAuth:
    """Tests for API key authentication on tenant-scoped routes."""

    @pytest.mark.api
    async def test_missing_api_key_returns_401(self, test_tenant):
        """Request without X-API-Key header returns 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/{test_tenant}/api/v1/guests")
        assert response.status_code == 401
        assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"

    @pytest.mark.api
    async def test_wrong_api_key_returns_401(self, test_tenant):
        """Request with incorrect API key returns 401."""
        headers = {"X-API-Key": "wrong-key"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
            response = await client.get(f"/{test_tenant}/api/v1/guests")
        assert response.status_code == 401
        assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"

    @pytest.mark.api
    async def test_valid_api_key_succeeds(self, api_client, test_tenant):
        """Request with correct API key succeeds."""
        response = await api_client.get(f"/{test_tenant}/api/v1/guests")
        assert response.status_code == 200

    @pytest.mark.api
    async def test_cleanup_endpoint_ignores_api_key(self):
        """Cleanup endpoint uses its own auth, not the tenant API key."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/cleanup")
        # Should get 401 from cleanup's own key check, not from tenant API key dependency
        assert response.status_code == 401
        assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.api
async def test_invite_roles_create_role(api_client, test_tenant):
    """Test POST /{tenant}/api/v1/invite-roles creates new role (SURF API emulation)"""
    payload = {
        "name": "New SURF Role",
        "shortName": "surf-role-123",
        "applicationUsages": [
            {
                "landingPage": "https://canvas.example.com/courses/123",
                "landingPageName": "Canvas: Test Course"
            }
        ]
    }

    response = await api_client.post(f"/{test_tenant}/api/v1/invite-roles", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    data = body["data"]

    assert data["name"] == "New SURF Role"
    assert data["scim_id"] == "surf-role-123"
    assert data["redirect_url"] == "https://canvas.example.com/courses/123"
    assert data["action"] == "created"


@pytest.mark.api
async def test_invite_roles_update_role(api_client, test_tenant, sample_role):
    """Test POST /{tenant}/api/v1/invite-roles updates existing role"""
    payload = {
        "name": "Updated Role Name",
        "shortName": sample_role["scim_id"],  # Use existing scim_id
        "applicationUsages": [
            {
                "landingPage": "https://updated.example.com",
                "landingPageName": "Updated Landing"
            }
        ]
    }

    response = await api_client.post(f"/{test_tenant}/api/v1/invite-roles", json=payload)

    assert response.status_code == 200
    body = response.json()
    data = body["data"]

    assert data["name"] == "Updated Role Name"
    assert data["redirect_url"] == "https://updated.example.com"
    assert data["action"] == "updated"


@pytest.mark.api
async def test_invite_roles_missing_required_fields(api_client, test_tenant):
    """Test POST /{tenant}/api/v1/invite-roles with missing required fields"""
    payload = {
        "name": "Test Group"
        # Missing shortName
    }

    response = await api_client.post(f"/{test_tenant}/api/v1/invite-roles", json=payload)

    # Pydantic validation returns 422 for missing required fields
    assert response.status_code == 422


@pytest.mark.api
async def test_multitenancy_in_api(api_client, sample_role):
    """Test that API respects tenant isolation — unconfigured tenant returns 404."""
    # Query roles for 'hvh' tenant (has sample_role + api_key)
    hvh_response = await api_client.get("/hvh/api/v1/roles")
    assert hvh_response.status_code == 200
    hvh_body = hvh_response.json()
    hvh_roles = hvh_body["data"]
    assert "Test Role" in [g["name"] for g in hvh_roles]

    # 'vu' tenant is registered as valid but has no config/api_key — should be rejected
    vu_response = await api_client.get("/vu/api/v1/roles")
    assert vu_response.status_code == 404
