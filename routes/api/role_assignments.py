"""
Role Assignment CRUD endpoints for API v1.

GET    /{tenant}/api/v1/role-assignments           - List all role assignments
GET    /{tenant}/api/v1/role-assignments/{id}      - Get single assignment
POST   /{tenant}/api/v1/role-assignments           - Create assignment
PATCH  /{tenant}/api/v1/role-assignments/{id}      - Update dates
DELETE /{tenant}/api/v1/role-assignments/{id}      - Delete assignment
"""
from fastapi import HTTPException, Query
from pydantic import BaseModel

from . import api_router

from services.storage.storage import (
    get_role_assignment_store,
    get_guest_store,
    get_role_store,
    create_role_assignment,
    update_role_assignment,
)
from models.models import InvitationRoleAssignment
from .common import (
    api_response, api_error, validate_tenant_or_raise,
    apply_pagination, log_api_call,
)


class RoleAssignmentCreate(BaseModel):
    guest_id: int
    role_id: int
    start_date: str | None = None
    end_date: str | None = None


class RoleAssignmentUpdate(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


@api_router.get("/{tenant}/api/v1/role-assignments")
async def list_role_assignments(
    tenant: str,
    guest_id: int | None = None,
    role_id: int | None = None,
    expand: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all role assignments with optional filtering."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", "/role-assignments", tenant, guest_id=guest_id, role_id=role_id, limit=limit, offset=offset)

    try:
        ra_store = get_role_assignment_store(tenant)

        # Build filter
        filter_by: dict = {}
        if guest_id is not None:
            filter_by["guest_id"] = guest_id
        if role_id is not None:
            filter_by["role_id"] = role_id

        items = await ra_store.read_items(filter_by=filter_by if filter_by else None)

        # Handle expand for guest and/or role
        if expand:
            expand_fields = [f.strip() for f in expand.split(",")]
            guest_store = get_guest_store(tenant) if "guest" in expand_fields else None
            role_store = get_role_store(tenant) if "role" in expand_fields else None

            for item in items:
                if guest_store and "guest" in expand_fields:
                    guest = await guest_store.read_items(filter_by={"id": item["guest_id"]})
                    item["guest"] = guest[0] if guest else None
                if role_store and "role" in expand_fields:
                    role = await role_store.read_item_by_id(item["role_id"])
                    item["role"] = role

        total = len(items)
        paginated = apply_pagination(items, limit, offset)
        return api_response(paginated, total=total, limit=limit, offset=offset)

    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.get("/{tenant}/api/v1/role-assignments/{assignment_id}")
async def get_role_assignment(tenant: str, assignment_id: int, expand: str | None = None):
    """Get single role assignment by ID."""
    validate_tenant_or_raise(tenant)
    log_api_call("GET", f"/role-assignments/{assignment_id}", tenant)

    try:
        ra_store = get_role_assignment_store(tenant)
        items = await ra_store.read_items(filter_by={"id": assignment_id})
        if not items:
            raise api_error("NOT_FOUND", f"Role assignment {assignment_id} not found", status_code=404)

        item = items[0]

        # Handle expand
        if expand:
            expand_fields = [f.strip() for f in expand.split(",")]
            if "guest" in expand_fields:
                guest_store = get_guest_store(tenant)
                guest = await guest_store.read_items(filter_by={"id": item["guest_id"]})
                item["guest"] = guest[0] if guest else None
            if "role" in expand_fields:
                role_store = get_role_store(tenant)
                role = await role_store.read_item_by_id(item["role_id"])
                item["role"] = role

        return api_response(item)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.post("/{tenant}/api/v1/role-assignments")
async def create_role_assignment_endpoint(tenant: str, data: RoleAssignmentCreate):
    """Create a new role assignment."""
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/role-assignments", tenant)

    try:
        # Verify guest exists
        guest_store = get_guest_store(tenant)
        guests = await guest_store.read_items(filter_by={"id": data.guest_id})
        if not guests:
            raise api_error("NOT_FOUND", f"Guest {data.guest_id} not found", status_code=404)

        # Verify role exists
        role_store = get_role_store(tenant)
        role = await role_store.read_item_by_id(data.role_id)
        if not role:
            raise api_error("NOT_FOUND", f"Role {data.role_id} not found", status_code=404)

        # Create assignment using storage function (handles validation)
        try:
            assignment = await create_role_assignment(
                tenant,
                data.guest_id,
                data.role_id,
                start_date=data.start_date or "",
                end_date=data.end_date or "",
            )
        except ValueError as e:
            raise api_error("VALIDATION_ERROR", str(e), status_code=400)

        return api_response(assignment)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.patch("/{tenant}/api/v1/role-assignments/{assignment_id}")
async def update_role_assignment_endpoint(tenant: str, assignment_id: int, data: RoleAssignmentUpdate):
    """Update role assignment dates."""
    validate_tenant_or_raise(tenant)
    log_api_call("PATCH", f"/role-assignments/{assignment_id}", tenant)

    try:
        ra_store = get_role_assignment_store(tenant)

        # Check assignment exists
        items = await ra_store.read_items(filter_by={"id": assignment_id})
        if not items:
            raise api_error("NOT_FOUND", f"Role assignment {assignment_id} not found", status_code=404)

        current = items[0]

        # Update using storage function (handles validation)
        try:
            updated = await update_role_assignment(
                tenant,
                assignment_id,
                start_date=data.start_date if data.start_date is not None else current.get("start_date", ""),
                end_date=data.end_date if data.end_date is not None else current.get("end_date", ""),
            )
        except ValueError as e:
            raise api_error("VALIDATION_ERROR", str(e), status_code=400)

        return api_response(updated)

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)


@api_router.delete("/{tenant}/api/v1/role-assignments/{assignment_id}")
async def delete_role_assignment(tenant: str, assignment_id: int):
    """Delete a role assignment."""
    validate_tenant_or_raise(tenant)
    log_api_call("DELETE", f"/role-assignments/{assignment_id}", tenant)

    try:
        ra_store = get_role_assignment_store(tenant)

        # Check assignment exists
        items = await ra_store.read_items(filter_by={"id": assignment_id})
        if not items:
            raise api_error("NOT_FOUND", f"Role assignment {assignment_id} not found", status_code=404)

        # Delete junction records first (foreign key constraint)
        await InvitationRoleAssignment.filter(role_assignment_id=assignment_id).delete()

        # Delete assignment
        await ra_store.delete_item(items[0])
        return api_response({"deleted": True, "id": assignment_id})

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)
