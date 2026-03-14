"""
Role CRUD endpoints for API v1.

GET    /{tenant}/api/v1/roles            - List all roles
GET    /{tenant}/api/v1/roles/{id}       - Get single role
POST   /{tenant}/api/v1/roles            - Create role
PATCH  /{tenant}/api/v1/roles/{id}       - Update role
DELETE /{tenant}/api/v1/roles/{id}       - Delete role
GET    /{tenant}/api/v1/roles/{id}/assignments - List role assignments for this role
"""
from datetime import date, timedelta

from fastapi import HTTPException, Query
from pydantic import BaseModel

from . import api_router

from domain.stores import get_role_store, get_role_assignment_store
from .common import (
    api_response, api_error, validate_tenant_or_raise,
    apply_pagination, log_api_call,
)


class RoleCreate(BaseModel):
    name: str
    scim_id: str | None = None
    role_details: str | None = None
    scope: str | None = None
    org_name: str | None = None
    logo_file_name: str | None = None
    mail_sender_email: str = ""
    mail_sender_name: str = ""
    more_info_email: str | None = None
    more_info_name: str | None = None
    redirect_url: str = ""
    redirect_text: str = ""
    default_start_date: str | None = None
    default_end_date: str | None = None
    role_end_date: str | None = None  # Defaults to 1 year from now if not provided


class RoleUpdate(BaseModel):
    name: str | None = None
    scim_id: str | None = None
    role_details: str | None = None
    scope: str | None = None
    org_name: str | None = None
    logo_file_name: str | None = None
    mail_sender_email: str | None = None
    mail_sender_name: str | None = None
    more_info_email: str | None = None
    more_info_name: str | None = None
    redirect_url: str | None = None
    redirect_text: str | None = None
    default_start_date: str | None = None
    default_end_date: str | None = None
    role_end_date: str | None = None


@api_router.get("/{tenant}/api/v1/roles")
async def list_roles(
    tenant: str,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all roles."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", "/roles", tenant, q=q, limit=limit, offset=offset)

    try:
        role_store = get_role_store(tenant)
        items = await role_store.read_items(q=q)

        total = len(items)
        paginated = apply_pagination(items, limit, offset)
        return api_response(paginated, total=total, limit=limit, offset=offset)

    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/roles/{role_id}")
async def get_role(tenant: str, role_id: int):
    """Get single role by ID."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/roles/{role_id}", tenant)

    try:
        role_store = get_role_store(tenant)
        role = await role_store.read_item_by_id(role_id)
        if not role:
            raise api_error("NOT_FOUND", f"Role {role_id} not found", status_code=404)
        return api_response(role)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.post("/{tenant}/api/v1/roles")
async def create_role(tenant: str, data: RoleCreate):
    """Create a new role."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/roles", tenant)

    try:
        role_store = get_role_store(tenant)

        role_data = {"tenant": tenant, **data.model_dump(exclude_none=True)}

        # Default role_end_date to 1 year from now if not provided
        if not role_data.get("role_end_date"):
            role_data["role_end_date"] = (date.today() + timedelta(days=365)).isoformat()

        created = await role_store.create_item(role_data)
        if not created:
            raise api_error("CREATE_FAILED", "Failed to create role", status_code=500)

        return api_response(created)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.patch("/{tenant}/api/v1/roles/{role_id}")
async def update_role(tenant: str, role_id: int, data: RoleUpdate):
    """Update role fields."""
    validate_tenant_or_raise(tenant)
    log_api_call("PATCH", f"/roles/{role_id}", tenant)

    try:
        role_store = get_role_store(tenant)

        # Check role exists
        role = await role_store.read_item_by_id(role_id)
        if not role:
            raise api_error("NOT_FOUND", f"Role {role_id} not found", status_code=404)

        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            raise api_error("INVALID_REQUEST", "No fields to update", status_code=400)

        updated = await role_store.update_item(role_id, update_data)
        if not updated:
            raise api_error("UPDATE_FAILED", "Failed to update role", status_code=500)

        return api_response(updated)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.delete("/{tenant}/api/v1/roles/{role_id}")
async def delete_role(tenant: str, role_id: int):
    """Delete a role."""
    validate_tenant_or_raise(tenant)
    log_api_call("DELETE", f"/roles/{role_id}", tenant)

    try:
        role_store = get_role_store(tenant)

        # Check role exists
        role = await role_store.read_item_by_id(role_id)
        if not role:
            raise api_error("NOT_FOUND", f"Role {role_id} not found", status_code=404)

        await role_store.delete_item(role)
        return api_response({"deleted": True, "id": role_id})

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/roles/{role_id}/assignments")
async def get_role_assignments(
    tenant: str,
    role_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List role assignments for this role."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/roles/{role_id}/assignments", tenant)

    try:
        # Verify role exists
        role_store = get_role_store(tenant)
        role = await role_store.read_item_by_id(role_id)
        if not role:
            raise api_error("NOT_FOUND", f"Role {role_id} not found", status_code=404)

        ra_store = get_role_assignment_store(tenant)
        items = await ra_store.read_items(filter_by={"role_id": role_id})

        total = len(items)
        paginated = apply_pagination(items, limit, offset)
        return api_response(paginated, total=total, limit=limit, offset=offset)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)
