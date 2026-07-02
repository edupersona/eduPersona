# Didit ID verification

Government-ID verification (passport / Dutch ID card) via [Didit](https://didit.me),
with document OCR + liveness + face-match. Exposed as the step card
[`VerifyIdDiditStep`](../steps/cards/verify_id_didit.py) and demoed by the single-step
persona **`id_verificatie`**. The extracted identity fields (name, document number, DOB,
nationality, …) become the step's output and flow to the completion webhook.

## Configuration (`tenants.<tenant>.didit` in `settings.json`)

| Key | Required | Meaning |
|---|---|---|
| `api_key` | yes | Didit API key (secret — `settings.json` is gitignored). |
| `workflow_id` | yes | UUID of a **pre-created** Didit workflow. |
| `base_url` | no | Didit API host; defaults to `https://verification.didit.me/v3`. |
| `language` | no | Didit-hosted UI language; **defaults to `nl`**. |

The referenced workflow is configured **in Didit** (console or the
`.agents/skills/didit-verification-management` scripts), not here. It must have liveness +
face-match enabled and documents restricted to passport + NL ID card to match this
integration's intent.

Runtime dependency: **`segno`** (pure-Python QR generator) — in `requirements.txt`.

The Didit config is a **tenant-level** block, read by `services/didit/client.py`; it is
*not* part of a step card's per-step `config` (which only carries copy/labels — see
[`customisation.md` §2](customisation.md)). One `didit` block serves every Didit step in
the tenant.

## Flow: in-app QR + backend polling (no browser redirect)

```
desktop /accept                     phone                    Didit
   │  click Start                                             
   ├───────────── create_session (workflow_id, language) ───▶ │
   │  ◀───────────── {session_id, url} ───────────────────────┤
   │  render url as QR (segno) ─── scan ──▶ open url ────────▶ │  capture doc + selfie
   │  ui.timer(4s): get_decision(session_id) ───────────────▶ │
   │  ◀── status: In Progress … → Approved (+ id fields) ─────┤
   │  complete(extract_id_fields) → review gate → Register     
```

The card holds phases in `self.state['phase']` (`start` → `awaiting` → `declined`/done),
toggled with `bind_visibility_from` (like `VerifyMobileStep`) — no manual orchestrator
refresh. A `ui.timer(POLL_INTERVAL=4s)` polls `get_decision` while `awaiting`; it gives up
after `POLL_TIMEOUT=600s`. `Approved` → `complete(fields)`; `Declined`/`Expired`/`Abandoned`
→ retry; `In Review` → "needs manual review". The timer lives in `render_enabled`, so it is
cancelled automatically when the awaiting panel is torn down on completion.

### Why polling, not a redirect or webhook — the key design choice

Didit's hosted capture happens on the user's **phone** (QR hand-off), but onboarding must
continue on the **desktop** web app. Three ways for the desktop to learn the phone finished:

- **Redirect** (Didit returns a browser to a callback): the *phone* is the completer and
  can't reach a dev `localhost`; only the desktop holds the session, and relying on Didit
  auto-redirecting the desktop is fragile.
- **Webhook** (Didit → our server): needs a **public inbound URL** (a tunnel in dev) plus
  signature verification and socket correlation. Breaks "test without deploying".
- **Polling** (desktop asks Didit): the phone talks only to Didit's public URL; the desktop
  polls Didit's API **outbound**. Works on `localhost` with no deploy, and dev == prod.

We chose polling. Consequently there is **no callback route, no CSRF/pending-token
registry, and no `callback` param on `create_session`** — an earlier draft copied that
OIDC-style redirect machinery and it was deliberately removed. Tenant isolation is trivial:
the card polls in its own live NiceGUI session with its own `self.tenant`; nothing is
shared across a route.

## Files

- `services/didit/client.py` — `create_session(tenant, vendor_data)`,
  `get_decision(tenant, session_id)`, `extract_id_fields(decision)`. `_http_request` is the
  patchable test seam (mirrors `services/webhook/delivery.py`).
- `services/didit/qr.py` — `qr_data_uri(url)` → SVG data-URI for `ui.html`/`ui.image`.
- `services/didit/__init__.py` — public exports.
- `steps/cards/verify_id_didit.py` — the `VerifyIdDiditStep` card (state machine + polling).

## Decision parsing — `extract_id_fields`

Returns a **whitelisted** set of ID fields (`first_name`, `last_name`, `full_name`,
`document_number`, `date_of_birth`, `nationality`, `document_type`, `expiration_date`,
`issuing_state`, `date_of_issue`, …) plus `liveness_score` / `face_match_score`. It
deliberately **omits the image/video blobs and signed URLs** (`portrait_image`,
`front_image`, `back_image`, liveness `reference_image`/`video_url`, face-match
`source_image`/`target_image`) — they bloat the webhook payload and are PII we don't need,
and the URLs are short-lived. `None`/empty fields are dropped too.

**Real decision shape (verified 2026-07).** The polled `GET /session/{id}/decision/`
returns the features as **top-level plural lists** — `id_verifications: [...]`,
`liveness_checks: [...]`, `face_matches: [...]` — and `features` is a list of *strings*
(`["ID_VERIFICATION", "LIVENESS", "FACE_MATCH"]`), not a container. `_find_feature` handles
this (takes the first list element, ignores the non-dict `features`) and still tolerates
the singular/nested variants defensively. `tests/test_verify_id_didit.py::test_extract_real_didit_shape`
pins this against a real payload. Note the ID fields sit under `id_verifications[].{first_name,
last_name, document_number, ...}` (not `id_token`/OIDC-style claims).

`_poll` logs every decision (`INFO` status+keys, `DEBUG` full payload) and a `WARNING` when
a session is `Approved` but nothing extracts — keep those if Didit changes the shape.

## Output & webhook

`complete(fields)` records the output under the step's `id`. The demo persona lists
`callback_outputs: ["id_document"]`, so the fields appear in the completion webhook's
`verifications.id_document` (see [`callback_api.md`](callback_api.md)). The completed card
shows the fields in a "View attributes" pulldown (`expandable_info`), like the other cards.

## Testing without a real ID

Didit documents a **sandbox** mode (`sandbox_scenario: "approve" | "decline_aml_hit" | …`
in the session-create body, **sandbox API keys only**) that runs the full pipeline with
magic inputs. As of writing, sandbox API keys cannot yet be created, so this is **not
wired in**. When keys become available it's a one-liner: pass `didit.sandbox_scenario` from
config into the `create_session` payload. Didit's `PATCH /session/{id}/update-status/` can
force a status but returns no document data, so it does not populate the pulldown.

## Future changes — pointers

- **Field mapping:** adjust `extract_id_fields` once a real decision payload is captured.
- **Sandbox:** add `sandbox_scenario` to `create_session` when sandbox keys exist.
- **Pre-fill / mismatch checks:** Didit's session `expected_details` (e.g. the invitation's
  given/family name) can flag mismatches — not currently sent.
- **Poll cadence/timeout:** `POLL_INTERVAL` / `POLL_TIMEOUT` class constants on the card
  (decision endpoint limit is 100/min).
