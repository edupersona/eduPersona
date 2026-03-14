"""
Invitation CRUD endpoints for API v1.

GET    /{tenant}/api/v1/invitations            - List all invitations
GET    /{tenant}/api/v1/invitations/{id}       - Get single invitation by ID
GET    /{tenant}/api/v1/invitations/code/{code} - Get invitation by code
POST   /{tenant}/api/v1/invitations            - Create invitation
PATCH  /{tenant}/api/v1/invitations/{id}       - Update invitation
DELETE /{tenant}/api/v1/invitations/{id}       - Delete invitation
"""
from fastapi import HTTPException, Query
from pydantic import BaseModel

from . import api_router

from domain.stores import (
    get_invitation_store,
    get_guest_store,
    get_role_assignment_store,
)
from domain.invitation_flow import create_invitation
from domain.models import InvitationRoleAssignment
from .common import (
    api_response, api_error, validate_tenant_or_raise,
    apply_pagination, log_api_call,
)


class InvitationCreate(BaseModel):
    guest_id: int
    role_assignment_ids: list[int]
    invitation_email: str
    personal_message: str | None = None


class InvitationUpdate(BaseModel):
    status: str | None = None
    personal_message: str | None = None
    invitation_email: str | None = None


@api_router.get("/{tenant}/api/v1/invitations")
async def list_invitations(
    tenant: str,
    guest_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    expand: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all invitations with optional filtering."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", "/invitations", tenant, guest_id=guest_id, status=status, limit=limit, offset=offset)

    try:
        inv_store = get_invitation_store(tenant)

        # Build filter
        filter_by: dict = {}
        if guest_id is not None:
            filter_by["guest_id"] = guest_id
        if status:
            filter_by["status"] = status

        items = await inv_store.read_items(filter_by=filter_by if filter_by else None, q=q)

        # Handle expand for guest
        if expand:
            expand_fields = [f.strip() for f in expand.split(",")]
            if "guest" in expand_fields:
                guest_store = get_guest_store(tenant)
                for item in items:
                    guest = await guest_store.read_items(filter_by={"id": item["guest_id"]})
                    item["guest"] = guest[0] if guest else None

        total = len(items)
        paginated = apply_pagination(items, limit, offset)
        return api_response(paginated, total=total, limit=limit, offset=offset)

    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/invitations/{invitation_id}")
async def get_invitation_by_id(tenant: str, invitation_id: int, expand: str | None = None):
    """Get single invitation by ID."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/invitations/{invitation_id}", tenant)

    try:
        inv_store = get_invitation_store(tenant)
        items = await inv_store.read_items(filter_by={"id": invitation_id})
        if not items:
            raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

        item = items[0]

        # Handle expand
        if expand:
            expand_fields = [f.strip() for f in expand.split(",")]
            if "guest" in expand_fields:
                guest_store = get_guest_store(tenant)
                guest = await guest_store.read_items(filter_by={"id": item["guest_id"]})
                item["guest"] = guest[0] if guest else None

        return api_response(item)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/invitations/code/{code}")
async def get_invitation_by_code(tenant: str, code: str, expand: str | None = None):
    """Get invitation by code (public lookup)."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/invitations/code/{code[:8]}...", tenant)

    try:
        inv_store = get_invitation_store(tenant)
        items = await inv_store.read_items(filter_by={"code": code})
        if not items:
            raise api_error("NOT_FOUND", "Invitation not found", status_code=404)

        item = items[0]

        # Handle expand
        if expand:
            expand_fields = [f.strip() for f in expand.split(",")]
            if "guest" in expand_fields:
                guest_store = get_guest_store(tenant)
                guest = await guest_store.read_items(filter_by={"id": item["guest_id"]})
                item["guest"] = guest[0] if guest else None

        return api_response(item)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.post("/{tenant}/api/v1/invitations")
async def create_invitation_endpoint(tenant: str, data: InvitationCreate):
    """Create a new invitation."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/invitations", tenant)

    try:
        # Verify guest exists
        guest_store = get_guest_store(tenant)
        guests = await guest_store.read_items(filter_by={"id": data.guest_id})
        if not guests:
            raise api_error("NOT_FOUND", f"Guest {data.guest_id} not found", status_code=404)

        # Verify all role assignments exist
        ra_store = get_role_assignment_store(tenant)
        for ra_id in data.role_assignment_ids:
            items = await ra_store.read_items(filter_by={"id": ra_id})
            if not items:
                raise api_error("NOT_FOUND", f"Role assignment {ra_id} not found", status_code=404)

        # Create invitation using storage function
        try:
            invitation = await create_invitation(
                tenant,
                data.guest_id,
                data.role_assignment_ids,
                data.invitation_email,
                personal_message=data.personal_message or "",
            )
        except ValueError as e:
            raise api_error("VALIDATION_ERROR", str(e), status_code=400)

        return api_response(invitation)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.patch("/{tenant}/api/v1/invitations/{invitation_id}")
async def update_invitation(tenant: str, invitation_id: int, data: InvitationUpdate):
    """Update invitation fields."""
    validate_tenant_or_raise(tenant)
    log_api_call("PATCH", f"/invitations/{invitation_id}", tenant)

    try:
        inv_store = get_invitation_store(tenant)

        # Check invitation exists
        items = await inv_store.read_items(filter_by={"id": invitation_id})
        if not items:
            raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            raise api_error("INVALID_REQUEST", "No fields to update", status_code=400)

        # Validate status if provided
        if "status" in update_data:
            valid_statuses = ["pending", "accepted", "expired"]
            if update_data["status"] not in valid_statuses:
                raise api_error("VALIDATION_ERROR",
                                f"Invalid status. Must be one of: {valid_statuses}", status_code=400)

        updated = await inv_store.update_item(invitation_id, update_data)
        if not updated:
            raise api_error("UPDATE_FAILED", "Failed to update invitation", status_code=500)

        return api_response(updated)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.delete("/{tenant}/api/v1/invitations/{invitation_id}")
async def delete_invitation(tenant: str, invitation_id: int):
    """Delete an invitation."""
    validate_tenant_or_raise(tenant)
    log_api_call("DELETE", f"/invitations/{invitation_id}", tenant)

    try:
        inv_store = get_invitation_store(tenant)

        # Check invitation exists
        items = await inv_store.read_items(filter_by={"id": invitation_id})
        if not items:
            raise api_error("NOT_FOUND", f"Invitation {invitation_id} not found", status_code=404)

        # Delete junction records first
        await InvitationRoleAssignment.filter(invitation_id=invitation_id).delete()

        # Delete invitation
        await inv_store.delete_item(items[0])
        return api_response({"deleted": True, "id": invitation_id})

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)
