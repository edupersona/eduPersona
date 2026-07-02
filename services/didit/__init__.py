"""Didit ID-verification integration.

`client` talks to Didit's hosted-session API (create session, poll decision, extract
ID fields); `qr` renders the session URL as a QR the user scans with their phone. The
step card (`steps/cards/verify_id_didit.py`) shows the QR and polls the decision in its
own live session — there is no browser redirect back, so no callback route is needed.
"""
from services.didit.client import create_session, extract_id_fields, get_decision
from services.didit.qr import qr_data_uri

__all__ = ['create_session', 'get_decision', 'extract_id_fields', 'qr_data_uri']
