"""Thin async client for Didit hosted verification sessions.

Config comes from `get_tenant_config(tenant)['didit']`: `api_key`, `workflow_id`,
and optional `base_url` (defaults to Didit's production v3 host). `_http_request` is
the patchable seam for tests, mirroring `services/webhook/delivery.py:_http_post`.

We only ever create a session and poll its decision — both are outbound calls, so the
whole flow works from localhost with no public inbound URL (see docs plan).
"""
from typing import Any

import httpx

from services.settings import get_tenant_config

DEFAULT_BASE_URL = "https://verification.didit.me/v3"

# ID-document fields worth surfacing to the webhook. Whitelisted so we never forward
# the base64 image blobs (portrait/front/back) — they bloat the payload and are PII we
# don't need. Every field is optional; documents vary by type and country.
_ID_FIELDS = (
    'first_name', 'last_name', 'full_name', 'document_number', 'personal_number',
    'date_of_birth', 'age', 'gender', 'marital_status', 'nationality',
    'document_type', 'document_subtype', 'issuing_state', 'issuing_state_name',
    'date_of_issue', 'expiration_date', 'place_of_birth', 'address',
    'formatted_address', 'parsed_address', 'mrz',
)


def _didit_config(tenant: str) -> dict:
    cfg: dict = get_tenant_config(tenant).get("didit", {}) or {}
    if not cfg.get("api_key") or not cfg.get("workflow_id"):
        raise ValueError(f"Didit is not configured for tenant '{tenant}'")
    return cfg


async def _http_request(method: str, url: str, api_key: str, *, json: dict | None = None) -> tuple[int, dict]:
    """Perform one Didit API call; return (status_code, parsed_json). Patchable test seam."""
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, url, json=json, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {}
        return resp.status_code, body


async def create_session(tenant: str, vendor_data: str) -> dict:
    """Create a verification session against the tenant's configured workflow.

    `vendor_data` is our own correlation string. No `callback` is set: the desktop card
    polls the decision in place (in-app QR + polling), so there is no browser redirect.
    Returns the session object (`session_id`, `url`, ...).
    """
    cfg = _didit_config(tenant)
    base = cfg.get("base_url") or DEFAULT_BASE_URL
    payload = {"workflow_id": cfg["workflow_id"], "vendor_data": vendor_data,
               "language": cfg.get("language") or "nl"}  # Didit-hosted UI language
    status, body = await _http_request("POST", f"{base}/session/", cfg["api_key"], json=payload)
    if status not in (200, 201):
        raise ValueError(f"Didit session create failed ({status}): {body}")
    return body


async def get_decision(tenant: str, session_id: str) -> dict:
    """Poll the decision for a session. Returns the full decision object."""
    cfg = _didit_config(tenant)
    base = cfg.get("base_url") or DEFAULT_BASE_URL
    status, body = await _http_request("GET", f"{base}/session/{session_id}/decision/", cfg["api_key"])
    if status != 200:
        raise ValueError(f"Didit decision fetch failed ({status}): {body}")
    return body


def _find_feature(decision: dict, *names: str) -> dict:
    """Locate a feature block by any of `names`, tolerating the two decision shapes
    (top-level vs nested under `features`) and singular/plural/list forms."""
    containers = [decision]
    features = decision.get('features') if isinstance(decision, dict) else None
    if isinstance(features, dict):
        containers.append(features)
    for container in containers:
        if not isinstance(container, dict):
            continue
        for name in names:
            value: Any = container.get(name)
            if isinstance(value, list) and value:
                value = value[0]
            if isinstance(value, dict):
                return value
    return {}


def extract_id_fields(decision: dict) -> dict:
    """Pull the useful ID-document fields (plus liveness/face-match scores) from a
    decision. Defensive: unknown shapes yield an empty-ish dict rather than raising."""
    id_block = _find_feature(decision, 'id_verification', 'id_verifications')
    liveness = _find_feature(decision, 'liveness', 'liveness_checks')
    face_match = _find_feature(decision, 'face_match', 'face_matches')

    out: dict[str, Any] = {k: id_block[k] for k in _ID_FIELDS if id_block.get(k) not in (None, '')}
    if liveness.get('score') is not None:
        out['liveness_score'] = liveness['score']
    if face_match.get('score') is not None:
        out['face_match_score'] = face_match['score']
    return out
