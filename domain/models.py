"""
Tortoise ORM models for edupersona application
"""
from datetime import date
from tortoise import fields
from ng_store.models import QModel, FieldSpec, Validator, required_validator


class InvitationStatus:
    """Invitation status pseudo-enum"""
    options = ["pending", "accepted", "expired"]

_email_validator = Validator(
    message="Must be a valid email address",
    validator=lambda v, _: '@' in v if v else True
)

class Guest(QModel):
    """Guest/user entity"""
    field_specs = {
        'email': FieldSpec(validators=[_email_validator]),
        'given_name': FieldSpec(validators=[required_validator]),
        'family_name': FieldSpec(validators=[required_validator]),
    }

    id = fields.IntField(primary_key=True)
    tenant = fields.CharField(max_length=255)
    user_id = fields.CharField(max_length=255, unique=True)         # SCIM 'userName' (required & unique)
    scim_id = fields.CharField(max_length=255, null=True)           # SCIM 'id' field ('their' resource id)
    #
    given_name = fields.CharField(max_length=255, null=True)        # SCIM: 'givenName'
    family_name = fields.CharField(max_length=255, null=True)       # SCIM: 'familyName'
    email = fields.CharField(max_length=255)
    # SCIM: TO DO,
    # - map email to 'emails' (list of email strings),
    # - map names to formattedName and displayName (display_name is available as a derived field, see storage.py)
    #
    role_assignments: fields.ReverseRelation["RoleAssignment"]
    invitations: fields.ReverseRelation["Invitation"]
    attributes: fields.ReverseRelation["GuestAttribute"]

    class Meta:
        table = "guests"


class GuestAttribute(QModel):
    """Guest OIDC attributes from various authentication flows"""
    id = fields.IntField(primary_key=True)
    guest = fields.ForeignKeyField("models.Guest", related_name="attributes")
    name = fields.CharField(max_length=255)  # identifies source, e.g., "eduID login", "login instelling"
    value = fields.TextField()  # JSON string with attributes, lists as "[x,y]"

    class Meta:
        table = "guest_attributes"


class Role(QModel):
    """Roles for organizing invitations with redirect config"""
    id = fields.IntField(primary_key=True)
    tenant = fields.CharField(max_length=255)
    scim_id = fields.CharField(max_length=255, null=True)       # SCIM: 'id' field ('their' resource id)
    #
    name = fields.CharField(max_length=255)                     # SCIM: 'displayName', eg 'Gastdocent XYZ'
    role_details = fields.CharField(max_length=255, null=True)  # subheader to explain role entitlements
    scope = fields.CharField(max_length=255, null=True)         # applicable scope for admin rights, eg 'upva'
    org_name = fields.CharField(max_length=255, null=True)      # eg, 'Universitaire PABO UvA'
    logo_file_name = fields.CharField(max_length=255, null=True)    # location in static, eg, "uva/canvas.png"
    #
    # invitation-related, later verhuizen naar een step-card...?
    mail_sender_email = fields.CharField(max_length=255)        # dit moet een @edupersona.nl mailadres zijn!
    mail_sender_name = fields.CharField(max_length=255)         # gebruikt in sjabloon, dus 'schoon' houden
    more_info_email = fields.CharField(max_length=255, null=True)   # 'als je vragen hebt...'
    more_info_name = fields.CharField(max_length=255, null=True)    # defaults naar mail_sender_*
    #
    redirect_url = fields.CharField(max_length=512)             # link to associated SP
    redirect_text = fields.CharField(max_length=255)            # text for redirect link
    #
    default_start_date = fields.DateField(null=True)            # pre-fill start for new assignments
    default_end_date = fields.DateField(null=True)              # pre-fill end for new assignments
    role_end_date = fields.DateField()                          # mandatory hard cap, role deleted after this date
    #
    role_assignments: fields.ReverseRelation["RoleAssignment"]

    class Meta:
        table = "roles"


class RoleAssignment(QModel):
    """Guest-role binding with date range (no invitation/status - just the assignment)"""
    id = fields.IntField(primary_key=True)
    tenant = fields.CharField(max_length=255)
    guest = fields.ForeignKeyField("models.Guest", related_name="role_assignments")
    role = fields.ForeignKeyField("models.Role", related_name="role_assignments")
    start_date = fields.DateField(null=True)
    end_date = fields.DateField(null=True)

    @classmethod
    def calculate_assignment_dates(
        cls,
        role_dict: dict,
        current_start: str | None = None,
        current_end: str | None = None
    ) -> tuple[str, str]:
        """
        Pre-fill assignment dates from role defaults, capped at role_end_date.
        User-entered dates take precedence but end_date is always capped.

        Returns:
            Tuple of (start_date_str, end_date_str) in YYYY-MM-DD format
        """
        def parse_date(val) -> date | None:
            if val is None or val == '':
                return None
            if isinstance(val, date):
                return val
            try:
                return date.fromisoformat(str(val))
            except (ValueError, TypeError):
                return None

        role_end = parse_date(role_dict.get('role_end_date'))

        # Start date: user value or role default
        start_str = current_start or ''
        if not start_str:
            default_start = parse_date(role_dict.get('default_start_date'))
            start_str = default_start.isoformat() if default_start else ''

        # End date: user value or role default, capped at role_end_date
        end_obj = parse_date(current_end)
        if not end_obj:
            end_obj = parse_date(role_dict.get('default_end_date'))

        # Cap at role_end_date
        if end_obj and role_end and end_obj > role_end:
            end_obj = role_end
        elif not end_obj and role_end:
            end_obj = role_end

        end_str = end_obj.isoformat() if end_obj else ''
        return (start_str, end_str)

    class Meta:
        table = "role_assignments"


class Invitation(QModel):
    """Invitation sent to a guest for one or more role assignments"""
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=32, unique=True, db_index=True)
    tenant = fields.CharField(max_length=255)
    guest = fields.ForeignKeyField("models.Guest", related_name="invitations")
    personal_message = fields.TextField(null=True)
    invitation_email = fields.CharField(max_length=255)
    invited_at = fields.DatetimeField(auto_now_add=True)
    accepted_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=50, default="pending")  # see InvitationStatus
    # Junction relation: invitation.role_assignments via InvitationRoleAssignment
    invitation_role_assignments: fields.ReverseRelation["InvitationRoleAssignment"]

    class Meta:
        table = "invitations"


class InvitationRoleAssignment(QModel):
    """Junction table linking invitations to role assignments (M:N)"""
    id = fields.IntField(primary_key=True)
    invitation = fields.ForeignKeyField("models.Invitation", related_name="invitation_role_assignments")
    role_assignment = fields.ForeignKeyField("models.RoleAssignment", related_name="invitation_role_assignments")

    class Meta:
        table = "invitation_role_assignments"
