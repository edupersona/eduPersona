"""Phase B — webhook subsystem (payload builder + delivery state machine).

Envelope construction reads only from Invitation + step_outputs (§2.7); the state
machine implements 4xx-terminal / 5xx-retry with exponential backoff (gotcha 4).
`_http_post` and `now_utc` are patched as seams; no real network, deterministic time.
"""

from datetime import datetime, timedelta, timezone

import pytest

from domain.models import Invitation, WebhookDelivery
from domain.persona import MailRef, PersonaConfig
from services.webhook import delivery as delivery_mod
from services.webhook import payload as payload_mod
from services.webhook.delivery import (
    BACKOFF,
    MAX_ATTEMPTS,
    _deliver,
    enqueue_callback,
    process_pending,
)
from services.webhook.payload import build_payload

FIXED = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_n = {"i": 0}


def _persona(callback_outputs: list[str]) -> PersonaConfig:
    return PersonaConfig(
        display_name={"en": "X"}, steps=[],
        mail=MailRef(layout="l", body="b"), callback_outputs=callback_outputs,
    )


async def _mk_inv(tenant: str, **kw) -> Invitation:
    _n["i"] += 1
    base: dict = dict(
        tenant=tenant, code=f"WBK{_n['i']}", guest_id=f"G{_n['i']}",
        invitation_email="anna@example.org", persona_key="gastdocent",
        callback_url="https://client.example.org/hook",
    )
    base.update(kw)
    return await Invitation.create(**base)


# --- envelope construction ---

async def test_payload_universal_fields_and_verifications(test_tenant, monkeypatch):
    monkeypatch.setattr(payload_mod, "get_persona_config", lambda t, k: _persona(["eduid"]))
    inv = await _mk_inv(
        test_tenant, guest_id="EMP-42",
        persona_params={"department": "CS"}, accepted_at=FIXED,
        step_outputs={"eduid": {"sub": "abc", "uids": ["anna"]}},
    )
    p = build_payload(inv, test_tenant)
    assert p["tenant"] == test_tenant
    assert p["persona"] == "gastdocent"
    assert p["invitation_code"] == inv.code
    assert p["guest_id"] == "EMP-42"
    assert p["email"] == "anna@example.org"
    assert p["persona_params"] == {"department": "CS"}
    assert p["completed_at"] == FIXED.isoformat()
    assert p["verifications"] == {"eduid": {"sub": "abc", "uids": ["anna"]}}


async def test_payload_missing_source_omitted(test_tenant, monkeypatch):
    monkeypatch.setattr(payload_mod, "get_persona_config", lambda t, k: _persona(["eduid", "institutional"]))
    inv = await _mk_inv(test_tenant, step_outputs={"eduid": {"sub": "x"}})
    p = build_payload(inv, test_tenant)
    assert set(p["verifications"]) == {"eduid"}  # institutional declared but absent → omitted


async def test_payload_persona_without_outputs(test_tenant, monkeypatch):
    monkeypatch.setattr(payload_mod, "get_persona_config", lambda t, k: _persona([]))
    inv = await _mk_inv(test_tenant, step_outputs={"eduid": {"sub": "x"}})
    p = build_payload(inv, test_tenant)
    assert p["verifications"] == {}


async def test_payload_completed_at_legacy_string(test_tenant, monkeypatch):
    """Legacy '%Y-%m-%d / %H:%M:%S' accepted_at strings normalize to ISO (gotcha 7)."""
    monkeypatch.setattr(payload_mod, "get_persona_config", lambda t, k: _persona([]))
    inv = await _mk_inv(test_tenant)
    inv.accepted_at = "2026-01-01 / 13:00:00"  # type: ignore[assignment]
    p = build_payload(inv, test_tenant)
    assert "T" in p["completed_at"]  # ISO 8601, not the legacy slash format


# --- state machine ---

async def _mk_delivery(tenant, **kw) -> WebhookDelivery:
    inv = await _mk_inv(tenant)
    base: dict = dict(invitation=inv, payload={"hello": "world"}, status="pending")
    base.update(kw)
    return await WebhookDelivery.create(**base)


async def test_deliver_2xx_delivered(test_tenant, monkeypatch):
    monkeypatch.setattr(delivery_mod, "_http_post", _const(200))
    d = await _mk_delivery(test_tenant)
    out = await _deliver(d.id)
    assert out is not None
    assert out.status == "delivered"
    assert out.last_status_code == 200
    assert out.next_retry_at is None
    assert out.attempt_n == 1


async def test_deliver_4xx_terminal(test_tenant, monkeypatch):
    monkeypatch.setattr(delivery_mod, "_http_post", _const(400))
    d = await _mk_delivery(test_tenant)
    out = await _deliver(d.id)
    assert out is not None
    assert out.status == "failed"
    assert out.last_status_code == 400
    assert out.next_retry_at is None  # 4xx is terminal — no retry scheduled


async def test_deliver_5xx_schedules_retry(test_tenant, monkeypatch):
    monkeypatch.setattr(delivery_mod, "_http_post", _const(503))
    monkeypatch.setattr(delivery_mod, "now_utc", lambda: FIXED)
    d = await _mk_delivery(test_tenant)
    out = await _deliver(d.id)
    assert out is not None
    assert out.status == "failed"
    assert out.attempt_n == 1
    assert out.next_retry_at == FIXED + timedelta(seconds=BACKOFF[0])


async def test_deliver_network_error_retries(test_tenant, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(delivery_mod, "_http_post", boom)
    monkeypatch.setattr(delivery_mod, "now_utc", lambda: FIXED)
    d = await _mk_delivery(test_tenant)
    out = await _deliver(d.id)
    assert out is not None
    assert out.status == "failed"
    assert out.last_status_code is None
    assert "connection refused" in (out.last_error or "")
    assert out.next_retry_at == FIXED + timedelta(seconds=BACKOFF[0])


async def test_deliver_max_attempts_terminal(test_tenant, monkeypatch):
    monkeypatch.setattr(delivery_mod, "_http_post", _const(500))
    monkeypatch.setattr(delivery_mod, "now_utc", lambda: FIXED)
    d = await _mk_delivery(test_tenant, attempt_n=MAX_ATTEMPTS - 1, status="failed")
    out = await _deliver(d.id)
    assert out is not None
    assert out.attempt_n == MAX_ATTEMPTS
    assert out.status == "failed"
    assert out.next_retry_at is None  # exhausted — no further retry


# --- enqueue + process_pending ---

async def test_enqueue_no_callback_url_noop(test_tenant):
    inv = await _mk_inv(test_tenant, callback_url=None)
    out = await enqueue_callback(test_tenant, inv.id)
    assert out is None
    assert await WebhookDelivery.all().count() == 0


async def test_enqueue_creates_and_delivers(test_tenant, monkeypatch):
    monkeypatch.setattr(payload_mod, "get_persona_config", lambda t, k: _persona(["eduid"]))
    monkeypatch.setattr(delivery_mod, "_http_post", _const(200))
    inv = await _mk_inv(test_tenant, step_outputs={"eduid": {"sub": "x"}})
    out = await enqueue_callback(test_tenant, inv.id)
    assert out is not None
    assert out.status == "delivered"
    assert out.payload["verifications"] == {"eduid": {"sub": "x"}}
    assert await WebhookDelivery.all().count() == 1


async def test_process_pending_refires_due_skips_future_and_exhausted(test_tenant, monkeypatch):
    monkeypatch.setattr(delivery_mod, "_http_post", _const(200))
    monkeypatch.setattr(delivery_mod, "now_utc", lambda: FIXED)
    due = await _mk_delivery(test_tenant, status="failed", attempt_n=1, next_retry_at=FIXED - timedelta(seconds=1))
    future = await _mk_delivery(test_tenant, status="failed", attempt_n=1, next_retry_at=FIXED + timedelta(hours=1))
    exhausted = await _mk_delivery(test_tenant, status="failed", attempt_n=MAX_ATTEMPTS, next_retry_at=None)
    delivered = await _mk_delivery(test_tenant, status="delivered", next_retry_at=None)

    count = await process_pending()
    assert count == 1  # only the due one
    assert (await WebhookDelivery.get(id=due.id)).status == "delivered"
    assert (await WebhookDelivery.get(id=future.id)).status == "failed"
    assert (await WebhookDelivery.get(id=exhausted.id)).status == "failed"
    assert (await WebhookDelivery.get(id=delivered.id)).status == "delivered"


def _const(code: int):
    async def _post(url, payload, headers):
        return code
    return _post
