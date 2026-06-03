"""Persona-aware mail composition (parallel to the role-mode postmark functions).

Per-tenant layout frame + per-persona body, both Jinja2 (§6). Reuses the existing
Postmark transport (`send_postmark_email`). Sender identity resolves
invitation-override > tenant default. Folded into postmark.py at Phase I.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from services.postmark.postmark import html_to_text, send_postmark_email
from services.persona_loader import get_persona_config
from services.settings import config, get_tenant_config

_TEMPLATE_DIR = Path(__file__).parent / "templates"


async def prepare_persona_invite_message(invitation: dict, tenant: str) -> dict:
    """Render the persona invite into a Postmark email_data dict.

    `invitation` is the dict shape returned by create_persona_invitation. Raises
    UnknownPersonaError via get_persona_config if the persona is gone.
    """
    cfg = get_persona_config(tenant, invitation["persona_key"])
    tenant_cfg = get_tenant_config(tenant)
    tenant_mail = tenant_cfg.get("mail") or {}

    base_url = config.get("base_url", "https://edupersona.nl")
    accept_url = f"{base_url}/accept/p/{invitation['code']}"

    # sender resolution: invitation override > tenant default > hardcoded fallback
    from_email = invitation.get("sender_email") or tenant_mail.get("sender_email") or "noreply@edupersona.nl"
    from_name = invitation.get("sender_name") or tenant_mail.get("sender_name") or "eduPersona"

    context = {
        "accept_url": accept_url,
        "persona": cfg.display_name,
        "persona_params": invitation.get("persona_params") or {},
        "given_name": invitation.get("given_name"),
        "family_name": invitation.get("family_name"),
        "sender_name": from_name,
        "guest_email": invitation.get("invitation_email", ""),
    }

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    body_html = env.get_template(cfg.mail.body).render(**context)
    html_body = env.get_template(cfg.mail.layout).render(body_html=body_html, **context)

    return {
        "from_email": from_email,
        "from_name": from_name,
        "to_email": invitation.get("invitation_email", ""),
        "subject": f"Uitnodiging: {cfg.label('nl')}",
        "html_body": html_body,
        "text_body": html_to_text(html_body),
    }


async def send_persona_invitation(tenant: str, invitation: dict) -> bool:
    """Compose and send the persona invite via Postmark. Returns success bool."""
    email_data = await prepare_persona_invite_message(invitation, tenant)
    return await send_postmark_email(email_data)
