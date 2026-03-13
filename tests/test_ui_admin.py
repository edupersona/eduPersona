"""
Tests for admin management interface using NiceGUI user fixture.
"""
import pytest
from nicegui.testing import User


@pytest.mark.ui
async def test_admin_login_page(user: User, test_tenant: str):
    """Test admin login page loads"""
    await user.open(f'/{test_tenant}/m/login')

    await user.should_see('Inloggen')  # Dutch: Login


@pytest.mark.ui
async def test_invitations_page_requires_auth(user: User, test_tenant: str):
    """Test invitations page requires authentication (redirects to login)"""
    await user.open(f'/{test_tenant}/m/invitations')

    # Without auth, should redirect to login
    await user.should_see('Inloggen')  # Dutch: Login


@pytest.mark.ui
async def test_invitations_page_authenticated(authenticated_invite_user: User, test_tenant: str):
    """Test invitations page loads when authenticated via dependency override"""
    await authenticated_invite_user.open(f'/{test_tenant}/m/invitations')

    # Should see invitations page content (empty state + add button)
    await authenticated_invite_user.should_see('Geen uitnodigingen')
    await authenticated_invite_user.should_see('Nieuwe uitnodiging')


@pytest.mark.ui
async def test_roles_page_requires_auth(user: User, test_tenant: str):
    """Test roles page requires authentication (redirects to login)"""
    await user.open(f'/{test_tenant}/m/roles')

    # Without auth, should redirect to login
    await user.should_see('Inloggen')  # Dutch: Login


@pytest.mark.ui
async def test_roles_page_authenticated(authenticated_role_admin_user: User, test_tenant: str):
    """Test roles page loads when authenticated via dependency override"""
    await authenticated_role_admin_user.open(f'/{test_tenant}/m/roles')

    # Should see roles page content (empty state + add buttons)
    await authenticated_role_admin_user.should_see('Geen rollen')
    await authenticated_role_admin_user.should_see('Nieuwe rol')
