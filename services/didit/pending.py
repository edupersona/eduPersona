"""In-flight Didit verification-session registry.

Mirrors the OIDC pending-login registry (services/oidc_mt/oidc_protocol.py): a
process-global dict keyed by a random `state` token. Each entry holds the *entire*
transaction — tenant, Didit session_id, the bound card callback handler, next_url —
so the single `/didit_callback` route resolves everything from here and never trusts
request query params. Isolation is carried by the token, not the route path.

The token is also bound to one browser via app.storage.user (CSRF): `consume` requires
membership in both places, so a token can't be forged or replayed across sessions.
Process-global ⇒ single worker only (already required for NiceGUI's socket.io).
"""
import secrets
import time

_pending: dict[str, dict] = {}
_PENDING_TTL = 1800   # 30 min — the user needs time to capture their ID + selfie
_PENDING_MAX = 1000   # global hard cap; evict oldest beyond this
_BIND_MAX = 20        # cap on a single browser's CSRF-binding token list


def _prune() -> None:
    """Drop TTL-expired entries and hard-cap the registry (evict oldest)."""
    now = time.monotonic()
    for state in [s for s, v in _pending.items() if now - v['created_at'] > _PENDING_TTL]:
        _pending.pop(state, None)
    overflow = len(_pending) - _PENDING_MAX
    if overflow > 0:
        for state, _v in sorted(_pending.items(), key=lambda kv: kv[1]['created_at'])[:overflow]:
            _pending.pop(state, None)


def new_state() -> str:
    """Mint a fresh, unguessable state token."""
    return secrets.token_urlsafe(32)


def register_pending_session(state: str, context: dict) -> None:
    """Stash a verification transaction under `state`. `context` is stored as-is
    (tenant, session_id, callback_handler, next_url) and never inspected here."""
    _prune()
    _pending[state] = {**context, 'created_at': time.monotonic()}


def bind_pending_state(states: list[str], state: str) -> None:
    """Bind `state` to a browser's CSRF list in place: drop tokens no longer live in the
    registry, append the new one, cap the length. Hand it app.storage.user's own list."""
    states[:] = ([s for s in states if s in _pending] + [state])[-_BIND_MAX:]


def consume_pending_state(states: list[str], state: str) -> dict | None:
    """One-time consume: `state` must be bound to this browser (in `states`) AND still
    live in the registry. Removes it from both. Returns the transaction, or None ⇒
    caller must reject (forged/expired/replayed)."""
    if not state or state not in states:
        return None
    states.remove(state)
    return _pending.pop(state, None)
