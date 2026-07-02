"""Didit ID-verification integration.

`client` talks to Didit's hosted-session API (create session, poll decision, extract
ID fields); `pending` is the in-flight session registry that binds a verification
transaction to one browser (mirrors the OIDC pending-login registry). See
`steps/cards/verify_id_didit.py` for the step card and `routes/didit_callback.py`
for the return-redirect route.
"""
from services.didit.client import create_session, extract_id_fields, get_decision
from services.didit.pending import (
    bind_pending_state,
    consume_pending_state,
    new_state,
    register_pending_session,
)

__all__ = [
    'create_session', 'get_decision', 'extract_id_fields',
    'new_state', 'register_pending_session', 'bind_pending_state', 'consume_pending_state',
]
