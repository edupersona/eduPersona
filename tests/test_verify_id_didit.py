"""Didit ID-verification: the client's field extraction + the step card's decision handling.

Network is never touched — `services.didit.client._http_request` is the patchable seam
(like the webhook tests patch `_http_post`), and the card's `result_handler_didit` is
driven directly with a decision dict (like the OIDC/mobile tests drive their handlers).
"""
import pytest
from nicegui import ui
from unittest.mock import AsyncMock

from domain.invitations import apply_invite_to_state, create_invitation
from services.persona_loader import get_persona_config
from services.didit import client as didit_client
from services.didit.client import create_session, extract_id_fields
from steps import Steps
from steps.cards.verify_id_didit import VerifyIdDiditStep


# ── extract_id_fields ─────────────────────────────────────────────────────

_ID_BLOCK = {
    "first_name": "Elena",
    "last_name": "Martinez",
    "full_name": "Elena Martinez",
    "document_number": "YZA123456",
    "date_of_birth": "1985-03-15",
    "nationality": "NLD",
    "document_type": "Passport",
    "expiration_date": "2030-08-21",
    # blobs that must NOT be forwarded:
    "portrait_image": "base64...",
    "front_document_image": "base64...",
    "back_document_image": "base64...",
}


def test_extract_top_level_shape():
    decision = {"status": "Approved", "id_verification": _ID_BLOCK,
                "liveness": {"score": 95}, "face_match": {"score": 88}}
    out = extract_id_fields(decision)
    assert out["first_name"] == "Elena"
    assert out["last_name"] == "Martinez"
    assert out["document_number"] == "YZA123456"
    assert out["liveness_score"] == 95
    assert out["face_match_score"] == 88
    # image blobs are stripped
    assert "portrait_image" not in out
    assert "front_document_image" not in out


def test_extract_nested_and_plural_list_shape():
    """The polled decision may nest features and use plural/list keys — tolerate both."""
    decision = {
        "status": "Approved",
        "features": {
            "id_verifications": [_ID_BLOCK],
            "liveness_checks": [{"score": 71}],
            "face_matches": [{"score": 60}],
        },
    }
    out = extract_id_fields(decision)
    assert out["first_name"] == "Elena"
    assert out["liveness_score"] == 71
    assert out["face_match_score"] == 60


def test_extract_unknown_shape_is_empty():
    assert extract_id_fields({"status": "Declined"}) == {}


# ── create_session ────────────────────────────────────────────────────────

async def test_create_session_builds_payload(test_tenant, monkeypatch):
    seen: dict = {}

    async def fake_request(method, url, api_key, *, json=None):
        seen.update(method=method, url=url, api_key=api_key, json=json)
        return 201, {"session_id": "sess-1", "url": "https://verify.didit.me/session/tok"}

    monkeypatch.setattr(didit_client, "_http_request", fake_request)
    result = await create_session(test_tenant, "hvh:CODE:id_document", "http://localhost:8080/didit_callback?state=x")

    assert result["session_id"] == "sess-1"
    assert seen["method"] == "POST" and seen["url"].endswith("/session/")
    assert seen["api_key"] == "test-didit-api-key"
    assert seen["json"]["workflow_id"] == "test-didit-workflow-id"
    assert seen["json"]["vendor_data"] == "hvh:CODE:id_document"
    assert seen["json"]["callback"].endswith("state=x")


async def test_create_session_raises_on_error(test_tenant, monkeypatch):
    monkeypatch.setattr(didit_client, "_http_request", AsyncMock(return_value=(403, {"detail": "no credits"})))
    with pytest.raises(ValueError):
        await create_session(test_tenant, "vd", "http://cb")


# ── the step card ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _silence_notify(monkeypatch):
    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)


async def _id_step(test_tenant) -> tuple[Steps, VerifyIdDiditStep]:
    created = await create_invitation(test_tenant, "id_verificatie", "id@example.org", "EMP-9")
    state: dict = {}
    await apply_invite_to_state(test_tenant, state, created["code"])
    cfg = get_persona_config(test_tenant, "id_verificatie")
    steps = Steps(test_tenant, state, {"steps": cfg.steps})
    step = next(s for s in steps.step_instances if s.step_id == "id_document")
    assert isinstance(step, VerifyIdDiditStep)
    return steps, step


async def test_persona_loads_with_single_step(test_tenant):
    _steps, step = await _id_step(test_tenant)
    assert step.step_id == "id_document"
    assert len(_steps.step_instances) == 1


async def test_approved_decision_completes_with_id_fields(test_tenant):
    steps, step = await _id_step(test_tenant)
    await step.result_handler_didit({"status": "Approved", "id_verification": _ID_BLOCK,
                                     "liveness": {"score": 90}, "face_match": {"score": 80}})
    assert steps.outcomes["id_document"] == "completed"
    out = steps.outputs["id_document"]
    assert out["first_name"] == "Elena" and out["last_name"] == "Martinez"
    assert "portrait_image" not in out


async def test_declined_decision_fails_and_flags(test_tenant):
    steps, step = await _id_step(test_tenant)
    await step.result_handler_didit({"status": "Declined"})
    assert steps.outcomes["id_document"] == "failed"
    assert step.state.get("declined") is True
    assert "id_document" not in steps.outputs
