"""Didit ID-verification: field extraction, session create, QR, and the polling card.

Network is never touched — `services.didit.client._http_request` is the patchable seam
(like the webhook tests patch `_http_post`), and the card's `_poll` is driven with a
monkeypatched `get_decision` (the decision the phone would have produced at Didit).
"""
import pytest
from nicegui import ui
from unittest.mock import AsyncMock

from domain.invitations import apply_invite_to_state, create_invitation
from services.persona_loader import get_persona_config
from services.didit import client as didit_client
from services.didit.client import create_session, extract_id_fields
from services.didit.qr import qr_data_uri
from steps import Steps
from steps.cards import verify_id_didit
from steps.cards.verify_id_didit import VerifyIdDiditStep


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


# ── extract_id_fields ─────────────────────────────────────────────────────

def test_extract_top_level_shape():
    decision = {"status": "Approved", "id_verification": _ID_BLOCK,
                "liveness": {"score": 95}, "face_match": {"score": 88}}
    out = extract_id_fields(decision)
    assert out["first_name"] == "Elena"
    assert out["last_name"] == "Martinez"
    assert out["document_number"] == "YZA123456"
    assert out["liveness_score"] == 95
    assert out["face_match_score"] == 88
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


def test_extract_real_didit_shape():
    """Regression against a real Didit decision (2026-07): top-level plural LIST features,
    `features` is a list of strings, image/video URLs and None fields must be dropped."""
    decision = {
        "status": "Approved",
        "features": ["ID_VERIFICATION", "LIVENESS", "FACE_MATCH"],
        "id_verifications": [{
            "status": "Approved", "document_type": "Identity Card", "document_subtype": None,
            "document_number": "IY7911P49", "personal_number": None, "portrait_image": None,
            "front_image": None, "back_image": None, "date_of_birth": "1959-09-16", "age": None,
            "expiration_date": "2035-01-28", "date_of_issue": "2025-01-28", "issuing_state": "NLD",
            "issuing_state_name": None, "first_name": "Peter", "last_name": "Kleijnjan",
            "full_name": "Peter Kleijnjan", "gender": None, "address": None,
            "formatted_address": None, "nationality": "NLD", "mrz": None, "warnings": [],
        }],
        "liveness_checks": [{"status": "Approved", "method": "PASSIVE", "score": 98.92}],
        "face_matches": [{"status": "Approved", "score": 76.97}],
    }
    out = extract_id_fields(decision)
    assert out == {
        "document_type": "Identity Card", "document_number": "IY7911P49",
        "date_of_birth": "1959-09-16", "expiration_date": "2035-01-28",
        "date_of_issue": "2025-01-28", "issuing_state": "NLD", "first_name": "Peter",
        "last_name": "Kleijnjan", "full_name": "Peter Kleijnjan", "nationality": "NLD",
        "liveness_score": 98.92, "face_match_score": 76.97,
    }
    assert "portrait_image" not in out and "front_image" not in out


# ── QR ─────────────────────────────────────────────────────────────────────

def test_qr_data_uri_is_svg_data_uri():
    uri = qr_data_uri("https://verify.didit.me/session/tok")
    assert uri.startswith("data:image/svg+xml")


# ── create_session ──────────────────────────────────────────────────────────

async def test_create_session_builds_payload_without_callback(test_tenant, monkeypatch):
    seen: dict = {}

    async def fake_request(method, url, api_key, *, json=None):
        seen.update(method=method, url=url, api_key=api_key, json=json)
        return 201, {"session_id": "sess-1", "url": "https://verify.didit.me/session/tok"}

    monkeypatch.setattr(didit_client, "_http_request", fake_request)
    result = await create_session(test_tenant, "hvh:CODE:id_document")

    assert result["session_id"] == "sess-1"
    assert seen["method"] == "POST" and seen["url"].endswith("/session/")
    assert seen["api_key"] == "test-didit-api-key"
    assert seen["json"] == {"workflow_id": "test-didit-workflow-id",
                            "vendor_data": "hvh:CODE:id_document", "language": "nl"}
    assert "callback" not in seen["json"]  # in-app polling → no redirect


async def test_create_session_raises_on_error(test_tenant, monkeypatch):
    monkeypatch.setattr(didit_client, "_http_request", AsyncMock(return_value=(403, {"detail": "no credits"})))
    with pytest.raises(ValueError):
        await create_session(test_tenant, "vd")


# ── the polling card ─────────────────────────────────────────────────────────

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


def _fake_decision(monkeypatch, decision: dict):
    monkeypatch.setattr(verify_id_didit, "get_decision", AsyncMock(return_value=decision))


async def test_persona_loads_with_single_step(test_tenant):
    steps, step = await _id_step(test_tenant)
    assert step.step_id == "id_document"
    assert len(steps.step_instances) == 1
    assert step.state["phase"] == "start"


async def test_poll_approved_completes_with_id_fields(test_tenant, monkeypatch):
    steps, step = await _id_step(test_tenant)
    step.state.update(phase="awaiting", session_id="sess-1")
    _fake_decision(monkeypatch, {"status": "Approved", "id_verification": _ID_BLOCK,
                                 "liveness": {"score": 90}, "face_match": {"score": 80}})
    await step._poll()
    assert steps.outcomes["id_document"] == "completed"
    out = steps.outputs["id_document"]
    assert out["first_name"] == "Elena" and out["last_name"] == "Martinez"
    assert "portrait_image" not in out


async def test_poll_declined_moves_to_declined_phase(test_tenant, monkeypatch):
    steps, step = await _id_step(test_tenant)
    step.state.update(phase="awaiting", session_id="sess-1")
    _fake_decision(monkeypatch, {"status": "Declined"})
    await step._poll()
    assert step.state["phase"] == "declined"
    assert "id_document" not in steps.outcomes
    assert step.state.get("status_message")


async def test_poll_in_progress_keeps_waiting(test_tenant, monkeypatch):
    steps, step = await _id_step(test_tenant)
    step.state.update(phase="awaiting", session_id="sess-1")
    _fake_decision(monkeypatch, {"status": "In Progress"})
    await step._poll()
    assert step.state["phase"] == "awaiting"
    assert "id_document" not in steps.outcomes


async def test_poll_noop_when_not_awaiting(test_tenant, monkeypatch):
    steps, step = await _id_step(test_tenant)
    called = AsyncMock(return_value={"status": "Approved"})
    monkeypatch.setattr(verify_id_didit, "get_decision", called)
    await step._poll()  # phase is still 'start'
    called.assert_not_awaited()
