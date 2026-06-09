"""VerifyMobileStep — the in-card code-exchange transaction.

Drives the step's handlers directly (like the OIDC tests drive `result_handler`):
a bad number doesn't send; a good number reveals the code stage; a wrong code
records nothing and stays put; the right code completes with the mobile under the
step's own output. `ui.notify` is patched out — it needs a NiceGUI client context.
"""
import re

import pytest

import domain.step_cards as sc
from domain.invitations import apply_invite_to_state, create_invitation
from domain.step_cards import Steps, VerifyMobileStep
from services.persona_loader import get_persona_config


@pytest.fixture(autouse=True)
def _silence_notify(monkeypatch):
    monkeypatch.setattr(sc.ui, "notify", lambda *a, **k: None)


async def _mobile_step(test_tenant) -> tuple[Steps, VerifyMobileStep]:
    created = await create_invitation(test_tenant, "alumnus", "a@example.org", "EMP-1")
    state: dict = {}
    await apply_invite_to_state(test_tenant, state, created["code"])
    cfg = get_persona_config(test_tenant, "alumnus")
    steps = Steps(test_tenant, state, {"steps": cfg.steps})
    step = next(s for s in steps.step_instances if s.step_id == "verify_mobile")
    assert isinstance(step, VerifyMobileStep)
    return steps, step


async def test_invalid_number_does_not_send(test_tenant):
    steps, step = await _mobile_step(test_tenant)
    steps.state["mobile_number"] = "abc"
    step._send_code()
    assert step._code is None
    assert not steps.state.get("code_sent")


async def test_send_reveals_code_stage_then_verifies(test_tenant):
    steps, step = await _mobile_step(test_tenant)
    steps.state["mobile_number"] = "+31 6 12345678"
    step._send_code()
    assert steps.state["code_sent"] is True
    assert step._code is not None and re.fullmatch(r"\d{4}", step._code)

    # wrong code → no outcome recorded, transaction stays open
    steps.state["mobile_code"] = "0000" if step._code != "0000" else "1111"
    await step._verify()
    assert "verify_mobile" not in steps.outcomes

    # correct code → completed, mobile under the step's own output
    steps.state["mobile_code"] = step._code
    await step._verify()
    assert steps.outcomes["verify_mobile"] == "completed"
    assert steps.state["outputs"]["verify_mobile"] == {"mobile": "+31 6 12345678"}


async def test_reset_returns_to_number_stage(test_tenant):
    steps, step = await _mobile_step(test_tenant)
    steps.state["mobile_number"] = "+31612345678"
    step._send_code()
    step._reset()
    assert step._code is None
    assert steps.state["code_sent"] is False
