"""
RESTful API v1 package for edupersona.

All endpoints are tenant-scoped: /{tenant}/api/v1/...
"""
from fastapi import APIRouter

api_router = APIRouter()

# Import all route modules to register their endpoints
from . import guests, roles, role_assignments, invitations, convenience, surf_invite, cleanup

# Re-export shared utilities
from .common import api_response, api_error, validate_tenant_or_raise

__all__ = ['api_router', 'api_response', 'api_error', 'validate_tenant_or_raise']
