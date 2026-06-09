"""
State management utilities for edupersona application.
Provides state initialization for pages using NiceGUI tab storage.
"""
from nicegui import app
from ng_rdm.utils import logger


_DEFAULTS = {
    'invite_code': '',
    'invitation_id': None,
    'role_assignments': [],
    'role_name': '',
    # Per-step bookkeeping owned by steps.Steps; see docs/step_cards.md
    'outcomes': {},
    'outputs': {},
    'oidc_state': {},
}


def initialize_state():
    """Ensure tab state has all expected keys; preserve any existing values.

    Earlier versions only initialized when tab storage was empty, which left
    stale tabs (e.g. carrying just `oidc_state` from an OIDC kickoff) missing
    other defaults — readers like `Steps.render()` would then KeyError.
    """
    for key, default in _DEFAULTS.items():
        app.storage.tab.setdefault(key, default)
    return app.storage.tab
