# pyright: reportUnusedImport=false
"""
Shared pytest fixtures for edupersona tests.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from tortoise import Tortoise
from httpx import AsyncClient, ASGITransport
from starlette.middleware.sessions import SessionMiddleware
from nicegui import app, storage, ui
from nicegui.testing import User
from services.settings import config
from ng_rdm.store.multitenancy import set_valid_tenants
from services.auth.dependencies import (
    require_admin_auth,
    require_invite_auth,
    require_role_admin_auth,
)

# NOTE: Do NOT import main here - let the test plugin handle it to avoid route registration conflicts
# Tenant registration and middleware setup is done via autouse fixture below

# Register API routes on the NiceGUI app once at module load time
import routes.api  # noqa: F401
from routes.api import api_router
app.include_router(api_router)


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment before each test.

    This must run before each test because:
    1. main.py is reloaded for each test, resetting global state
    2. valid_tenants gets reset to [] when multitenancy module reloads
    3. We need to re-register test tenants before each test
    """
    # Register test tenants (must happen before routes are accessed)
    set_valid_tenants(['hvh', 'vu'])

    # Set storage secret for testing
    storage.Storage.secret = 'test-secret-for-pytest'

    # Register exception handlers (overrides NiceGUI's defaults)
    from services.exception_handlers import register_exception_handlers
    register_exception_handlers(app)

    yield

@pytest.fixture(autouse=True)
async def reset_database():
    """Reset database before each test using in-memory SQLite"""
    await Tortoise.init(
        db_url='sqlite://:memory:',
        modules={"models": ["domain.models"]}
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture
def test_tenant():
    """Provide test tenant identifier"""
    return "hvh"


@pytest.fixture
async def api_client():
    """AsyncClient for API testing"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_oidc_userinfo():
    """Mock OIDC userinfo response"""
    return {
        "sub": "mock-subject-id",
        "eduperson_principal_name": "test@example.com",
        "name": "Test User",
        "given_name": "Test",
        "family_name": "User",
        "email": "test@example.com",
        "eduid_login": {
            "identifier": "mock-eduid-id",
            "verified": True
        }
    }


@pytest.fixture
def mock_oidc_id_token():
    """Mock OIDC ID token claims"""
    return {
        "sub": "mock-subject-id",
        "aud": "mock-client-id",
        "iss": "https://login.test.eduid.nl",
        "exp": 9999999999,
        "iat": 1234567890,
        "acr": "http://eduid.nl/trust/validate-names"
    }


@pytest.fixture
def mock_oidc_token_data():
    """Mock OIDC token response"""
    return {
        "access_token": "mock-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "id_token": "mock-id-token"
    }


@pytest.fixture
def mock_scim_client(monkeypatch):
    """Mock SCIM client to avoid external API calls"""
    mock_client = Mock()
    mock_client.create_user = AsyncMock(return_value={"id": "scim-user-123"})
    mock_client.create_group = AsyncMock(return_value={"id": "scim-group-456"})
    mock_client.add_user_to_group = AsyncMock(return_value=True)
    mock_client.remove_user_from_group = AsyncMock(return_value=True)
    mock_client.delete_user = AsyncMock(return_value=True)

    # Patch SCIM client creation
    async def mock_get_scim_client(*args, **kwargs):
        return mock_client

    # This would need to be patched where SCIM client is created
    # monkeypatch.setattr("services.storage.storage.get_scim_client", mock_get_scim_client)

    return mock_client


@pytest.fixture
def mock_smtp(monkeypatch):
    """Mock SMTP email sending"""
    mock_send = AsyncMock(return_value=True)
    monkeypatch.setattr("services.smtp_mail.sendmail_async", mock_send)
    return mock_send


@pytest.fixture
async def sample_guest(test_tenant):
    """Create a sample guest for testing"""
    from domain.stores import get_guest_store

    guest_store = get_guest_store(test_tenant)
    guest = await guest_store.create_item({
        "tenant": test_tenant,
        "user_id": "testguest@example.com",
        "given_name": "Test",
        "family_name": "Guest",
        "email": "testguest@example.com",
    })
    return guest


@pytest.fixture
async def sample_role(test_tenant):
    """Create a sample role for testing"""
    from datetime import date, timedelta
    from domain.stores import get_role_store

    role_store = get_role_store(test_tenant)
    role = await role_store.create_item({
        "tenant": test_tenant,
        "scim_id": "test-role-scim-id",
        "name": "Test Role",
        "redirect_url": "https://example.com/test",
        "redirect_text": "Go to Test",
        "mail_sender_email": "test@example.com",
        "mail_sender_name": "Test Sender",
        "role_end_date": (date.today() + timedelta(days=365)).isoformat(),
    })
    return role


@pytest.fixture
async def sample_role_assignment(test_tenant, sample_guest, sample_role):
    """Create a sample role assignment for testing"""
    from domain.assignments import create_role_assignment

    role_assignment = await create_role_assignment(
        test_tenant,
        sample_guest["id"],
        sample_role["id"],
    )
    return role_assignment


def _create_auth_user(user: User, test_tenant: str, authz: list[str]):
    """Helper to wrap user.open with storage setup after page loads."""
    original_open = user.open

    async def open_with_auth(path: str, **kwargs):
        client = await original_open(path, **kwargs)
        with user:
            app.storage.user.update({
                'authenticated': True,
                'tenant': test_tenant,
                'username': 'Test User',
                'authz': authz
            })
        return client

    user.open = open_with_auth  # type: ignore
    return user


@pytest.fixture
async def authenticated_admin_user(user: User, test_tenant):
    """User with basic admin authentication (no specific authz).

    Use for routes with Depends(require_admin_auth).
    """
    app.dependency_overrides[require_admin_auth] = lambda: test_tenant
    yield _create_auth_user(user, test_tenant, authz=[])
    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_invite_user(user: User, test_tenant):
    """User with invitations authorization.

    Use for routes with Depends(require_invite_auth).
    """
    app.dependency_overrides[require_invite_auth] = lambda: test_tenant
    yield _create_auth_user(user, test_tenant, authz=['invitations'])
    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_role_admin_user(user: User, test_tenant):
    """User with roles authorization.

    Use for routes with Depends(require_role_admin_auth).
    """
    app.dependency_overrides[require_role_admin_auth] = lambda: test_tenant
    yield _create_auth_user(user, test_tenant, authz=['roles'])
    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_full_admin_user(user: User, test_tenant):
    """User with full admin access (both invitations and roles).

    Use when testing across multiple protected pages.
    """
    app.dependency_overrides[require_admin_auth] = lambda: test_tenant
    app.dependency_overrides[require_invite_auth] = lambda: test_tenant
    app.dependency_overrides[require_role_admin_auth] = lambda: test_tenant
    yield _create_auth_user(user, test_tenant, authz=['invitations', 'roles'])
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_invitation(test_tenant, sample_role_assignment):
    """Create a sample invitation for testing (linked to role assignment)"""
    from domain.invitations import create_invitation
    from domain.stores import get_guest_store

    # Get guest_id from role_assignment
    guest_id = sample_role_assignment["guest_id"]

    # Get guest email
    guest_store = get_guest_store(test_tenant)
    guests = await guest_store.read_items(filter_by={"id": guest_id})
    guest_email = guests[0]["email"] if guests else "test@example.com"

    invitation = await create_invitation(
        test_tenant,
        guest_id,
        [sample_role_assignment["id"]],  # list of role_assignment_ids
        guest_email,
    )
    return invitation["code"]
