"""
Convenience endpoints for API v1.

POST /{tenant}/api/v1/quick-invite - Create guest + assignment + invitation in one call
"""
from fastapi import HTTPException
from pydantic import BaseModel

from . import api_router

from services.storage.storage import (
    get_guest_store,
    get_role_store,
    create_role_assignment,
    create_invitation,
)
from .common import api_response, api_error, validate_tenant_or_raise, log_api_call


class QuickInviteRequest(BaseModel):
    user_id: str
    email: str
    given_name: str | None = None
    family_name: str | None = None
    role_id: int | None = None
    role_name: str | None = None  # Alternative to role_id
    start_date: str | None = None
    end_date: str | None = None
    personal_message: str | None = None


@api_router.post("/{tenant}/api/v1/quick-invite")
async def quick_invite(tenant: str, data: QuickInviteRequest):
    """Create guest + role assignment + invitation in one call.

    Either role_id or role_name must be provided. If guest already exists
    (by user_id), the existing guest is used.
    """
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/quick-invite", tenant, user_id=data.user_id)

    try:
        guest_store = get_guest_store(tenant)
        role_store = get_role_store(tenant)

        # Resolve role
        if data.role_id:
            role = await role_store.read_item_by_id(data.role_id)
            if not role:
                raise api_error("NOT_FOUND", f"Role {data.role_id} not found", status_code=404)
        elif data.role_name:
            roles = await role_store.read_items(filter_by={"name": data.role_name.strip()})
            if not roles:
                raise api_error("NOT_FOUND", f"Role '{data.role_name}' not found", status_code=404)
            role = roles[0]
        else:
            raise api_error("VALIDATION_ERROR", "Either role_id or role_name is required", status_code=400)

        # Find or create guest
        guests = await guest_store.read_items(filter_by={"user_id": data.user_id})
        if guests:
            guest = guests[0]
            created_guest = False
        else:
            guest_data = {
                "tenant": tenant,
                "user_id": data.user_id,
                "email": data.email,
            }
            if data.given_name:
                guest_data["given_name"] = data.given_name
            if data.family_name:
                guest_data["family_name"] = data.family_name

            guest = await guest_store.create_item(guest_data)
            if not guest:
                raise api_error("CREATE_FAILED", "Failed to create guest", status_code=500)
            created_guest = True

        # Create role assignment
        try:
            role_assignment = await create_role_assignment(
                tenant,
                guest["id"],
                role["id"],
                start_date=data.start_date or "",
                end_date=data.end_date or "",
            )
        except ValueError as e:
            raise api_error("VALIDATION_ERROR", str(e), status_code=400)

        # Create invitation
        try:
            invitation = await create_invitation(
                tenant,
                guest["id"],
                [role_assignment["id"]],
                data.email,
                personal_message=data.personal_message or "",
            )
        except ValueError as e:
            raise api_error("VALIDATION_ERROR", str(e), status_code=400)

        return api_response({
            "guest": guest,
            "guest_created": created_guest,
            "role_assignment": role_assignment,
            "invitation": invitation,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)
