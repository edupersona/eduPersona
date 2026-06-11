"""Simulator page render checks.

UI-only: auth gate, page renders, static name inputs present, dynamic persona
fields materialise. Route registered via main.py; no top-level route import.
"""
import pytest
from nicegui.testing import User


@pytest.mark.ui
async def test_simulator_requires_auth(user: User, test_tenant: str):
    """Without invite auth the page does not render (redirected to login)."""
    await user.open(f"/m/{test_tenant}/simulator")
    await user.should_not_see("Gastgegevens")


@pytest.mark.ui
async def test_simulator_page_renders(authenticated_invite_user: User, test_tenant: str):
    await authenticated_invite_user.open(f"/m/{test_tenant}/simulator")
    await authenticated_invite_user.should_see("Gastgegevens")
    await authenticated_invite_user.should_see("Gastdocent")   # persona option label
    await authenticated_invite_user.should_see("voornaam")     # _('Given name') static input
    await authenticated_invite_user.should_see("achternaam")   # _('Family name') static input


@pytest.mark.ui
async def test_simulator_dynamic_fields(authenticated_invite_user: User, test_tenant: str):
    await authenticated_invite_user.open(f"/m/{test_tenant}/simulator")
    # gastdocent's expected_params materialise as inputs
    await authenticated_invite_user.should_see("faculteit")
    await authenticated_invite_user.should_see("personal_message")
