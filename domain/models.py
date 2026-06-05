"""Tortoise ORM models for edupersona (persona-mode).

Post-pivot the system is "invitations and their lifecycle": Invitation is the only
first-class entity (§2.7), with WebhookDelivery hanging off it. Guest / Role /
RoleAssignment and the junction table were dropped at the Phase I cutover.
"""
from tortoise import fields
from ng_rdm.models import RdmModel, MultitenantRdmModel


class InvitationStatus:
    """Invitation status pseudo-enum"""
    options = ["pending", "accepted", "expired"]


class Invitation(MultitenantRdmModel):
    """A self-contained onboarding record for one guest + one persona (§2.7).

    Identity facts come from the client app (given_name/family_name, display-only)
    or are written to step_outputs by the step cards. No Guest entity.
    """
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=32, unique=True, db_index=True)
    invitation_email = fields.CharField(max_length=255, db_index=True)
    given_name = fields.CharField(max_length=255, null=True)   # display string from client app; not verified
    family_name = fields.CharField(max_length=255, null=True)  # display string from client app; not verified
    invited_at = fields.DatetimeField(auto_now_add=True)
    accepted_at = fields.DatetimeField(null=True)
    expiry_date = fields.DatetimeField(null=True)  # null = never expires; sweep flips overdue → expired
    status = fields.CharField(max_length=50, default="pending")  # see InvitationStatus

    persona_key = fields.CharField(max_length=64)
    client_ref = fields.CharField(max_length=255, null=True, db_index=True)
    persona_params = fields.JSONField(null=True)   # payload pass-through, never SQL-queried (§3.1)
    sender_email = fields.CharField(max_length=255, null=True)
    sender_name = fields.CharField(max_length=255, null=True)
    callback_url = fields.CharField(max_length=1024, null=True)
    step_outputs = fields.JSONField(null=True)     # verified-fact source for the callback envelope (§2.7)

    webhook_deliveries: fields.ReverseRelation["WebhookDelivery"]

    class Meta(RdmModel.Meta):  # type: ignore[reportIncompatibleVariableOverride]
        table = "invitations"


class WebhookDelivery(RdmModel):
    """Durable outbound-callback record (one per persona invitation completion).

    Carries the built payload plus the retry state machine (§2.3, §3.2): 4xx is
    terminal, 5xx and network errors retry with exponential backoff up to a max
    attempt count. Tenant is resolved via the invitation FK — no tenant column.
    """
    id = fields.IntField(primary_key=True)
    invitation = fields.ForeignKeyField("models.Invitation", related_name="webhook_deliveries")
    attempt_n = fields.IntField(default=0)
    status = fields.CharField(max_length=20, default="pending")  # pending|in_flight|delivered|failed
    last_status_code = fields.IntField(null=True)
    last_error = fields.TextField(null=True)
    next_retry_at = fields.DatetimeField(null=True)
    payload = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta(RdmModel.Meta):  # type: ignore[reportIncompatibleVariableOverride]
        table = "webhook_deliveries"
