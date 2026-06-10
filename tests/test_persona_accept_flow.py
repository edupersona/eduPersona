"""Persona accept flow.

Domain-level: the persona step lifecycle keys OIDC output by IdP, persists
state['outputs'] to Invitation.step_outputs at finalize, and fires the callback
only when configured. Plus one NiceGUI render check (route registered via main.py;
no top-level route import). The conftest services.webhook re-link keeps the UI
test robust.
"""

from unittest.mock import AsyncMock

import pytest

import domain.invitations as ip
from domain.invitations import (
    apply_invite_to_state,
    create_invitation,
)
from domain.models import Invitation
from steps import OIDCLoginStep, Steps
from services.persona_loader import get_persona_config

USERINFO = {"sub": "abc", "uids": ["anna"], "given_name": "Anna"}
INST_USERINFO = {"sub": "inst-1", "schac_home_organization": "hvh.nl"}


async def _drive_oidc(steps, step_id, userinfo) -> None:
    """Simulate an OIDC step returning its userinfo (keyed by IdP name)."""
    step = next(s for s in steps.step_instances if s.step_id == step_id)
    assert isinstance(step, OIDCLoginStep)
    await step.result_handler(userinfo, {}, {})


async def _build_steps(tenant, code):
    state: dict = {}
    await apply_invite_to_state(tenant, state, code)
    cfg = get_persona_config(tenant, "gastdocent")
    steps = Steps(tenant, state, {"steps": cfg.steps})
    return steps


async def _oidc_step(steps) -> OIDCLoginStep:
    step = next(s for s in steps.step_instances if s.step_id == "eduid_login")
    assert isinstance(step, OIDCLoginStep)
    return step


async def test_lifecycle_persists_outputs_and_fires_callback(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    created = await create_invitation(
        test_tenant, "gastdocent", "anna@example.org", "EMP-1", callback_url="https://client/hook",
    )
    steps = await _build_steps(test_tenant, created["code"])

    # simulate both OIDC returns (eduID then institutional) → review gate
    await _drive_oidc(steps, "eduid_login", USERINFO)
    await _drive_oidc(steps, "institutional_login", INST_USERINFO)
    assert steps.all_steps_done and not steps.is_complete  # gated on Register
    await steps.register()  # the review step's 'Register' button → finalize

    inv = await Invitation.get(id=created["id"])
    assert inv.status == "accepted"
    # OIDC output keyed by IdP name, not step id
    assert inv.step_outputs == {"eduid": USERINFO, "institutional": INST_USERINFO}
    assert steps.is_complete  # finalize ran on Register, once every step was done
    enqueue.assert_awaited_once_with(test_tenant, created["id"])


async def test_lifecycle_no_callback_when_unconfigured(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    created = await create_invitation(test_tenant, "gastdocent", "a@example.org", "EMP-1")  # no callback_url
    steps = await _build_steps(test_tenant, created["code"])

    await _drive_oidc(steps, "eduid_login", USERINFO)
    await _drive_oidc(steps, "institutional_login", INST_USERINFO)
    await steps.register()

    inv = await Invitation.get(id=created["id"])
    assert inv.status == "accepted"
    assert inv.step_outputs == {"eduid": USERINFO, "institutional": INST_USERINFO}
    enqueue.assert_not_called()


async def test_oidc_output_keyed_by_idp_not_step_id(test_tenant, monkeypatch):
    monkeypatch.setattr(ip, "enqueue_callback", AsyncMock())
    created = await create_invitation(test_tenant, "gastdocent", "a@example.org", "EMP-1")
    steps = await _build_steps(test_tenant, created["code"])
    oidc = await _oidc_step(steps)
    await oidc.result_handler(USERINFO, {}, {})
    assert "eduid" in steps.state["outputs"]
    assert "eduid_login" not in steps.state["outputs"]  # step_id is NOT used as the output key


async def test_completion_does_not_bleed_across_invitations(test_tenant, monkeypatch):
    """Opening a different invitation in the same tab resets onboarding progress —
    persona A's completion must never carry into persona B's fresh flow."""
    monkeypatch.setattr(ip, "enqueue_callback", AsyncMock())
    g = await create_invitation(test_tenant, "gastdocent", "anna@example.org", "EMP-1")
    steps = await _build_steps(test_tenant, g["code"])
    await _drive_oidc(steps, "eduid_login", USERINFO)
    await _drive_oidc(steps, "institutional_login", INST_USERINFO)
    await steps.register()
    assert steps.is_complete  # finished as gastdocent

    # Same tab state, fresh alumnus invite (different code) → progress must reset
    a = await create_invitation(test_tenant, "alumnus", "anna@example.org", "EMP-2")
    assert await apply_invite_to_state(test_tenant, steps.state, a["code"])
    assert steps.state.get("completed") is not True
    assert steps.state["outcomes"] == {}
    assert steps.state["outputs"] == {}

    # A fresh orchestrator for the alumnus invite is NOT complete — it onboards anew
    cfg = get_persona_config(test_tenant, "alumnus")
    alumnus = Steps(test_tenant, steps.state, {"steps": cfg.steps})
    await alumnus.startup()
    assert not alumnus.is_complete


async def test_same_invitation_reload_preserves_progress(test_tenant, monkeypatch):
    """Re-applying the SAME invite code (e.g. the OIDC round-trip) keeps in-flight steps."""
    monkeypatch.setattr(ip, "enqueue_callback", AsyncMock())
    g = await create_invitation(test_tenant, "gastdocent", "anna@example.org", "EMP-1")
    steps = await _build_steps(test_tenant, g["code"])
    await _drive_oidc(steps, "eduid_login", USERINFO)  # one step done, not finished

    assert await apply_invite_to_state(test_tenant, steps.state, g["code"])
    assert steps.outcomes.get("eduid_login") == "completed"  # preserved across reload
    assert steps.state["outputs"].get("eduid") == USERINFO


# --- one NiceGUI render check (route comes from main.py registration) ---

@pytest.mark.ui
async def test_accept_persona_page_renders(user, test_tenant):
    created = await create_invitation(
        test_tenant, "gastdocent", "anna@example.org", "EMP-1", given_name="Anna",
    )
    await user.open(f"/accept/{created['code']}")
    await user.should_see("Welkom")      # heading (Dutch)
    await user.should_see("Anna")        # given_name in heading
    await user.should_see("Gastdocent")  # persona display_name
    await user.should_see("eduID")       # eduid_login step


@pytest.mark.ui
async def test_accept_persona_invalid_code_shows_form(user, test_tenant):
    await user.open("/accept/does-not-exist")
    await user.should_see("Uitnodiging accepteren")  # spartan code-entry form


@pytest.mark.ui
async def test_accept_already_accepted_shows_welcome_screen(user, test_tenant):
    """Reopening an accepted invitation shows the persona welcome screen, not a fresh flow."""
    created = await create_invitation(test_tenant, "gastdocent", "anna@example.org", "EMP-1")
    await Invitation.filter(tenant=test_tenant, code=created["code"]).update(status="accepted")
    await user.open(f"/accept/{created['code']}")
    await user.should_see("toegang tot de leeromgeving")  # per-persona completion_message
    await user.should_see("Naar de leeromgeving")         # per-persona cta_label
    await user.should_not_see("Inloggen met eduID")       # no step cards — onboarding is done


@pytest.mark.ui
async def test_accept_expired_shows_dead_end(user, test_tenant):
    """An expired invitation gets a dead-end screen, not a fresh flow."""
    created = await create_invitation(test_tenant, "gastdocent", "anna@example.org", "EMP-1")
    await Invitation.filter(tenant=test_tenant, code=created["code"]).update(status="expired")
    await user.open(f"/accept/{created['code']}")
    await user.should_see("verlopen")       # expired message
    await user.should_not_see("Welkom")     # onboarding heading never renders


async def test_expire_overdue_invitations_sweep(test_tenant):
    """Sweep flips overdue pending invites to expired; future/NULL untouched. Through the store."""
    from datetime import timedelta
    from ng_rdm.utils.helpers import now_utc
    from domain.invitations import expire_overdue_invitations

    overdue = await create_invitation(test_tenant, "gastdocent", "a@example.org", "EMP-1",
                                      expiry_date=now_utc() - timedelta(days=1))
    future = await create_invitation(test_tenant, "gastdocent", "b@example.org", "EMP-1",
                                     expiry_date=now_utc() + timedelta(days=5))
    never = await create_invitation(test_tenant, "gastdocent", "c@example.org", "EMP-1",
                                    expiry_date=None)  # falls to tenant default (14d, future)

    n = await expire_overdue_invitations(test_tenant)
    assert n == 1
    assert (await Invitation.get(tenant=test_tenant, code=overdue["code"])).status == "expired"
    assert (await Invitation.get(tenant=test_tenant, code=future["code"])).status == "pending"
    assert (await Invitation.get(tenant=test_tenant, code=never["code"])).status == "pending"


async def test_zero_duration_never_expires(test_tenant, monkeypatch):
    """expiry_duration <= 0 → expiry_date None (never expires)."""
    import domain.invitations as di
    monkeypatch.setattr(di, "get_tenant_config", lambda t: {"expiry_duration": 0})
    created = await create_invitation(test_tenant, "gastdocent", "a@example.org", "EMP-1")
    assert (await Invitation.get(tenant=test_tenant, code=created["code"])).expiry_date is None


@pytest.mark.ui
async def test_accept_past_expiry_swept_on_claim(user, test_tenant):
    """A still-pending invite past its expiry_date is swept to expired on claim → dead-end."""
    from datetime import timedelta
    from ng_rdm.utils.helpers import now_utc
    created = await create_invitation(test_tenant, "gastdocent", "anna@example.org", "EMP-1",
                                      expiry_date=now_utc() - timedelta(hours=1))
    await user.open(f"/accept/{created['code']}")
    await user.should_see("verlopen")
    await user.should_not_see("Welkom")


@pytest.mark.ui
async def test_accept_missing_persona_shows_friendly_card(user, test_tenant, monkeypatch):
    """A valid invite whose persona is gone → friendly card, not a 500 (ui_guard)."""
    from services.persona_loader import UnknownPersonaError

    created = await create_invitation(test_tenant, "gastdocent", "anna@example.org", "EMP-1")

    def _boom(tenant, key):
        raise UnknownPersonaError(f"Unknown persona '{key}'")

    monkeypatch.setattr("routes.accept.get_persona_config", _boom)
    await user.open(f"/accept/{created['code']}")
    await user.should_see("kan op dit moment niet worden verwerkt")  # friendly fallback card
    await user.should_not_see("Welkom")  # the steps heading never renders
