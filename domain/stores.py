"""Tenant registration for persona-mode.

The ng_rdm store façade was role-mode scaffolding; persona-mode reads/writes the
`Invitation` model directly (Shape B, §2.7). All that remains here is tenant
registration at startup.
"""
from ng_rdm.store.multitenancy import set_valid_tenants
from ng_rdm.utils import logger


def initialize_multitenancy() -> None:
    """Register all configured tenants from settings."""
    from services.settings import config

    tenants = list(config.tenants.keys())
    set_valid_tenants(tenants)
    logger.info(f"Registered tenants: {tenants}")
