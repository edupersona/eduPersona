"""Invitation API — POST/GET/list/resend/DELETE over HTTP via the ASGI test client."""

import pytest

import routes.api.invitations as ep
from domain.models import Invitation, WebhookDelivery

BASE = "/api/v1/hvh/invitations"


@pytest.fixture(autouse=True)
def _no_real_mail(monkeypatch):
    """The endpoint sends real Postmark mail; keep these API tests offline.

    Individual tests (e.g. mail-failure) re-patch this attr to assert behaviour.
    """
    async def _noop(tenant, invitation):
        return None
    monkeypatch.setattr(ep, "_send_mail_best_effort", _noop)


async def _post(api_client, **body):
    body.setdefault("guest_id", "EMP-1")  # required field; tests that care pass their own
    return await api_client.post(BASE, json=body)


async def test_post_happy(api_client):
    r = await _post(api_client, persona_key="gastdocent", email="anna@example.org",
                    given_name="Anna", guest_id="EMP-42")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["persona_key"] == "gastdocent"
    assert data["guest_id"] == "EMP-42"
    assert data["status"] == "pending"
    assert data["accept_url"].endswith(f"/accept/{data['code']}")
    assert await Invitation.filter(code=data["code"]).count() == 1


async def test_post_unknown_persona_404(api_client):
    r = await _post(api_client, persona_key="nope", email="a@example.org")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "NOT_FOUND"


async def test_post_invalid_email_400(api_client):
    r = await _post(api_client, persona_key="gastdocent", email="not-an-email")
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "VALIDATION_ERROR"


async def test_post_missing_guest_id_422(api_client):
    r = await api_client.post(BASE, json={"persona_key": "gastdocent", "email": "a@example.org"})
    assert r.status_code == 422  # required by the pydantic schema


async def test_post_blank_guest_id_422(api_client):
    r = await _post(api_client, persona_key="gastdocent", email="a@example.org", guest_id="   ")
    assert r.status_code == 422  # StringConstraints strips → empty → rejected


async def test_post_invalid_params_400(api_client):
    r = await _post(api_client, persona_key="gastdocent", email="a@example.org",
                    persona_params={"bogus": "x"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "VALIDATION_ERROR"


async def test_post_same_guest_id_two_rows(api_client):
    a = (await _post(api_client, persona_key="gastdocent", email="a@example.org", guest_id="R1")).json()["data"]
    b = (await _post(api_client, persona_key="gastdocent", email="a@example.org", guest_id="R1")).json()["data"]
    assert a["id"] != b["id"]
    assert await Invitation.filter(guest_id="R1").count() == 2


async def test_list_filters(api_client):
    await _post(api_client, persona_key="gastdocent", email="x@example.org", guest_id="R1")
    await _post(api_client, persona_key="gastdocent", email="y@example.org", guest_id="R2")
    # filter by guest_id
    r = await api_client.get(BASE, params={"guest_id": "R1"})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["invitation_email"] == "x@example.org"
    # filter by email
    r2 = await api_client.get(BASE, params={"email": "y@example.org"})
    assert r2.json()["meta"]["total"] == 1
    # filter by persona_key
    r3 = await api_client.get(BASE, params={"persona_key": "gastdocent"})
    assert r3.json()["meta"]["total"] == 2


async def test_get_single_with_webhook_deliveries(api_client):
    created = (await _post(api_client, persona_key="gastdocent", email="a@example.org")).json()["data"]
    inv = await Invitation.get(id=created["id"])
    await WebhookDelivery.create(invitation=inv, payload={"x": 1}, status="delivered", attempt_n=1, last_status_code=200)

    r = await api_client.get(f"{BASE}/{created['id']}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["id"] == created["id"]
    assert len(data["webhook_deliveries"]) == 1
    assert data["webhook_deliveries"][0]["status"] == "delivered"
    assert data["webhook_deliveries"][0]["last_status_code"] == 200


async def test_get_single_404(api_client):
    r = await api_client.get(f"{BASE}/99999")
    assert r.status_code == 404


async def test_get_by_code(api_client):
    created = (await _post(api_client, persona_key="gastdocent", email="a@example.org")).json()["data"]
    r = await api_client.get(f"{BASE}/code/{created['code']}")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == created["id"]


async def test_resend(api_client):
    created = (await _post(api_client, persona_key="gastdocent", email="a@example.org")).json()["data"]
    r = await api_client.post(f"{BASE}/{created['id']}/resend")
    assert r.status_code == 200
    assert r.json()["data"]["id"] == created["id"]


async def test_delete(api_client):
    created = (await _post(api_client, persona_key="gastdocent", email="a@example.org")).json()["data"]
    r = await api_client.delete(f"{BASE}/{created['id']}")
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] is True
    assert await Invitation.filter(id=created["id"]).count() == 0


async def test_mail_failure_tolerated(api_client, monkeypatch):
    async def boom(tenant, invitation):
        raise RuntimeError("postmark down")
    monkeypatch.setattr(ep, "_send_mail_best_effort", boom)
    r = await _post(api_client, persona_key="gastdocent", email="a@example.org")
    assert r.status_code == 200  # invitation persisted despite mail failure
    assert await Invitation.filter(code=r.json()["data"]["code"]).count() == 1


async def test_requires_api_key():
    """No X-API-Key → rejected (tenant_api_router dependency)."""
    from httpx import ASGITransport, AsyncClient
    from nicegui import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        r = await anon.post(BASE, json={"persona_key": "gastdocent", "email": "a@example.org"})
    assert r.status_code in (401, 403)


# ── expiry ──────────────────────────────────────────────────────────────────

async def test_post_sets_default_expiry(api_client):
    """No expiry_date in the body → tenant default duration applied."""
    r = await _post(api_client, persona_key="gastdocent", email="a@example.org")
    assert r.json()["data"]["expiry_date"] is not None


async def test_post_explicit_expiry_override(api_client):
    """Client-supplied expiry_date is honoured."""
    r = await _post(api_client, persona_key="gastdocent", email="a@example.org",
                    expiry_date="2030-01-15T00:00:00+00:00")
    assert "2030-01-15" in r.json()["data"]["expiry_date"]


async def test_resend_bumps_expiry(api_client):
    """A resent invite gets a fresh deadline, even if it was nearly/already expired."""
    from datetime import timedelta
    from ng_rdm.utils.helpers import now_utc
    created = (await _post(api_client, persona_key="gastdocent", email="a@example.org",
                           expiry_date=(now_utc() - timedelta(days=1)).isoformat())).json()["data"]
    r = await api_client.post(f"{BASE}/{created['id']}/resend")
    new_inv = await Invitation.get(id=created["id"])
    assert new_inv.expiry_date is not None and new_inv.expiry_date > now_utc()


async def test_maintenance_requires_key(api_client):
    r = await api_client.post("/maintenance", headers={"X-Cleanup-Key": "wrong"})
    assert r.status_code == 401


async def test_maintenance_expires_overdue(api_client):
    """POST /maintenance with the cleanup key flips overdue pending invites to expired."""
    from datetime import timedelta
    from ng_rdm.utils.helpers import now_utc
    from services.settings import config
    overdue = (await _post(api_client, persona_key="gastdocent", email="a@example.org",
                           expiry_date=(now_utc() - timedelta(days=1)).isoformat())).json()["data"]
    fresh = (await _post(api_client, persona_key="gastdocent", email="b@example.org")).json()["data"]

    r = await api_client.post("/maintenance", headers={"X-Cleanup-Key": config.get("cleanup_api_key")})
    assert r.status_code == 200
    assert r.json()["data"]["expired_count"] >= 1
    assert (await Invitation.get(id=overdue["id"])).status == "expired"
    assert (await Invitation.get(id=fresh["id"])).status == "pending"
