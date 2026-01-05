"""
RESTful API endpoints for edupersona application.
Provides JSON API access to invitations and groups data.
"""

import json

from fastapi import HTTPException, Request
from nicegui import app

from services.logging import logger
from services.storage import (
    create_invitation,
    find,
    find_one,
    upsert,
)


# GET /api/invitations - return all invitations
@app.get("/api/invitations")
async def get_invitations():
    """GET /api/invitations - return all invitations"""
    try:
        invitations = find("memberships", with_relations=["guest", "group"])
        logger.info(f"API GET /api/invitations - returning {len(invitations)} invitations")
        return invitations
    except Exception as e:
        logger.error(f"API GET /api/invitations error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# POST /api/invitations - create new invitation
@app.post("/api/invitations")
async def create_invitation_api(request: Request):
    """POST /api/invitations - create new invitation"""
    try:
        # Parse JSON request body
        body = await request.body()
        data = json.loads(body.decode('utf-8'))
        logger.info(f"API POST /api/invitations - received data: {data}")

        # Validate required fields
        required_fields = ['guest_id', 'group_name', 'invitation_mail_address']
        missing_fields = [field for field in required_fields if not data.get(field, '').strip()]

        if missing_fields:
            logger.warning(f"API POST /api/invitations - missing fields: {missing_fields}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Missing required fields",
                    "missing_fields": missing_fields
                }
            )

        # Look up group by name to get group_id
        group = find_one("groups", name=data['group_name'].strip())

        if not group:
            logger.warning(f"API POST /api/invitations - group not found: {data['group_name']}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Group not found",
                    "group_name": data['group_name'].strip()
                }
            )

        # Create invitation using the found group_id
        invitation_id = create_invitation(
            data['guest_id'].strip(),
            group['id'],
            data['invitation_mail_address'].strip()
        )

        logger.info(f"API POST /api/invitations - created invitation: {invitation_id}")

        # Return created invitation
        return {
            "invitation_id": invitation_id,
            "guest_id": data['guest_id'].strip(),
            "group_name": data['group_name'].strip(),
            "group_id": group['id'],
            "invitation_mail_address": data['invitation_mail_address'].strip(),
            "message": "Invitation created successfully"
        }

    except json.JSONDecodeError as e:
        logger.error(f"API POST /api/invitations - JSON decode error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except Exception as e:
        logger.error(f"API POST /api/invitations error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# GET /api/groups - return all groups
@app.get("/api/groups")
async def get_groups():
    """GET /api/groups - return all groups"""
    try:
        groups = find("groups")
        logger.info(f"API GET /api/groups - returning {len(groups)} groups")
        return groups
    except Exception as e:
        logger.error(f"API GET /api/groups error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


"""
# example POST /api/invite_roles payload:
{
  "name": "Gastdocent in Gastrononie [4]",
    "shortName": "d245496f27814809a5ef986f22d5fe1d",
    "applicationUsages": [
        {
            "id": 3489,
            "landingPage": "https://uvadlo-acc.instructure.com/courses/3813",
            "landingPageName": "Canvas: Gastdocent in Gastrononie",
            "application": {
                "id": 534,
                "manageId": "68c551ce-dad6-4f13-a936-720167de227c",
                "manageType": "SAML20_SP"
            }
        }
    ]
}
# shortName is mapped to group_id (our internal identifier)
# name is mapped to name
# redirect_url is taken from applicationUsages[0].landingPage
# redirect_text is taken from applicationUsages[0].landingPageName, defaults to "name"  -- note this is NOT in Invite API
"""

# POST /api/invite_roles - create/update group (SURF Invite Role API lookalike, lots of data discarded)
@app.post("/api/invite_roles")
async def create_invite_role(request: Request):
    """POST /api/invite_roles - create or update group, emulating SURF Invite API"""
    # note: shortName (as sent in the json) is used as our group_id
    try:
        body = await request.body()
        data = json.loads(body.decode('utf-8'))
        logger.info(f"API POST /api/invite_roles - received SURF payload: {json.dumps(data)}")

        # Extract and validate fields
        name = data.get('name', '').strip()
        group_id = data.get('shortName', '').strip()
        if not name or not group_id:
            raise HTTPException(status_code=400, detail={
                                "error": "Missing required fields", "required": ["name", "shortName"]})

        # Extract redirect_url from applicationUsages
        redirect_url = ""
        if app_usages := data.get('applicationUsages', []):
            redirect_url = app_usages[0].get('landingPage', '').strip()
            redirect_text = app_usages[0].get('landingPageName', name)

        # Upsert group by group_id
        group_id, was_created = upsert("groups", {"group_id": group_id}, {
                                       "name": name, "redirect_url": redirect_url, "redirect_text": redirect_text})
        action = "created" if was_created else "updated"
        logger.info(f"API POST /api/invite_roles - {action} group: {group_id}")

        return {"group_id": group_id, "name": name, "redirect_url": redirect_url, "message": f"Group {action} successfully"}

    except json.JSONDecodeError as e:
        logger.error(f"API POST /api/invite_roles - JSON decode error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API POST /api/invite_roles error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
