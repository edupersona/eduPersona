"""Self-service admin onboarding — the `admin` persona's completion action.

Covers: the CollectIntake card output shape; the `completion` config parse; the
settings.json write primitive (idempotent, isolated to a temp file); the provision +
notify service; and the end-to-end lifecycle proving accept_invitation runs the action
in place of a webhook.
"""
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import domain.invitations as ip
import services.admin_onboarding as ao
import services.settings as ss
from domain.invitations import apply_invite_to_state, create_invitation
from domain.models import Invitation
from services.persona_loader import get_persona_config
from steps import OIDCLoginStep, Steps
from steps.cards.collect_intake import CollectIntakeStep


# ── helpers ────────────────────────────────────────────────────────────────

async def _admin_steps(test_tenant, **invite_kw) -> tuple[Steps, dict]:
    created = await create_invitation(
        test_tenant, "admin", "jane@example.org", "jane@example.org",
        given_name="Jane", family_name="Doe", **invite_kw,
    )
    state: dict = {}
    await apply_invite_to_state(test_tenant, state, created["code"])
    cfg = get_persona_config(test_tenant, "admin")
    return Steps(test_tenant, state, {"steps": cfg.steps}), created


async def _intake_step(steps) -> CollectIntakeStep:
    step = next(s for s in steps.step_instances if s.step_id == "collect_intake")
    assert isinstance(step, CollectIntakeStep)
    return step


async def _drive_oidc(steps, step_id, userinfo) -> None:
    step = next(s for s in steps.step_instances if s.step_id == step_id)
    assert isinstance(step, OIDCLoginStep)
    await step.result_handler(userinfo, {}, {})


# ── persona config parsing ───────────────────────────────────────────────

def test_admin_persona_completion_config(test_tenant):
    cfg = get_persona_config(test_tenant, "admin")
    assert cfg.callback_url is None
    assert cfg.completion is not None
    assert cfg.completion.action == "admin_onboarding"
    assert cfg.completion.authz == ["invitations", "simulator"]
    assert cfg.completion.notify_email == "admin@your-domain.com"


# ── CollectIntake card ─────────────────────────────────────────────────────

async def test_collect_intake_records_fields(test_tenant):
    steps, _ = await _admin_steps(test_tenant)
    step = await _intake_step(steps)
    step.state["organisatie"] = "ACME University"
    step.state["toepassingsscenario"] = "  SSO for guest lecturers  "
    await step._submit()
    assert steps.outcomes["collect_intake"] == "completed"
    assert steps.outputs["collect_intake"] == {
        "organisatie": "ACME University",
        "toepassingsscenario": "SSO for guest lecturers",  # trimmed
    }


async def test_collect_intake_nullable_when_empty(test_tenant):
    steps, _ = await _admin_steps(test_tenant)
    step = await _intake_step(steps)
    await step._submit()  # nothing typed
    assert steps.outputs["collect_intake"] == {"organisatie": None, "toepassingsscenario": None}


# ── settings write primitive ───────────────────────────────────────────────

@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """Point the settings service at a writable copy so upsert tests don't mutate
    the frozen fixture; restore the cache after."""
    dst = tmp_path / "settings.json"
    shutil.copy(ss._settings_path(), dst)
    monkeypatch.setenv("EDUPERSONA_SETTINGS_FILE", str(dst))
    ss.reload_settings()
    yield dst
    monkeypatch.undo()
    ss.reload_settings()


def test_upsert_tenant_admin_appends_and_persists(temp_settings):
    ss.upsert_tenant_admin("hvh", "sub-123", "Jane Doe", ["invitations", "simulator"])
    admins = ss.get_tenant_config("hvh")["admins"]
    entry = next(a for a in admins if a.get("user") == "sub-123")
    assert entry == {"display_name": "Jane Doe", "user": "sub-123", "authz": ["invitations", "simulator"]}
    # persisted to disk
    on_disk = json.loads(Path(temp_settings).read_text())
    assert any(a["user"] == "sub-123" for a in on_disk["tenants"]["hvh"]["admins"])


def test_upsert_tenant_admin_idempotent_on_sub(temp_settings):
    before = len(ss.get_tenant_config("hvh")["admins"])
    ss.upsert_tenant_admin("hvh", "sub-123", "Jane Doe", ["invitations"])
    ss.upsert_tenant_admin("hvh", "sub-123", "Jane D. Updated", ["invitations", "simulator"])
    admins = ss.get_tenant_config("hvh")["admins"]
    matches = [a for a in admins if a.get("user") == "sub-123"]
    assert len(matches) == 1                       # updated, not duplicated
    assert len(admins) == before + 1
    assert matches[0]["display_name"] == "Jane D. Updated"
    assert matches[0]["authz"] == ["invitations", "simulator"]


# ── provision + notify service ─────────────────────────────────────────────

async def test_complete_admin_onboarding_provisions_and_notifies(test_tenant, monkeypatch):
    upsert = Mock()
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(ao, "upsert_tenant_admin", upsert)
    monkeypatch.setattr(ao, "send_postmark_email", send)

    created = await create_invitation(
        test_tenant, "admin", "jane@example.org", "jane@example.org",
        given_name="Jane", family_name="Doe",
    )
    inv = await Invitation.get(tenant=test_tenant, code=created["code"])
    inv.step_outputs = {
        "eduid_login": {"sub": "edu-sub-xyz"},
        "collect_intake": {"organisatie": "ACME", "toepassingsscenario": "SSO"},
    }

    cfg = get_persona_config(test_tenant, "admin")
    await ao.complete_admin_onboarding(test_tenant, inv, cfg.completion)

    upsert.assert_called_once_with(test_tenant, "edu-sub-xyz", "Jane Doe", ["invitations", "simulator"])
    send.assert_awaited_once()
    body = send.await_args.args[0]
    assert body["to_email"] == "admin@your-domain.com"
    assert "edu-sub-xyz" in body["text_body"]
    assert "ACME" in body["text_body"] and "SSO" in body["text_body"]


async def test_complete_admin_onboarding_skips_without_sub(test_tenant, monkeypatch):
    upsert = Mock()
    monkeypatch.setattr(ao, "upsert_tenant_admin", upsert)
    monkeypatch.setattr(ao, "send_postmark_email", AsyncMock(return_value=True))

    created = await create_invitation(
        test_tenant, "admin", "jane@example.org", "jane@example.org", given_name="Jane",
    )
    inv = await Invitation.get(tenant=test_tenant, code=created["code"])
    inv.step_outputs = {"collect_intake": {"organisatie": "ACME"}}  # no eduid_login.sub

    cfg = get_persona_config(test_tenant, "admin")
    await ao.complete_admin_onboarding(test_tenant, inv, cfg.completion)
    upsert.assert_not_called()


# ── end-to-end lifecycle through accept_invitation ─────────────────────────

async def test_lifecycle_provisions_admin_instead_of_callback(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    upsert = Mock()
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    monkeypatch.setattr(ao, "upsert_tenant_admin", upsert)
    monkeypatch.setattr(ao, "send_postmark_email", send)

    steps, created = await _admin_steps(test_tenant)
    await _drive_oidc(steps, "eduid_login", {"sub": "edu-sub-xyz", "given_name": "Jane"})
    step = await _intake_step(steps)
    step.state["organisatie"] = "ACME University"
    step.state["toepassingsscenario"] = "Guest-lecturer SSO"
    await step._submit()

    assert steps.all_steps_done
    await steps.register()

    inv = await Invitation.get(tenant=test_tenant, code=created["code"])
    assert inv.status == "accepted"
    assert inv.step_outputs["eduid_login"]["sub"] == "edu-sub-xyz"
    enqueue.assert_not_called()  # admin persona has no callback_url → no webhook
    upsert.assert_called_once_with(test_tenant, "edu-sub-xyz", "Jane Doe", ["invitations", "simulator"])
    send.assert_awaited_once()
    assert "ACME University" in send.await_args.args[0]["text_body"]
