"""Phase D — persona-mode invitation lifecycle (create / accept / apply-to-state).

Shape B: rows written directly, no Guest. Validates persona + params, leaves
guest_id NULL, fires the callback only when configured, and never auto-skips
across personas for the same email. enqueue_callback is patched to observe calls.
"""

from unittest.mock import AsyncMock

import pytest

from domain.invitations_persona import (
    accept_persona_invitation,
    apply_persona_invite_to_state,
    create_persona_invitation,
)
from domain.models import Invitation
from domain.persona import MailRef, PersonaConfig
import domain.invitations_persona as ip
from services.persona_loader import PersonaParamsError, UnknownPersonaError


def _persona(callback_url=None) -> PersonaConfig:
    return PersonaConfig(
        display_name={"en": "X"}, steps=[],
        mail=MailRef(layout="l", body="b"), callback_url=callback_url,
    )


# --- create ---

async def test_create_happy_minimal(test_tenant):
    out = await create_persona_invitation(test_tenant, "gastdocent", "anna@example.org")
    assert out["status"] == "pending"
    assert out["persona_key"] == "gastdocent"
    assert out["given_name"] is None
    inv = await Invitation.get(id=out["id"])
    assert inv.guest_id is None  # type: ignore[attr-defined]  # Shape B: no Guest
    assert inv.invitation_email == "anna@example.org"


async def test_create_with_names_and_params(test_tenant):
    out = await create_persona_invitation(
        test_tenant, "gastdocent", "anna@example.org",
        given_name="Anna", family_name="Verver", client_ref="EMP-42",
        persona_params={"department": "CS"},
    )
    assert out["given_name"] == "Anna"
    assert out["family_name"] == "Verver"
    assert out["client_ref"] == "EMP-42"
    assert out["persona_params"] == {"department": "CS"}


async def test_create_unknown_persona_raises(test_tenant):
    with pytest.raises(UnknownPersonaError):
        await create_persona_invitation(test_tenant, "nope", "a@example.org")


async def test_create_invalid_params_raises(test_tenant):
    with pytest.raises(PersonaParamsError):
        await create_persona_invitation(
            test_tenant, "gastdocent", "a@example.org", persona_params={"bogus": "x"},
        )


async def test_create_callback_url_falls_back_to_persona_default(test_tenant, monkeypatch):
    monkeypatch.setattr(ip, "get_persona_config", lambda t, k: _persona(callback_url="https://persona-default/hook"))
    out = await create_persona_invitation(test_tenant, "gastdocent", "a@example.org")
    assert out["callback_url"] == "https://persona-default/hook"
    # explicit override wins
    out2 = await create_persona_invitation(test_tenant, "gastdocent", "a@example.org", callback_url="https://override/hook")
    assert out2["callback_url"] == "https://override/hook"


async def test_same_client_ref_produces_independent_rows(test_tenant):
    a = await create_persona_invitation(test_tenant, "gastdocent", "a@example.org", client_ref="REF1")
    b = await create_persona_invitation(test_tenant, "gastdocent", "a@example.org", client_ref="REF1")
    assert a["id"] != b["id"]
    assert a["code"] != b["code"]
    assert await Invitation.filter(client_ref="REF1").count() == 2


# --- accept ---

async def test_accept_flips_status_and_no_callback_when_unconfigured(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    out = await create_persona_invitation(test_tenant, "gastdocent", "a@example.org")  # no callback_url
    ok = await accept_persona_invitation(test_tenant, out["code"])
    assert ok is True
    inv = await Invitation.get(id=out["id"])
    assert inv.status == "accepted"
    assert inv.accepted_at is not None
    enqueue.assert_not_called()


async def test_accept_enqueues_callback_when_configured(test_tenant, monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)
    out = await create_persona_invitation(
        test_tenant, "gastdocent", "a@example.org", callback_url="https://client/hook",
    )
    await accept_persona_invitation(test_tenant, out["code"])
    enqueue.assert_awaited_once_with(test_tenant, out["id"])


async def test_accept_callback_failure_does_not_raise(test_tenant, monkeypatch):
    boom = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(ip, "enqueue_callback", boom)
    out = await create_persona_invitation(
        test_tenant, "gastdocent", "a@example.org", callback_url="https://client/hook",
    )
    ok = await accept_persona_invitation(test_tenant, out["code"])
    assert ok is True  # acceptance committed despite callback failure
    assert (await Invitation.get(id=out["id"])).status == "accepted"


async def test_accept_unknown_or_non_pending_returns_false(test_tenant, monkeypatch):
    monkeypatch.setattr(ip, "enqueue_callback", AsyncMock())
    assert await accept_persona_invitation(test_tenant, "no-such-code") is False
    out = await create_persona_invitation(test_tenant, "gastdocent", "a@example.org")
    await accept_persona_invitation(test_tenant, out["code"])
    assert await accept_persona_invitation(test_tenant, out["code"]) is False  # already accepted


# --- multi-persona-per-guest: independent invitations + callbacks, no auto-skip ---

async def test_multi_persona_same_email_independent(test_tenant, monkeypatch):
    monkeypatch.setattr(ip, "get_persona_config", lambda t, k: _persona(callback_url="https://client/hook"))
    enqueue = AsyncMock()
    monkeypatch.setattr(ip, "enqueue_callback", enqueue)

    a = await create_persona_invitation(test_tenant, "gastdocent", "same@example.org")
    b = await create_persona_invitation(test_tenant, "alumnus", "same@example.org")
    assert a["id"] != b["id"]

    await accept_persona_invitation(test_tenant, a["code"])
    await accept_persona_invitation(test_tenant, b["code"])
    # two independent callbacks — no cross-persona auto-skip (§2.1)
    assert enqueue.await_count == 2
    assert {await_args.args[1] for await_args in enqueue.await_args_list} == {a["id"], b["id"]}


# --- apply-to-state ---

async def test_apply_persona_invite_to_state(test_tenant):
    out = await create_persona_invitation(
        test_tenant, "gastdocent", "anna@example.org",
        given_name="Anna", family_name="Verver", persona_params={"department": "CS"},
    )
    state: dict = {}
    ok = await apply_persona_invite_to_state(test_tenant, state, out["code"])
    assert ok is True
    assert state["invite_code"] == out["code"]
    assert state["invitation_id"] == out["id"]
    assert state["persona_key"] == "gastdocent"
    assert state["persona_params"] == {"department": "CS"}
    assert state["guest_email"] == "anna@example.org"
    assert state["given_name"] == "Anna"
    assert state["family_name"] == "Verver"


async def test_apply_invalid_code_returns_false(test_tenant):
    assert await apply_persona_invite_to_state(test_tenant, {}, "bad-code") is False
