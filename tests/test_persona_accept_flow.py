"""Phase G — persona-mode accept flow.

Domain-level: the persona step lifecycle keys OIDC output by IdP, persists
state['outputs'] to Invitation.step_outputs at finalize, and fires the callback
only when configured. Plus one NiceGUI render check (route registered via main.py;
no top-level route import — gotcha 2). The conftest services.webhook re-link
(gotcha 1) keeps the UI test robust.
"""

from unittest.mock import AsyncMock

import pytest

import domain.invitations as ip
from domain.invitations import (
    apply_invite_to_state,
    create_invitation,
)
from domain.models import Invitation
from domain.step_cards import OIDCLoginStep, Steps, StepResult
from services.persona_loader import get_persona_config

USERINFO = {"sub": "abc", "uids": ["anna"], "given_name": "Anna"}


async def _build_steps(tenant, code):
    state: dict = {}
    await apply_invite_to_state(tenant, state, code)
    cfg = get_persona_config(tenant, "gastdocent")
    steps = Steps(tenant, state, {"steps": cfg.steps})
    # mirror the route: first step (verify_invite) is auto-recorded completed
    await steps.record(steps.step_instances[0].step_id, StepResult("completed"))
    return steps


async def _oidc_step(steps) -> OIDCLoginStep:
    step = next(s for s in steps.step_instances if s.step_id == "eduid_login")
    assert isinstance(step, OIDCLoginStep)
    return step


async def test_lifecycle_persists_outputs_and_fires_callback(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    created = await create_invitation(
        test_tenant, "gastdocent", "anna@example.org", callback_url="https://client/hook",
    )
    steps = await _build_steps(test_tenant, created["code"])

    # simulate the eduID OIDC return
    oidc = await _oidc_step(steps)
    await oidc.result_handler(USERINFO, {}, {})

    inv = await Invitation.get(id=created["id"])
    assert inv.status == "accepted"
    # OIDC output keyed by IdP name, not step id (gotcha 10)
    assert inv.step_outputs == {"eduid": USERINFO}
    assert steps.outcomes["finalize"] == "completed"
    enqueue.assert_awaited_once_with(test_tenant, created["id"])


async def test_lifecycle_no_callback_when_unconfigured(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    created = await create_invitation(test_tenant, "gastdocent", "a@example.org")  # no callback_url
    steps = await _build_steps(test_tenant, created["code"])

    oidc = await _oidc_step(steps)
    await oidc.result_handler(USERINFO, {}, {})

    inv = await Invitation.get(id=created["id"])
    assert inv.status == "accepted"
    assert inv.step_outputs == {"eduid": USERINFO}
    enqueue.assert_not_called()


async def test_oidc_output_keyed_by_idp_not_step_id(test_tenant, monkeypatch):
    monkeypatch.setattr(ip, "enqueue_callback", AsyncMock())
    created = await create_invitation(test_tenant, "gastdocent", "a@example.org")
    steps = await _build_steps(test_tenant, created["code"])
    oidc = await _oidc_step(steps)
    await oidc.result_handler(USERINFO, {}, {})
    assert "eduid" in steps.state["outputs"]
    assert "eduid_login" not in steps.state["outputs"]  # step_id is NOT used as the output key


# --- one NiceGUI render check (route comes from main.py registration) ---

@pytest.mark.ui
async def test_accept_persona_page_renders(user, test_tenant):
    created = await create_invitation(
        test_tenant, "gastdocent", "anna@example.org", given_name="Anna",
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
