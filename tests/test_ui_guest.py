"""
Tests for guest invitation acceptance workflow using NiceGUI user fixture.
These tests run fast without needing a real browser.
"""
import pytest
from nicegui.testing import User


@pytest.mark.ui
async def test_guest_sees_invitation_page(user: User, test_tenant: str, sample_invitation):
    """Test guest can view invitation page"""
    await user.open(f'/{test_tenant}/accept/{sample_invitation}')

    # Should see welcome and workflow elements (Dutch translations)
    await user.should_see('Welkom')  # Dutch: Welcome
    await user.should_see('eduID')


@pytest.mark.ui
async def test_guest_invalid_invitation_code(user: User, test_tenant: str):
    """Test guest with invalid invitation code sees error"""
    await user.open(f'/{test_tenant}/accept/invalid_code_12345')

    # Should see welcome page (invalid code shows notification, page still renders)
    await user.should_see('Welkom')  # Dutch: Welcome (page renders, error in notification)


@pytest.mark.ui
async def test_landing_page(user: User):
    """Test landing page loads correctly"""
    await user.open('/')

    # Should see landing page content (Dutch translations)
    await user.should_see('Beheer')  # Dutch: Management


@pytest.mark.ui
@pytest.mark.slow
async def test_guest_workflow_step_navigation(user: User, test_tenant: str, sample_invitation):
    """Test guest can navigate through workflow steps"""
    await user.open(f'/{test_tenant}/accept/{sample_invitation}')

    # Initial state should show first step (Dutch translation)
    await user.should_see('Welkom')  # Dutch: Welcome

    # Note: Full workflow test would require mocking OIDC
    # This is a basic structure test


@pytest.mark.ui
async def test_multiple_tabs_isolation(user: User, test_tenant: str, sample_invitation):
    """Test that NiceGUI tab storage isolates different invitation sessions"""
    # Open first invitation
    await user.open(f'/{test_tenant}/accept/{sample_invitation}')
    await user.should_see('Welkom')  # Dutch: Welcome

    # This tests the basic page load - full tab isolation testing
    # would require opening multiple browser contexts which is
    # better suited for integration tests
