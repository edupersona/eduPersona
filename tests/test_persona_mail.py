"""Persona-aware mail composition.

Template rendering (body wrapped in layout), missing-persona error, and sender
override precedence. Transport is patched; no network.
"""

from unittest.mock import AsyncMock

import pytest

import services.postmark.postmark as pp
from services.postmark.postmark import (
    prepare_invite_message,
    send_invitation_mail,
)
from services.persona_loader import UnknownPersonaError


def _inv(**kw) -> dict:
    base = {
        "id": 1, "code": "ABC123", "status": "pending",
        "persona_key": "gastdocent", "guest_id": "EMP-1",
        "invitation_email": "anna@example.org",
        "given_name": "Anna", "family_name": "Verver",
        "persona_params": {}, "callback_url": None,
        "sender_email": None, "sender_name": None,
    }
    base.update(kw)
    return base


async def test_prepare_renders_body_in_layout(test_tenant):
    msg = await prepare_invite_message(
        _inv(persona_params={"personal_message": "Welkom bij het team!", "department": "Informatica"}),
        test_tenant,
    )
    html = msg["html_body"]
    assert "Anna" in html                         # given_name greeting
    assert "Gastdocent" in html                    # persona display_name (nl)
    assert "Welkom bij het team!" in html          # persona_params personal_message block
    assert "Informatica" in html                   # department block
    assert "/accept/ABC123" in html                # accept_url
    assert "eduPersona" in html                    # layout frame
    assert msg["to_email"] == "anna@example.org"
    assert msg["subject"] == "Uitnodiging: Gastdocent"
    assert msg["text_body"].strip()                # plain-text alternative rendered


async def test_prepare_greeting_fallback_without_name(test_tenant):
    msg = await prepare_invite_message(_inv(given_name=None), test_tenant)
    assert "collega" in msg["html_body"]           # falls back when no given_name


async def test_prepare_missing_persona_raises(test_tenant):
    with pytest.raises(UnknownPersonaError):
        await prepare_invite_message(_inv(persona_key="nope"), test_tenant)


async def test_sender_default_from_tenant(test_tenant):
    msg = await prepare_invite_message(_inv(), test_tenant)
    assert msg["from_email"] == "noreply@edupersona.nl"
    assert msg["from_name"] == "eduPersona"


async def test_sender_override_wins(test_tenant):
    msg = await prepare_invite_message(
        _inv(sender_email="dean@uva.nl", sender_name="De Decaan"), test_tenant,
    )
    assert msg["from_email"] == "dean@uva.nl"
    assert msg["from_name"] == "De Decaan"


async def test_send_invitation_mail_calls_transport(test_tenant, monkeypatch):
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(pp, "send_postmark_email", sent)
    ok = await send_invitation_mail(test_tenant, _inv())
    assert ok is True
    sent.assert_awaited_once()
    assert sent.await_args is not None
    email_data = sent.await_args.args[0]
    assert email_data["to_email"] == "anna@example.org"
    assert email_data["subject"] == "Uitnodiging: Gastdocent"
