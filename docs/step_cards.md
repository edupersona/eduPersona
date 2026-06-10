# Step cards & the onboarding orchestrator

The `/accept` flow is a sequence of step cards driven by `steps.Steps`. Each step is described in `settings.tenants.<t>.scenarios.<key>.steps` and resolved to a Python class via the `STEP_CARD_CLASSES` registry, which every `StepCard` subclass joins automatically (keyed by class name = the `"class"` field in settings.json).

This document codifies the contract. The code lives in the top-level [`steps/`](../steps/) package — `base.py` (the `StepCard` contract + `StepResult` + registry), `orchestrator.py` (`Steps`, `render_welcome`), and one module per card under [`steps/cards/`](../steps/cards/). The package is the extension surface: adopters compose steps in settings.json and add new cards under `cards/`.

## Single-session invariant

End-to-end onboarding MUST complete within one browser session. Tab close, server restart, or new device → restart at step 1. Rationale: the authentication assurance produced by step N is invalidated if an interruption lets a different actor finish step N+1. Don't add flow-resumption mechanisms (session cookies, magic-link bridges of the *flow*).

Verification side channels (e.g., email verify) that write a durable DB marker are the only exception — they persist *facts about the user*, never flow progress. See `is_already_done` below.

## Lifecycle (per step)

```
PENDING → IN_PROGRESS → { COMPLETED, FAILED, SKIPPED }
```

- `PENDING` — prerequisites met, user has not yet acted.
- `IN_PROGRESS` — user clicked; awaiting result (sync return or async callback like OIDC).
- `COMPLETED` — step's work done; orchestrator may enable the next step.
- `FAILED` — recoverable by default (UI offers retry). A step can set `fatal=True` on its result to request scenario abort.
- `SKIPPED` — entered at scenario startup when `is_already_done()` returns True. Treated as COMPLETED for prerequisite purposes.

There is no persistent `WAITING` state. A step that dispatches an out-of-band action renders a "we sent you an email; refresh after clicking" hint and stays `IN_PROGRESS` in the session; on the next page load, `is_already_done()` checks the durable marker and transitions to `SKIPPED`/`COMPLETED`.

## The `StepResult` contract

Steps signal outcome by returning a typed `StepResult` — never by mutating `state` directly.

```python
@dataclass
class StepResult:
    outcome: 'completed' | 'failed' | 'in_progress'
    output: dict | None = None       # payload persisted under state['outputs'][step_id]
    error: str | None = None
    fatal: bool = False              # only with outcome='failed'
```

Returning `None` from `act()` means "no immediate transition" — useful for OIDC steps that complete asynchronously via `result_handler`. The result handler calls `self.steps.record(self.step_id, StepResult(...))` directly.

## What a step MAY do

- Read scenario context: `self.state['invite_code']`, `self.state['role_assignments']`, etc., and `self.tenant`.
- Read its own and prior steps' outputs: `self.state['outputs'][some_step_id]`.
- Invoke domain services scoped to `(tenant, invite_code)` — OIDC, mail, etc.
- Finish itself via `await self.complete(output)` / `await self.fail(...)` (which also trigger the orchestrator re-render).

## What a step MAY NOT do

- Read or write other steps' completion state (`state['outcomes']` is orchestrator-owned).
- Hardcode IdP names, URLs, or copy. All of these come from config.
- Perform scenario-terminal actions (invitation acceptance, session establishment). Those belong to the orchestrator's built-in finalize (`Steps._finalize`).
- Assume its own position in the sequence. The step works whether it's at position 0 or 99.

## `is_already_done()`

Default returns False. Override in *verification* steps that have a durable DB marker (an `Invitation.status`, a value already in `Invitation.step_outputs`, etc.). Called once per step at scenario startup; True → step is recorded as `SKIPPED`.

This is the only place a step legitimately persists across sessions. Use it sparingly — most steps should NOT auto-skip; the single-session invariant requires re-completing them on restart.

## The orchestrator (`Steps`)

Owns:
- Scenario instantiation from config (assigns `step_id` from `config.id` or position).
- The completion map `state['outcomes']` and output store `state['outputs']`.
- Prerequisite evaluation — positional ("all prior steps completed or skipped").
- The single state-mutation funnel `record(step_id, result)`.
- The review gate + terminal hook `register()` — once *every* step is in a terminal-OK state (`all_steps_done`) the render shows a **Register** button; clicking it runs the built-in `_finalize()` side effect.

Steps signal outcomes via `await self.complete(output)` / `await self.fail(error, notify=...)` — or, for a single-button step, by returning a `StepResult` from `act()`. Both funnel through the orchestrator's `record(step_id, result)` internally; cards never call `record` or touch `state['outcomes']` directly.

## Finalization & the welcome screen

Finalization is **not** a step — it's a built-in orchestrator side effect (`Steps._finalize`): it persists `state['outputs']` to `Invitation.step_outputs` and calls `accept_invitation` (which fires the webhook callback). It does **not** run automatically when the last step finishes. Instead, once every step is `completed`/`skipped` (`Steps.all_steps_done`), the orchestrator renders a **review gate** — the completed cards plus a primary **Register** button — so the guest can review the collected data before anything is sent. Clicking Register calls `Steps.register()`, which runs `_finalize()`. Idempotent — guarded by `state['completed']`/`state['finalize_failed']` within a session and by the invitation's own status across sessions.

On success the orchestrator's `render()` stops showing step cards and renders `render_welcome(tenant, persona_key, given_name)` — a per-persona, localized success screen (`PersonaConfig.completion_message` + `cta_label`, CTA linking to `success_redirect_url`). The same `render_welcome` is reused by `routes/accept.py` for a returning user who reopens an already-accepted invitation, so both paths render identically.

## Scenarios

Today every tenant has a single scenario keyed `"default"`. The structure (`tenants.<t>.scenarios.<key>.steps` + `tenants.<t>.default_scenario`) is in place so future tenants can define multiple scenarios — selected per-invitation via `Invitation.scenario_key` (not yet implemented). The derivation function that picks a scenario from a user's roles will run at *invitation creation time*, freezing the choice into the invitation row; it will never re-derive at `/accept`.

## Adding a new step card

1. Add a module under `steps/cards/` defining a `StepCard` subclass, and list it in `steps/cards/__init__.py`. It auto-registers by class name — no registry edit.
2. Implement `render_enabled()` (your free-form canvas; use `with self.form_column():` for the standard single-column form chrome, which also renders `help_text`). Override `render_completed()` for a richer success view.
3. Finish the step with `await self.complete(output)` / `await self.fail(error, notify=...)`. For a single-button step you may instead override `act()` to return a `StepResult`.
4. If the step has an out-of-band durable marker (verification-style): override `is_already_done()` with a cheap DB read.
5. Add an entry to the relevant scenario in `settings.json` (and `settings.example.json`). All copy, IdP names, URLs go in `config` — never hardcoded in Python.

A step card is a free-form NiceGUI canvas: a multi-part *transaction* (enter a value → trigger an action → confirm → done) can live entirely inside `render_enabled`, driven by reactive bindings — `bind_value` for inputs, `bind_visibility` off a `self.state` flag to reveal/hide parts as it progresses — and completes with a single `self.complete()`. No sub-step machinery; the whole exchange is one orchestrator step. `VerifyMobileStep` is the worked example (number → simulated code via `ui.notify` → verify), keeping transient values (`state['code_sent']`, the generated code) out of `outputs`.

## State keys (per-session, `app.storage.tab`)

- `invite_code`, `invitation_id`, `role_assignments`, `role_name` — scenario context, written by `apply_invite_code_to_state`.
- `outcomes: dict[step_id, str]` — orchestrator-owned completion map.
- `outputs: dict[step_id, dict]` — orchestrator-stored step payloads.
- `oidc_state` — internal to `services.oidc_mt`.
