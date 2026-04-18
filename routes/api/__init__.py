"""
RESTful API v1 package for edupersona.

Tenant-scoped endpoints (/{tenant}/api/v1/...) require X-API-Key header.
Non-tenant endpoints (e.g. cleanup) use their own auth mechanism.
"""
from fastapi import APIRouter, Depends

from services.auth.dependencies import require_api_key

# Tenant-scoped router — all routes require a valid per-tenant API key
tenant_api_router = APIRouter(dependencies=[Depends(require_api_key)])

# Top-level router (cleanup uses its own API key mechanism)
api_router = APIRouter()

# Import tenant-scoped route modules (register on tenant_api_router)
from . import guests, roles, role_assignments, invitations, convenience, surf_invite  # noqa: E402

# Import non-auth route modules (register on api_router)
from . import cleanup  # noqa: E402

# Nest tenant router into top-level router
api_router.include_router(tenant_api_router)

# Re-export shared utilities
from .common import api_response, api_error, validate_tenant_or_raise  # noqa: E402

__all__ = ['api_router', 'tenant_api_router', 'api_response', 'api_error', 'validate_tenant_or_raise']
