"""Outbound webhook delivery state machine.

Contract: plain webhook, bearer-token authenticated via the per-tenant
`callback_secret`. **4xx is terminal, 5xx and network errors retry** with
exponential backoff, up to MAX_ATTEMPTS total attempts.

`_http_post` is the patchable seam for tests. `enqueue_callback` is the entry
point (no-op when the invitation has no callback_url), called from the accept flow
on completion.
"""

import asyncio
from datetime import timedelta

import httpx

from ng_rdm.utils import logger
from ng_rdm.utils.helpers import now_utc
from domain.models import Invitation, WebhookDelivery
from services.settings import get_tenant_config
from services.webhook.payload import build_payload

# Exponential backoff between retries, in seconds. Index i is the wait
# after the (i+1)-th failed attempt. MAX_ATTEMPTS caps total tries; the final
# value is headroom for the last scheduled wait.
BACKOFF = [30, 120, 900, 7200, 43200]
MAX_ATTEMPTS = 5


async def _http_post(url: str, payload: dict, headers: dict[str, str]) -> int:
    """POST the payload and return the HTTP status code. Patchable test seam.

    Raises on network/transport errors (caught by _deliver as retriable).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        return resp.status_code


async def _deliver(delivery_id: int) -> WebhookDelivery | None:
    """Run one delivery attempt and persist the resulting state."""
    delivery = await WebhookDelivery.get_or_none(id=delivery_id).prefetch_related("invitation")
    if delivery is None:
        logger.error(f"_deliver: WebhookDelivery {delivery_id} not found")
        return None
    invitation: Invitation = delivery.invitation  # type: ignore[assignment]
    url = invitation.callback_url
    if not url:
        return delivery

    tenant = invitation.tenant  # type: ignore[attr-defined]
    secret = get_tenant_config(tenant).get("callback_secret") or ""
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}

    delivery.attempt_n += 1
    delivery.status = "in_flight"
    code: int | None = None
    try:
        code = await _http_post(url, delivery.payload, headers)
        delivery.last_error = None  # type: ignore[reportAttributeAccessIssue]  # TextField(null=True)
    except Exception as e:  # network/transport error — retriable
        delivery.last_error = str(e)

    delivery.last_status_code = code

    if code is not None and 200 <= code < 300:
        delivery.status = "delivered"
        delivery.next_retry_at = None
    elif code is not None and 400 <= code < 500:
        delivery.status = "failed"        # 4xx is terminal — do not schedule
        delivery.next_retry_at = None
    else:                                  # 5xx or network error — retry if attempts remain
        delivery.status = "failed"
        if delivery.attempt_n >= MAX_ATTEMPTS:
            delivery.next_retry_at = None  # exhausted
        else:
            wait = BACKOFF[min(delivery.attempt_n - 1, len(BACKOFF) - 1)]
            delivery.next_retry_at = now_utc() + timedelta(seconds=wait)

    await delivery.save()
    return delivery


async def enqueue_callback(tenant: str, invitation_id: int) -> WebhookDelivery | None:
    """Create a delivery for the invitation and attempt it immediately.

    No-op (returns None) when the invitation has no callback_url. Called from the
    accept flow on completion.
    """
    invitation = await Invitation.get_or_none(id=invitation_id)
    if invitation is None:
        logger.error(f"enqueue_callback: invitation {invitation_id} not found")
        return None
    if not invitation.callback_url:
        return None

    delivery = await WebhookDelivery.create(
        invitation=invitation,
        payload=build_payload(invitation, tenant),
        status="pending",
    )
    return await _deliver(delivery.id)


async def process_pending(limit: int = 20) -> int:
    """Re-fire failures whose backoff has elapsed and that have attempts left.

    Returns the number of deliveries re-attempted. Future-scheduled and exhausted
    (next_retry_at NULL) deliveries are skipped.
    """
    due = await WebhookDelivery.filter(
        status="failed",
        next_retry_at__lte=now_utc(),
        attempt_n__lt=MAX_ATTEMPTS,
    ).limit(limit).all()
    for delivery in due:
        await _deliver(delivery.id)
    return len(due)


async def webhook_retry_loop(interval: int = 60) -> None:
    """App-level background loop re-firing due webhook failures.

    Registered from main.py's production entrypoint via app.on_startup. Uses
    asyncio.sleep (not ui.timer) — it is app-level, not page-bound.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await process_pending()
        except Exception as e:
            logger.error(f"webhook_retry_loop: {e}")
