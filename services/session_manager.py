"""
State management for the accept (guest onboarding) flow.

Session state lives in `app.storage.user` — cookie-keyed, so it survives the cross-site
OIDC redirect (unlike `app.storage.tab`, whose sessionStorage-derived tab id is not
reliably restored on the return leg). It is namespaced by invite code so concurrent
invitations stay isolated.
"""
from nicegui import app


_DEFAULTS = {
    'invite_code': '',
    'invitation_id': None,
    # Per-step bookkeeping owned by steps.Steps; see docs/step_cards.md
    'outcomes': {},                # dict[step_id, outcome]
    'step_state': {},              # dict[step_id, dict] — per-card state, incl. each step's 'outputs'
}


def session_state(code: str) -> dict:
    """Return the accept-flow session state for invite `code`, seeding defaults.

    Held in `app.storage.user` and namespaced by invite code. Mutations persist via
    NiceGUI's observable storage and survive the OIDC redirect, so a step completed
    during the callback is still recorded when the IdP redirects back and the page
    reloads. `setdefault` returns the *same* dict across reloads — the callback closure
    and the reloaded page see one object.
    """
    sessions = app.storage.user.setdefault('accept_sessions', {})
    state = sessions.setdefault(code, {})
    for key, default in _DEFAULTS.items():
        state.setdefault(key, default)
    return state


def clear_session_state(code: str) -> None:
    """Drop the scratch state for `code` once its invitation is terminal (accepted /
    expired) — the accept page then renders from the DB invitation, not session state,
    so the slot is dead weight. Keeps `app.storage.user['accept_sessions']` bounded."""
    app.storage.user.get('accept_sessions', {}).pop(code, None)
