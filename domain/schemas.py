"""
API request/response schemas (Pydantic models).
"""
from pydantic import BaseModel


# Guest schemas
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


# Role schemas
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


# Role Assignment schemas
class RoleAssignmentCreate(BaseModel):
    guest_id: int
    role_id: int
    start_date: str | None = None
    end_date: str | None = None


class RoleAssignmentUpdate(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


# Invitation schemas
class InvitationCreate(BaseModel):
    guest_id: int
    role_assignment_ids: list[int]
    invitation_email: str
    personal_message: str | None = None


class InvitationUpdate(BaseModel):
    status: str | None = None
    personal_message: str | None = None
    invitation_email: str | None = None


# Convenience endpoint schemas
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


# SURF Invite API schemas
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
