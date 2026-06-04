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

    # NiceGUI test isolation gotcha (§10.1): nicegui_reset_globals pops the top-level
    # package of every @ui.page from sys.modules. A page under `services` (e.g.
    # services.oidc_mt.oidc_callback) severs `services`'s attribute link to siblings
    # like services.webhook, breaking later monkeypatch.setattr('services.webhook.…').
    # Re-link the cached submodule. A bare `import services.webhook` does NOT re-set
    # the attribute when the module is already cached — must assign explicitly.
    # (Related gotcha 2: test modules must not import under a @ui.page package like
    # routes.m — it pins the package and breaks per-test route re-registration; that's
    # why services/simulator_helpers.py lives in services, not routes.m.)
    import sys
    import services
    if 'services.webhook' in sys.modules:
        services.webhook = sys.modules['services.webhook']  # type: ignore[attr-defined]

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
    """AsyncClient for API testing (includes tenant API key header)."""
    headers = {"X-API-Key": config.tenants.hvh.api_key}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
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
async def sample_invitation(test_tenant):
    """Create a sample persona invitation; returns its code."""
    from domain.invitations import create_invitation

    invitation = await create_invitation(
        test_tenant, "gastdocent", "sample@example.org", given_name="Sample",
    )
    return invitation["code"]
