# Customising and extending: personas and step cards

This guide describes how to set up eduPersona for your own institution: how to configure
a **persona**, which **step cards** are available (with their intent, required config and
result), and how to customise existing cards or add new ones.

> Background and the full contract live in the code and the neighbouring docs:
> [`personas.md`](personas.md) (the persona concept), [`step_cards.md`](step_cards.md)
> (the step-card lifecycle and the `StepResult` contract) and
> [`callback_api.md`](callback_api.md) (the webhook to the client). This guide is the
> practical entry point; the code remains the source of truth.

---

## 1. Configuring a persona

A **persona** is the kind of guest you onboard (e.g. `gastdocent`, `alumnus`). The persona determines which step cards run, the mail template, an
optional post-success redirect, and which step results are returned to the IAM webhook/callback.

Personas live per tenant in `settings.json` under `tenants.<tenant>.personas.<key>`. Use
[`settings.example.json`](../settings.example.json) as a template.

### Persona keys

| Key | Required | Meaning |
|---|---|---|
| `display_name` | yes | Label in UI and mail. |
| `steps` | yes | The list of step cards to run (see §2). |
| `mail` | yes | `{layout, body}` — per-tenant mail templates for frame + per-persona body, both Jinja2 under [`services/postmark/templates/`](../services/postmark/templates/). |
| `expected_params` | yes (may be `{}`) | Schema for the `persona_params` the calling app (~IAM) supplies with an invitation (per param e.g. `type` and `required`). See [`personas.md`](personas.md) for the full field contract. |
| `callback_outputs` | yes (may be `[]`) | Which step results are returned to the calling app (~IAM) in the webhook. References the `id` of the steps (see §2). |
| `success_redirect_url` | no | Target of the call-to-action button ('cta') on the success screen. |
| `callback_url` | no | The client's webhook endpoint (`null` = no callback). |
| `completion_message`, `cta_label` | no | Text shown on the page *after* registration (`render_welcome`); fall back to translated defaults. |
| `completion` | no | Server-side side effect after completion (e.g. `{"action": "admin_onboarding", ...}`). |

### A step in `steps`

Each step is an object with three fields:

```json
{
  "class": "OIDCLoginStep",   // the step-card class (see §2)
  "id": "eduid_login",        // unique within the persona; also the output key
  "config": { ... }            // card-specific configuration (see §2 and §3)
}
```

- `class` — the name of the step-card class. Cards register themselves automatically by
  class name (see §5), so this is literally the Python class name.
- `id` — unique within the persona. The step result is stored under this `id` and — if the
  `id` is listed in `callback_outputs` — delivered to the webhook under this key.
- `config` — see §3 for the fields every card shares, and §2 for the card-specific ones.

Steps run **in order**: a step only becomes active once all preceding steps are completed
(`completed`) or skipped (`skipped`). The whole onboarding must finish within a single
browser session (see [`step_cards.md`](step_cards.md) — "single-session invariant").

### Language

Just write all user-facing config text in your deployment's primary language (the demo is
Dutch) — there are no per-language subkeys. The how and why (and running bilingually) is
in [`personas.md`](personas.md#language).

---

## 2. Step cards included in the current repo

The step cards live in [`steps/cards/`](../steps/). Below, per card: the intent, the
**required** and **optional** card-specific config (on top of the shared fields from §3),
and the **result** the card records (its `output`, stored under the step `id` and delivered
to the webhook when the `id` is listed in `callback_outputs`).

### `OIDCLoginStep`

- **Intent:** log in via OIDC (eduID or an institutional account). Optionally an ACR
  step-up: request *and* verify a specific authentication strength (e.g. MFA).
- **Required:** `idp` — a key under `tenants.<tenant>.oidc` describing the OIDC client.
- **Optional:**
  - `primary_button: {label, hint?}` — the login button.
  - `secondary_button: {label, url, hint?}` — an external link (opens in a new tab),
    e.g. "I don't have an eduID yet".
  - `acr_value` — the ACR to request/verify (e.g. `https://refeds.org/profile/mfa`).
  - `acr_failed_text` — error message on ACR mismatch (the step stays retryable).
- **Result:** the verified `userinfo` (dict). The id_token's `acr` claim is merged in, so
  the callback always carries it. On ACR mismatch the step fails (non-fatal) and the guest
  can retry.

### `VerifyConsentStep`

- **Intent:** a consent / code-of-conduct screen. The primary button opens a dialog with
  (1) a scrollable text rendered as Markdown and/or (2) an external link, plus (3) a
  checkbox that enables the confirm button.
- **Required:** `dialog_title`, `confirm_button_label`.
- **Optional:**
  - `primary_button: {label}` — the button that opens the dialog.
  - `consent_text` — a **path** to a Markdown file (e.g. `static/hvh/docs/gedragscode.md`),
    relative to the server's working directory. The file is read at startup; a missing file
    is a config error (fail-fast).
  - `consent_link: {label, url}` — external link (new tab).
  - `consent_label` — label next to the checkbox (default "I agree").
- **Result:** `{"consent_given": "<ISO-8601 UTC timestamp>"}` — the moment the guest clicked
  confirm.

### `VerifyMobileStep` (demo)

- **Intent:** verify a mobile number via a code exchange, entirely within one card. The
  code is **simulated** through a notification (no real SMS). You'd need to wire this to an SMS gateway service.
- **Required:** none card-specific; only the shared fields (§3).
- **Optional:** `mobile_label`, `code_label`, `send_button_label`, `verify_button_label`,
  `resend_label`, `phone_pattern` (regex for the number), `help_text`.
- **Result:** `{"mobile": "<entered number>"}`.

### `VerifyAlumniDb` (demo)

- **Intent:** a **demonstration** of custom verification against a (simulated) backend. The
  guest enters a date of birth + six-digit student number; on a "match" an alumnus id is
  returned. The rules are hardcoded (birth year between 1960 and 1990, six digits → a fixed
  `alumnus_id`); this is a template to replace with a real lookup (see §4).
- **Required:** none card-specific; only the shared fields (§3). (The help text and field
  labels live in code in this demo card, not in config.)
- **Result:** `{"alumnus_id": "A203920"}` on success. Otherwise the step fails (retryable)
  with a notification.

### `CollectIntakeStep` (demo)

- **Intent:** a short free-form intake: organisation name + an open question about the
  intended use case. Use to register eduPersona PoC participants. Both fields are optional; the step always completes.
- **Required:** none card-specific; only the shared fields (§3).
- **Optional:** `submit_label` (default "Verder").
- **Result:** `{"organisatie": str|null, "toepassingsscenario": str|null}`.

### `VerifyIdDiditStep`

- **Intent:** verify a government ID (passport / Dutch ID card) via Didit's hosted flow —
  document OCR + liveness + face-match. The user scans a QR with their phone to capture;
  the card polls Didit and advances the desktop when approved. No browser redirect.
- **Required:** none card-specific; only the shared fields (§3). The Didit credentials live
  in a **tenant-level** `tenants.<tenant>.didit` block (`api_key`, `workflow_id`,
  `base_url?`, `language?` — default `nl`), *not* in this step's `config`.
- **Optional:** `primary_button: {label, hint?}` (the Start button), `declined_text`,
  `timeout_text`, `review_text` (retry/terminal messages, all through `_()`).
- **Result:** the extracted ID fields (`first_name`, `last_name`, `document_number`,
  `date_of_birth`, `nationality`, `document_type`, `expiration_date`, …) plus
  `liveness_score` / `face_match_score`; base64 image blobs are stripped.
- **See:** [`didit.md`](didit.md) for the config, the polling-vs-redirect architecture, and
  the decision-shape caveat.

---

## 3. Shared config of every step card

On top of the card-specific fields from §2, every card reads these fields from `config`
(via the base class [`steps/base.py`](../steps/base.py)):

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | The card's heading. |
| `completed_text` | yes | Text shown once the step is completed. |
| `disabled_text` | no | Text shown while the step is not yet active (preceding steps not done). |
| `help_text` | no | Optional explanation above the input (rendered by `form_column()` / `render_help()`). |

A missing **required** field produces a clear `ValueError` at startup naming the key — the
server then refuses to start. That is intended behaviour.

---

## 4. Customising existing cards

- **Text and labels:** almost all user-facing text comes from `config` and runs through
  `_()`. So change your copy in `settings.json`, not in Python. For a second language: add
  translations in [`services/i18n.py`](../services/i18n.py), keyed by the source string.
- **Styling:** use the semantic CSS classes in
  [`static/css/base.css`](../static/css/base.css) (see [`cline_docs/styling.md`](../cline_docs/styling.md)).
  Avoid inline `.style()` for colours/backgrounds; add a semantic class instead. The consent
  dialog, for instance, uses `.consent-dialog` / `.consent-text`.
- **Behaviour (e.g. real verification):** `VerifyAlumniDb` is set up as a template. Replace
  the hardcoded rules in `_verify()` with a real (async) lookup against your own backend and
  pass the resolved id to `self.complete({...})`. Stick to the contract in
  [`step_cards.md`](step_cards.md): read only your own `self.state` and the read-only
  `self.steps.context`, and always signal via `complete()`/`fail()`.

---

## 5. Creating a new step card

A step card is a free-form NiceGUI canvas that signals its outcome via a single typed
`StepResult`. A multi-part transaction (enter a value → trigger an action → confirm) fits
inside one card, driven by reactive bindings (`bind_value`, `bind_visibility`) on
`self.state` — no sub-step machinery. `VerifyMobileStep` and `VerifyConsentStep` are worked
examples.

Steps:

1. **Add a module** under [`steps/cards/`](../steps/cards/) with a subclass of `StepCard`,
   and list it in [`steps/cards/__init__.py`](../steps/cards/__init__.py). The card registers
   itself automatically by class name — that name is what you use as `"class"` in the config.
2. **Read your config** in `__init__` (call `super().__init__(config)` first) and seed any
   default values on `self.state`. Use `config['x']` for required keys (a missing key is
   turned into a clean `ValueError` at startup by the orchestrator) and `config.get('x')`
   for optional ones.
3. **Paint the UI** in `render_enabled()` — a free-form canvas. Use
   `with self.form_column():` for the standard single-column form chrome (which also renders
   `help_text`). Override `render_completed()` for a richer success view if you like.
4. **Finish** with `await self.complete(output)` or `await self.fail(error, notify=...)`.
   For a single-button card you can instead override `act()` and return a `StepResult`. The
   `output` dict lands under the step `id` and is delivered to the webhook if that `id` is in
   `callback_outputs`.
5. **Optional — durable skip:** if the step has a persistent DB marker (verification-style),
   override `is_already_done()` with a cheap DB read; `True` at startup → the step is
   `skipped`. Use this sparingly — the single-session invariant requires most steps to be
   re-completed on restart.
6. **Wire it into the config:** add a step object with your `class`, an `id` and the `config`
   to a persona in `settings.json`. All copy, IdP
   names and URLs belong in `config` — never hardcoded in Python.

The full contract (lifecycle, what a card may and may not do, the `StepResult` type) is in
[`step_cards.md`](step_cards.md).
