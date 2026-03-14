"""
SURF Invite API compatibility endpoints.

POST /{tenant}/api/v1/invite-roles - Upsert role from SURF Invite API format

Example SURF Invite API payload:
{
  "name": "Gastdocent in Gastrononie [4]",
  "shortName": "d245496f27814809a5ef986f22d5fe1d",
  "applicationUsages": [
    {
      "id": 3489,
      "landingPage": "https://uvadlo-acc.instructure.com/courses/3813",
      "landingPageName": "Canvas: Gastdocent in Gastrononie",
      "application": { "id": 534, "manageId": "...", "manageType": "SAML20_SP" }
    }
  ]
}

Field mapping:
  shortName -> scim_id (upsert key)
  name -> name
  applicationUsages[0].landingPage -> redirect_url
  applicationUsages[0].landingPageName -> redirect_text (falls back to name)
"""
from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import BaseModel

from . import api_router

from domain.stores import get_role_store
from .common import api_response, api_error, validate_tenant_or_raise, log_api_call


class ApplicationUsage(BaseModel):
    """SURF Invite API application usage entry."""
    id: int | None = None
    landingPage: str | None = None
    landingPageName: str | None = None
    application: dict | None = None


class InviteRoleRequest(BaseModel):
    """SURF Invite API role payload."""
    name: str
    shortName: str
    applicationUsages: list[ApplicationUsage] = []


@api_router.post("/{tenant}/api/v1/invite-roles")
async def create_invite_role(tenant: str, data: InviteRoleRequest):
    """Upsert role from SURF Invite API format.

    Creates a new role or updates an existing one based on shortName (scim_id).
    """
    validate_tenant_or_raise(tenant)
    log_api_call("POST", "/invite-roles", tenant, scim_id=data.shortName)

    try:
        role_store = get_role_store(tenant)

        name = data.name.strip()
        scim_id = data.shortName.strip()

        redirect_url = ""
        redirect_text = name
        if data.applicationUsages:
            redirect_url = (data.applicationUsages[0].landingPage or "").strip()
            redirect_text = data.applicationUsages[0].landingPageName or name

        existing = await role_store.read_items(filter_by={"scim_id": scim_id})

        if existing:
            await role_store.update_item(
                existing[0]["id"],
                {"name": name, "redirect_url": redirect_url, "redirect_text": redirect_text}
            )
            return api_response({
                "id": existing[0]["id"],
                "scim_id": scim_id,
                "name": name,
                "redirect_url": redirect_url,
                "action": "updated"
            })
        else:
            default_role_end = (date.today() + timedelta(days=365)).isoformat()
            created = await role_store.create_item({
                "tenant": tenant,
                "scim_id": scim_id,
                "name": name,
                "redirect_url": redirect_url,
                "redirect_text": redirect_text,
                "mail_sender_email": "",
                "mail_sender_name": "",
                "role_end_date": default_role_end,
            })
            if not created:
                raise api_error("CREATE_FAILED", "Failed to create role", status_code=500)

            return api_response({
                "id": created["id"],
                "scim_id": scim_id,
                "name": name,
                "redirect_url": redirect_url,
                "action": "created"
            })

    except HTTPException:
        raise
    except Exception as e:
        raise api_error("INTERNAL_ERROR", str(e), status_code=500)
