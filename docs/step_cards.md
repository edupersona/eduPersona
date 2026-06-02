# Step cards & the onboarding orchestrator

The `/accept` flow is a sequence of step cards driven by `domain.step_cards.Steps`. Each step is described in `settings.tenants.<t>.scenarios.<key>.steps` and resolved to a Python class via the `STEP_CARD_CLASSES` registry.

This document codifies the contract. The implementation lives in [`domain/step_cards.py`](../domain/step_cards.py).

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
- Invoke domain services scoped to `(tenant, invite_code)` — `update_guest_from_userinfo`, `accept_invitation`, OIDC, mail.
- Trigger its own re-render via the orchestrator (`record` does this).

## What a step MAY NOT do

- Read or write other steps' completion state (`state['outcomes']` is orchestrator-owned).
- Hardcode IdP names, URLs, or copy. All of these come from config.
- Perform scenario-terminal actions (invitation acceptance, session establishment). Those belong to `FinalizeStep`.
- Assume its own position in the sequence. The step works whether it's at position 0 or 99.

## `is_already_done()`

Default returns False. Override in *verification* steps that have a durable DB marker (an `EmailVerified` row, a `GuestAttribute`, an `Invitation.status`, etc.). Called once per step at scenario startup; True → step is recorded as `SKIPPED`.

This is the only place a step legitimately persists across sessions. Use it sparingly — most steps should NOT auto-skip; the single-session invariant requires re-completing them on restart.

## The orchestrator (`Steps`)

Owns:
- Scenario instantiation from config (assigns `step_id` from `config.id` or position).
- The completion map `state['outcomes']` and output store `state['outputs']`.
- Prerequisite evaluation — positional ("all prior steps completed or skipped").
- The single state-mutation funnel `record(step_id, result)`.
- The terminal hook `_maybe_run_finalize()` — auto-invokes the `FinalizeStep`'s `act()` once all other steps are in a terminal-OK state.

Steps must call `await self.steps.record(self.step_id, result)` whenever they want to signal an outcome.

## The `FinalizeStep`

A declarative terminal step (`kind = 'finalize'`) that owns the scenario-wide side effects: `accept_invitation` + `establish_guest_session_for_code`. Auto-runs when its prerequisites are met. Idempotent — re-running is a no-op for already-accepted invitations.

Putting terminal logic here (instead of in the last interactive step) keeps the orchestrator scenario-agnostic. A scenario that needs different terminal behavior swaps the step class in config; no orchestrator changes.

## Scenarios

Today every tenant has a single scenario keyed `"default"`. The structure (`tenants.<t>.scenarios.<key>.steps` + `tenants.<t>.default_scenario`) is in place so future tenants can define multiple scenarios — selected per-invitation via `Invitation.scenario_key` (not yet implemented). The derivation function that picks a scenario from a user's roles will run at *invitation creation time*, freezing the choice into the invitation row; it will never re-derive at `/accept`.

## Adding a new step card

1. Subclass `StepCard`. Implement `render_enabled()` at minimum; override `render_completed()` if you need a richer success view.
2. If the step takes a user action: override `act()` to return a `StepResult`.
3. If the step has an out-of-band durable marker (verification-style): override `is_already_done()` with a cheap DB read.
4. If the step terminates the scenario: set `kind = 'finalize'` and implement `act()` to perform the side effects.
5. Register the class in `STEP_CARD_CLASSES`.
6. Add an entry to the relevant scenario in `settings.json` (and `settings.example.json`). All copy, IdP names, URLs go in `config` — never hardcoded in Python.

## State keys (per-session, `app.storage.tab`)

- `invite_code`, `invitation_id`, `role_assignments`, `role_name` — scenario context, written by `apply_invite_code_to_state`.
- `outcomes: dict[step_id, str]` — orchestrator-owned completion map.
- `outputs: dict[step_id, dict]` — orchestrator-stored step payloads.
- `oidc_state` — internal to `services.oidc_mt`.
