"""
Guest CRUD endpoints for API v1.

GET    /{tenant}/api/v1/guests           - List all guests
GET    /{tenant}/api/v1/guests/{id}      - Get single guest
POST   /{tenant}/api/v1/guests           - Create guest
PATCH  /{tenant}/api/v1/guests/{id}      - Update guest
DELETE /{tenant}/api/v1/guests/{id}      - Delete guest
GET    /{tenant}/api/v1/guests/{id}/attributes      - Get guest's OIDC attributes
GET    /{tenant}/api/v1/guests/{id}/role-assignments - Get guest's role assignments
GET    /{tenant}/api/v1/guests/{id}/invitations     - Get guest's invitations
"""
from fastapi import HTTPException, Query
from pydantic import BaseModel

from . import api_router

from domain.stores import (
    get_guest_store,
    get_guest_attribute_store,
    get_role_assignment_store,
    get_invitation_store,
)
from .common import (
    api_response, api_error, validate_tenant_or_raise,
    parse_expand, apply_pagination, log_api_call,
)


class GuestCreate(BaseModel):
    user_id: str
    email: str
    given_name: str | None = None
    family_name: str | None = None
    scim_id: str | None = None


class GuestUpdate(BaseModel):
    email: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    scim_id: str | None = None


@api_router.get("/{tenant}/api/v1/guests")
async def list_guests(
    tenant: str,
    q: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all guests with enriched data (assignment_count, guest_statuses)."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", "/guests", tenant, q=q, status=status, limit=limit, offset=offset)

    try:
        guest_store = get_guest_store(tenant)
        items = await guest_store.read_items(q=q)

        # Filter by status if provided
        if status:
            items = [g for g in items if status in g.get("guest_statuses", [])]

        total = len(items)
        paginated = apply_pagination(items, limit, offset)
        return api_response(paginated, total=total, limit=limit, offset=offset)

    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/guests/{guest_id}")
async def get_guest(tenant: str, guest_id: int):
    """Get single guest by ID."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/guests/{guest_id}", tenant)

    try:
        guest_store = get_guest_store(tenant)
        items = await guest_store.read_items(filter_by={"id": guest_id})
        if not items:
            raise api_error("NOT_FOUND", f"Guest {guest_id} not found", status_code=404)
        return api_response(items[0])

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.post("/{tenant}/api/v1/guests")
async def create_guest(tenant: str, data: GuestCreate):
    """Create a new guest."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/guests", tenant)

    try:
        guest_store = get_guest_store(tenant)

        # Check for existing guest with same user_id
        existing = await guest_store.read_items(filter_by={"user_id": data.user_id})
        if existing:
            raise api_error("CONFLICT", f"Guest with user_id '{data.user_id}' already exists", status_code=409)

        guest_data = {"tenant": tenant, **data.model_dump(exclude_none=True)}
        created = await guest_store.create_item(guest_data)
        if not created:
            raise api_error("CREATE_FAILED", "Failed to create guest", status_code=500)

        return api_response(created)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.patch("/{tenant}/api/v1/guests/{guest_id}")
async def update_guest(tenant: str, guest_id: int, data: GuestUpdate):
    """Update guest fields."""
    validate_tenant_or_raise(tenant)
    log_api_call("PATCH", f"/guests/{guest_id}", tenant)

    try:
        guest_store = get_guest_store(tenant)

        # Check guest exists
        items = await guest_store.read_items(filter_by={"id": guest_id})
        if not items:
            raise api_error("NOT_FOUND", f"Guest {guest_id} not found", status_code=404)

        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            raise api_error("INVALID_REQUEST", "No fields to update", status_code=400)

        updated = await guest_store.update_item(guest_id, update_data)
        if not updated:
            raise api_error("UPDATE_FAILED", "Failed to update guest", status_code=500)

        return api_response(updated)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.delete("/{tenant}/api/v1/guests/{guest_id}")
async def delete_guest(tenant: str, guest_id: int):
    """Delete a guest."""
    validate_tenant_or_raise(tenant)
    log_api_call("DELETE", f"/guests/{guest_id}", tenant)

    try:
        guest_store = get_guest_store(tenant)

        # Check guest exists
        items = await guest_store.read_items(filter_by={"id": guest_id})
        if not items:
            raise api_error("NOT_FOUND", f"Guest {guest_id} not found", status_code=404)

        await guest_store.delete_item(items[0])
        return api_response({"deleted": True, "id": guest_id})

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/guests/{guest_id}/attributes")
async def get_guest_attributes(tenant: str, guest_id: int):
    """Get guest's OIDC attributes."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/guests/{guest_id}/attributes", tenant)

    try:
        # Verify guest exists
        guest_store = get_guest_store(tenant)
        guests = await guest_store.read_items(filter_by={"id": guest_id})
        if not guests:
            raise api_error("NOT_FOUND", f"Guest {guest_id} not found", status_code=404)

        attr_store = get_guest_attribute_store(tenant)
        items = await attr_store.read_items(filter_by={"guest_id": guest_id})
        return api_response(items, total=len(items))

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/guests/{guest_id}/role-assignments")
async def get_guest_role_assignments(tenant: str, guest_id: int):
    """Get guest's role assignments."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/guests/{guest_id}/role-assignments", tenant)

    try:
        # Verify guest exists
        guest_store = get_guest_store(tenant)
        guests = await guest_store.read_items(filter_by={"id": guest_id})
        if not guests:
            raise api_error("NOT_FOUND", f"Guest {guest_id} not found", status_code=404)

        ra_store = get_role_assignment_store(tenant)
        items = await ra_store.read_items(filter_by={"guest_id": guest_id})
        return api_response(items, total=len(items))

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/guests/{guest_id}/invitations")
async def get_guest_invitations(tenant: str, guest_id: int):
    """Get guest's invitations."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/guests/{guest_id}/invitations", tenant)

    try:
        # Verify guest exists
        guest_store = get_guest_store(tenant)
        guests = await guest_store.read_items(filter_by={"id": guest_id})
        if not guests:
            raise api_error("NOT_FOUND", f"Guest {guest_id} not found", status_code=404)

        inv_store = get_invitation_store(tenant)
        items = await inv_store.read_items(filter_by={"guest_id": guest_id})
        return api_response(items, total=len(items))

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)
