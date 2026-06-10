# Callback API (completion webhook)

When a guest finishes onboarding, eduPersona notifies the client application with a
single **outbound HTTP webhook** — the *callback*. This is the primary terugkoppeling
mechanism (SCIM is an optional alternative; see `services/scim.py`).

> The callback is **outbound** (eduPersona → your endpoint), so it is **not** part of
> the self-documenting Swagger at `/docs` — that only covers eduPersona's inbound REST
> API. This file is the contract.

The single source of truth for the body is
[`services/webhook/payload.py:build_payload`](../services/webhook/payload.py); the
delivery/retry behaviour lives in
[`services/webhook/delivery.py`](../services/webhook/delivery.py).

## When it fires

On completion of an invitation (the guest confirms the review step's **Register**
button → the invitation flips to `accepted`), eduPersona enqueues one callback **iff
the invitation has a `callback_url`**. No `callback_url` → no callback (the optional
SCIM push, if configured, still runs independently).

One completion produces exactly one `WebhookDelivery` record, retried as needed.

## Request

```
POST {callback_url}
Authorization: Bearer {callback_secret}
Content-Type: application/json
```

- **`callback_url`** is set per invitation (the `callback_url` field on
  `POST /api/v1/{tenant}/invitations`).
- **`callback_secret`** is configured **per tenant** (`tenants.<t>.callback_secret`)
  and sent as a bearer token so your endpoint can authenticate the caller. Verify it.
- Request timeout is 10s.

### Body

```json
{
  "tenant": "hvh",
  "persona": "gastdocent",
  "invitation_code": "a1b2c3d4",
  "guest_id": "EMP-00421",
  "completed_at": "2026-06-10T12:00:00+00:00",
  "email": "guest@example.org",
  "persona_params": { "faculteit": "FNWI" },
  "verifications": {
    "eduid": { "sub": "…", "given_name": "…", "family_name": "…", "email": "…" }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tenant` | string | Tenant key the invitation belongs to. |
| `persona` | string | The invitation's `persona_key`. |
| `invitation_code` | string | The invitation code. |
| `guest_id` | string | The client's own identifier for the guest (maps to SCIM `externalId`). |
| `completed_at` | string \| null | Acceptance timestamp, ISO 8601 (UTC). |
| `email` | string | The invitation email address. |
| `persona_params` | object | The `persona_params` supplied at invitation creation (verbatim, may be `{}`). |
| `verifications` | object | Verified step outputs — see below. |

The universal fields are **always present**. Identity facts (`given_name` /
`family_name`) are *not* top-level: they are display strings on the invitation and only
surface inside `verifications` if a step wrote them there.

### The `verifications` block

`verifications` carries one entry per key listed in the persona's **`callback_outputs`**,
read verbatim from the invitation's `step_outputs`:

- The persona config decides *which* outputs are exposed (`callback_outputs: ["eduid", …]`).
- OIDC steps key their output by **IdP name** (e.g. `eduid`, `institutional`); other
  steps key by their `step_id`.
- A `callback_outputs` key with no matching `step_outputs` entry is **logged and omitted**
  — a missing source never breaks delivery, so always treat each key as optional.

## Delivery contract

Your endpoint's HTTP status determines what happens next:

| Response | Outcome |
|----------|---------|
| **2xx** | `delivered` — done. |
| **4xx** | `failed`, **terminal** — not retried (treat as a permanent contract/auth error). |
| **5xx or network/transport error** | `failed`, **retried** with backoff until `MAX_ATTEMPTS`. |

- **MAX_ATTEMPTS = 5** total attempts.
- Backoff after each failed attempt (seconds): **30, 120, 900, 7200, 43200**
  (30s → 2m → 15m → 2h → 12h).
- A background loop (`webhook_retry_loop`, registered in `main.py:run()`) wakes every
  60s and re-fires any due, non-exhausted failures (`process_pending`).

**Idempotency:** because of retries (and because a returning guest can re-accept), your
endpoint may receive the same logical completion more than once. De-duplicate on
`invitation_code` (or `guest_id` + `persona`).

## Checking delivery status

Each attempt is persisted as a `WebhookDelivery` row. Fetch an invitation's deliveries
via the REST API:

```
GET /api/v1/{tenant}/invitations/{id}
```

The response includes a `webhook_deliveries` array:

| Field | Meaning |
|-------|---------|
| `id` | Delivery id. |
| `status` | `pending` → `in_flight` → `delivered` \| `failed`. |
| `attempt_n` | Number of attempts made so far. |
| `last_status_code` | HTTP status of the last attempt (null on network error). |
| `next_retry_at` | When the next retry is due (ISO 8601), or null if delivered, terminal (4xx), or exhausted. |

Note `failed` covers both terminal 4xx and a not-yet-exhausted 5xx — distinguish them by
`next_retry_at` (null = no further attempts).

## Configuration summary

| Where | Key | Purpose |
|-------|-----|---------|
| Per invitation (API) | `callback_url` | Target URL; absent ⇒ no callback. |
| Per tenant (settings.json) | `callback_secret` | Bearer token sent on every callback. |
| Per persona (settings.json) | `callback_outputs` | Which `step_outputs` keys appear in `verifications`. |

## Source

- Envelope: [`services/webhook/payload.py`](../services/webhook/payload.py)
- Delivery + retry state machine: [`services/webhook/delivery.py`](../services/webhook/delivery.py)
- Worked examples / assertions: [`tests/test_webhook.py`](../tests/test_webhook.py)
- Persona context: [`personas.md`](personas.md)
