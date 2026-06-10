"""Tenant registration and the invitation store façade.

Writes go to the `Invitation` model directly. This module registers tenants at
startup plus one lightweight read/delete façade over `Invitation` for the admin list page —
a plain `MultitenantTortoiseStore` with a single `calc_guest_name` derived field, so
the ng_rdm `ListTable`/`DetailCard` widgets get the data-source protocol they expect.
"""
from ng_rdm.store.multitenancy import MultitenantTortoiseStore, set_valid_tenants
from ng_rdm.utils import logger

from domain.models import Invitation


def initialize_multitenancy() -> None:
    """Register all configured tenants from settings."""
    from services.settings import config

    tenants = list(config.tenants.keys())
    set_valid_tenants(tenants)
    logger.info(f"Registered tenants: {tenants}")


def _calc_guest_name(row: dict) -> str:
    name = ((row.get("given_name") or "") + " " + (row.get("family_name") or "")).strip()
    return name or row.get("invitation_email") or ""


_invitation_stores: dict[str, MultitenantTortoiseStore] = {}


def get_invitation_store(tenant: str) -> MultitenantTortoiseStore:
    """Tenant-scoped singleton store over `Invitation` for the admin list page.

    Singleton so a `ListTable` observing it refreshes on its own deletes. The accept /
    API flows still write `Invitation` directly (domain/invitations.py) — this façade is
    read + delete only, with `calc_guest_name` derived from the row's own name columns.
    """
    store = _invitation_stores.get(tenant)
    if store is None:
        store = MultitenantTortoiseStore(Invitation, tenant=tenant)
        store.set_derived_fields({"calc_guest_name": _calc_guest_name})
        _invitation_stores[tenant] = store
    return store
