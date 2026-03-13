"""
Tests for SURF Invite API compatibility endpoint.
Tests for generic v1 REST API are in test_api_v1.py.
"""
import pytest


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
    """Test that API respects tenant isolation via path-based routing"""
    # Query roles for 'uva' tenant (has sample_role)
    uva_response = await api_client.get("/uva/api/v1/roles")
    assert uva_response.status_code == 200
    uva_body = uva_response.json()
    uva_roles = uva_body["data"]

    # Query from different tenant should not see UVA roles
    vu_response = await api_client.get("/vu/api/v1/roles")
    assert vu_response.status_code == 200
    vu_body = vu_response.json()
    vu_roles = vu_body["data"]

    # UVA should have our sample role, VU should not
    uva_role_names = [g["name"] for g in uva_roles]
    vu_role_names = [g["name"] for g in vu_roles]

    assert "Test Role" in uva_role_names
    assert "Test Role" not in vu_role_names
