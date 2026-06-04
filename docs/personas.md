# Personas

The **persona** is the organising concept of edupersona: the *kind* of guest being
onboarded (e.g. `gastdocent`, `alumnus`). This doc is a map into the code — the
contract lives in the code, not here.

## What a persona owns

A persona holds only what makes it differ from another persona. The typed contract
is [`domain/persona.py`](../domain/persona.py) → `PersonaConfig`:

- `display_name: {lang: label}` — UI/mail label.
- `steps: [...]` — the onboarding step cards to run (same shape the step framework
  consumes; see [`domain/step_cards.py`](../domain/step_cards.py) and
  [`docs/step_cards.md`](step_cards.md)).
- `mail: {layout, body}` — per-tenant layout frame + per-persona body, both Jinja2
  under [`services/postmark/templates/`](../services/postmark/templates/).
- `expected_params: {name: ExpectedParam}` — schema for client-supplied
  `persona_params` (`type` ∈ string/int/bool/enum, `required`, `enum`).
- `callback_outputs: [...]` — which `step_outputs` keys surface in the webhook.
- `success_redirect_url`, `callback_url` — optional.

Personas live per-tenant under `settings.json` → `tenants.<t>.personas.<key>`
(see `settings.example.json` for `gastdocent` + `alumnus`). They are loaded and
validated by [`services/persona_loader.py`](../services/persona_loader.py):
`get_persona_config(tenant, key)` and `validate_persona_params(cfg, raw)`
(raise `UnknownPersonaError` / `PersonaParamsError`, both `ValueError`).

**Not** in a persona: authorization, role membership, validity windows,
deprovisioning — those live in the client app's IAM/IGA.

## Lifecycle

1. **Create** — client app calls `POST /api/v1/{tenant}/invitations`
   ([`routes/api/invitations.py`](../routes/api/invitations.py)) or an admin uses the
   [simulator](../routes/m/simulator.py). `domain.invitations.create_invitation`
   writes an `Invitation` row directly (no Guest entity) and mail is sent
   best-effort ([`services/postmark/postmark.py`](../services/postmark/postmark.py)).
2. **Accept** — guest opens `/accept/{code}` ([`routes/accept.py`](../routes/accept.py)).
   `Steps` runs the persona's step cards. OIDC steps write verified userinfo to
   `state['outputs'][idp]`; non-OIDC steps to `state['outputs'][step_id]`.
3. **Finalize** — `FinalizeStep` persists `state['outputs']` to
   `Invitation.step_outputs`, then `accept_invitation` flips status and enqueues the
   webhook.
4. **Callback** — [`services/webhook/payload.py:build_payload`](../services/webhook/payload.py)
   builds the envelope (universal fields + one `verifications` entry per
   `callback_outputs` key, read verbatim from `step_outputs`).
   [`delivery.py`](../services/webhook/delivery.py) delivers with bearer auth and
   retries: **4xx terminal, 5xx + network errors retry** on backoff
   `[30, 120, 900, 7200, 43200]`s, max 5 attempts. The app-level
   `webhook_retry_loop` re-fires due failures (registered in `main.py:run()`).

## Data model

`Invitation` ([`domain/models.py`](../domain/models.py)) is the only first-class
entity (§"invitation is the only entity"). `persona_params` and `step_outputs` are
JSON pass-throughs, never queried at SQL level. Cross-invitation grouping is a
`WHERE invitation_email = ?` / `WHERE client_ref = ?` query, not a Guest join.

## Adding a persona

1. Add a block under `tenants.<t>.personas.<key>` in `settings.json` (and the
   `settings.example.json` template).
2. Add a body template `services/postmark/templates/personas/<key>.jinja2`.
3. If the persona introduces a new step type, register it in
   `STEP_CARD_CLASSES` in `domain/step_cards.py`.
