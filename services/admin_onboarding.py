"""Self-service admin onboarding — the `"admin_onboarding"` completion action.

When a persona declares `completion.action == "admin_onboarding"`, finishing its
onboarding provisions the verified eduID `sub` as a tenant admin (written to
settings.json + reloaded) and e-mails the collected intake to the configured address,
in place of the usual webhook callback. Invoked best-effort from `accept_invitation`.
"""
from ng_rdm.utils import logger

from domain.models import Invitation
from domain.persona import CompletionConfig
from services.postmark.postmark import send_postmark_email
from services.settings import get_tenant_config, upsert_tenant_admin


async def complete_admin_onboarding(tenant: str, inv: Invitation, completion: CompletionConfig) -> None:
    """Provision the eduID `sub` as a tenant admin and notify, from a completed invite."""
    outputs = inv.step_outputs or {}
    sub = (outputs.get("eduid_login") or {}).get("sub")
    if not sub:
        logger.error(f"admin onboarding: no eduID 'sub' in step_outputs for invitation {inv.id}; skipping")
        return

    # display_name from the registration data (voornaam/achternaam), else the e-mail.
    display_name = " ".join(p for p in (inv.given_name, inv.family_name) if p).strip() or inv.invitation_email
    upsert_tenant_admin(tenant, sub, display_name, completion.authz)
    logger.info(f"admin onboarding: provisioned '{display_name}' ({sub}) for '{tenant}' authz={completion.authz}")

    await _send_intake_notification(tenant, inv, completion, sub, display_name, outputs)


async def _send_intake_notification(
    tenant: str, inv: Invitation, completion: CompletionConfig,
    sub: str, display_name: str, outputs: dict,
) -> None:
    """E-mail the collected intake to the persona's `notify_email` (best-effort)."""
    if not completion.notify_email:
        return
    intake = outputs.get("collect_intake") or {}
    tenant_mail = get_tenant_config(tenant).get("mail") or {}
    body = (
        f"New eduPersona admin onboarded for tenant '{tenant}':\n\n"
        f"Name: {display_name}\n"
        f"Email: {inv.invitation_email}\n"
        f"eduID sub: {sub}\n"
        f"Organisatie: {intake.get('organisatie') or '—'}\n"
        f"Toepassingsscenario: {intake.get('toepassingsscenario') or '—'}\n"
    )
    ok = await send_postmark_email({
        "from_email": tenant_mail.get("sender_email") or "noreply@edupersona.nl",
        "from_name": tenant_mail.get("sender_name") or "eduPersona",
        "to_email": completion.notify_email,
        "subject": f"eduPersona admin onboarded: {display_name}",
        "html_body": f"<pre>{body}</pre>",
        "text_body": body,
    })
    if not ok:
        logger.error(f"admin onboarding: notify mail to {completion.notify_email} failed for invitation {inv.id}")
