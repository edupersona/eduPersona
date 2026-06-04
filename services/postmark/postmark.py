"""Postmark email service (persona-mode).

Renders a per-persona body wrapped in a per-tenant layout (§6) and sends it via the
Postmark API. Sender identity resolves invitation-override > tenant default.
"""
import re
from html import unescape
from pathlib import Path

import httpx
from jinja2 import Environment, FileSystemLoader

from ng_rdm.utils import logger
from services.persona_loader import get_persona_config
from services.settings import config, get_tenant_config

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def html_to_text(html_content: str) -> str:
    """Convert HTML to plain text for the email's text alternative."""
    text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'<li>', '• ', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', r'\2 (\1)', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def prepare_invite_message(invitation: dict, tenant: str) -> dict:
    """Render the persona invite into a Postmark email_data dict.

    `invitation` is the dict shape returned by create_invitation. Raises
    UnknownPersonaError via get_persona_config if the persona is gone.
    """
    cfg = get_persona_config(tenant, invitation["persona_key"])
    tenant_mail = get_tenant_config(tenant).get("mail") or {}

    base_url = config.get("base_url", "https://edupersona.nl")
    accept_url = f"{base_url}/accept/{invitation['code']}"

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


async def send_postmark_email(email_data: dict) -> bool:
    """Send email via the Postmark API."""
    postmark_token = config.postmark.token
    message_stream = config.postmark.message_stream

    if not postmark_token:
        logger.error("Postmark token not configured in settings")
        return False

    postmark_data = {
        "From": f"{email_data['from_name']} <{email_data['from_email']}>",
        "To": email_data['to_email'],
        "Subject": email_data['subject'],
        "HtmlBody": email_data['html_body'],
        "TextBody": email_data['text_body'],
        "MessageStream": message_stream,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.postmarkapp.com/email",
                json=postmark_data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": postmark_token,
                },
            )
            if response.status_code == 200:
                logger.info(f"Postmark email sent. MessageID: {response.json().get('MessageID')}")
                return True
            logger.error(f"Postmark API error: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email via Postmark: {e}")
            return False


async def send_invitation_mail(tenant: str, invitation: dict) -> bool:
    """Compose and send the persona invite via Postmark. Returns success bool."""
    email_data = await prepare_invite_message(invitation, tenant)
    return await send_postmark_email(email_data)
