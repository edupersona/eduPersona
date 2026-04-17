"""
Postmark email service for sending invitations using HTML templates.
"""
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from html import unescape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import httpx

from services.settings import config
from ng_rdm.utils import logger


def map_invitation_context(invitation: dict, base_url: str) -> dict:
    """Build template context from invitation with role assignments."""
    context = invitation.copy()
    roles = [ra.get("role", {}) for ra in invitation.get("role_assignments", [])]

    context["tenant__HR"] = "UvA" if invitation.get('tenant') == 'uva' else ""
    context["accept_url"] = f"{base_url}/{invitation['tenant']}/accept/{invitation['code']}"

    # Role names for display
    role_names = [r.get("name", "") for r in roles if r.get("name")]
    context["role_names_string"] = " en ".join(role_names) if role_names else "toegang"
    context["title"] = f"Uitnodiging voor {context['role_names_string']}"
    first_name = role_names[0] if role_names else ""
    context["role__name__LC"] = first_name[:1].lower() + first_name[1:] if first_name else ""

    # Role details for template loop
    context["role_details_list"] = [
        {"name": ra.get("role", {}).get("name", ""),
         "role_details": ra.get("role", {}).get("role_details", ""),
         "org_name": ra.get("role", {}).get("org_name", ""),
         "start_date": ra.get("start_date", ""),
         "end_date": ra.get("end_date", "")}
        for ra in invitation.get("role_assignments", [])
    ]

    # First role for sender info
    first_role = roles[0] if roles else {}
    context["role__mail_sender_name"] = first_role.get("mail_sender_name", "")
    context["role__mail_sender_email"] = first_role.get("mail_sender_email", "noreply@edupersona.nl")
    context["role__org_name"] = first_role.get("org_name", "")
    context["role__name"] = first_role.get("name", "")
    context["role__role_details"] = first_role.get("role_details", "")

    return context


def html_to_text(html_content: str) -> str:
    """Convert HTML to plain text for email body."""
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


async def prepare_invite_message(invitation: dict, base_url: str | None = None) -> dict:
    """Prepare invitation email content from invitation with role assignments.

    Args:
        invitation: Invitation dict from get_invitation_with_roles() with:
                   - invitation fields (code, tenant, personal_message, invitation_email, etc.)
                   - role_assignments list, each containing 'role' dict with role details
        base_url: Base URL for the application. If None, uses config.base_url

    Returns:
        Dict with email fields: from_email, from_name, to_email, subject, html_body, text_body
    """
    if base_url is None:
        base_url = config.get('base_url', 'https://edupersona.nl')

    assert base_url
    context = map_invitation_context(invitation, base_url)

    template_dir = Path(__file__).parent / 'templates'
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('uva_jinja2.html')
    html_body = template.render(**context)

    # Plain text with role list
    role_lines = "\n".join(f"• {rd['name']}" for rd in context.get("role_details_list", []))
    pm_block = f"\nBericht van {context.get('role__mail_sender_name', '')}:\n{context.get('personal_message', '')}\n" if context.get(
        'personal_message') else ""

    text_body = f"""Hoi {context.get('guest__given_name') or invitation.get('guest__given_name', 'Collega')},

{context.get('role__mail_sender_name', '')} (van {context.get('role__org_name', '')}) wil je toegang geven tot:
{role_lines}
{pm_block}
Als je de link hieronder volgt word je doorverwezen naar eduPersona, waar je door de stappen wordt geleid om de uitnodiging te accepteren.

Accepteer uitnodiging: {context['accept_url']}

of kopieer deze link in je browser:
{context['accept_url']}
""".strip()

    return {
        "from_email": context.get("role__mail_sender_email", "noreply@edupersona.nl"),
        "from_name": context.get("role__mail_sender_name", "eduPersona"),
        "to_email": invitation.get("invitation_email", ""),
        "subject": f"Uitnodiging voor {context.get('role_names_string', 'toegang')} bij {context.get('role__org_name', 'uw organisatie')}",
        "html_body": html_body,
        "text_body": text_body
    }


async def send_postmark_email(email_data: dict) -> bool:
    """Send email via Postmark API."""
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
        "MessageStream": message_stream
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.postmarkapp.com/email",
                json=postmark_data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": postmark_token
                }
            )
            if response.status_code == 200:
                logger.info(f"Postmark email sent. MessageID: {response.json().get('MessageID')}")
                return True
            else:
                logger.error(f"Postmark API error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send email via Postmark: {e}")
            return False


async def send_postmark_invitation(tenant: str, code: str | None = None) -> bool:
    """Send an invitation email via Postmark API.

    Args:
        tenant: Tenant identifier
        code: Invitation code. If None, sends first pending invitation.

    Returns:
        True if email was sent successfully
    """
    from domain.invitations import get_invitation_with_roles
    from domain.stores import get_invitation_store

    logger.info(f"Sending Postmark invitation for tenant: {tenant}")

    if code:
        invitation = await get_invitation_with_roles(tenant, code)
    else:
        # Get first pending invitation
        store = get_invitation_store(tenant)
        invitations = await store.read_items(filter_by={"status": "pending"})
        if not invitations:
            logger.error(f"No pending invitations for tenant {tenant}")
            return False
        invitation = await get_invitation_with_roles(tenant, invitations[0]["code"])

    if not invitation:
        logger.error(f"Invitation not found for tenant {tenant}" + (f" with code {code}" if code else ""))
        return False

    invitation['tenant'] = tenant
    logger.info(f"Found invitation: {invitation.get('code')} for {invitation.get('invitation_email')}")

    email_data = await prepare_invite_message(invitation)
    success = await send_postmark_email(email_data)

    if success:
        logger.info("Postmark invitation email sent successfully!")
    else:
        logger.error("Failed to send Postmark invitation email")

    return success


async def send_test_invitation(tenant: str, code: str) -> bool:
    """Send a test invitation email via SMTP."""
    from domain.invitations import get_invitation_with_roles
    from services.smtp_mail import sendmail_async

    logger.info(f"Starting test invitation email for tenant: {tenant}")

    invitation = await get_invitation_with_roles(tenant, code)
    if not invitation:
        logger.error(f"Invitation not found for code {code}")
        return False

    invitation['tenant'] = tenant
    email_data = await prepare_invite_message(invitation)

    msg = MIMEMultipart('alternative')
    msg['From'] = f"{email_data['from_name']} <{email_data['from_email']}>"
    msg['To'] = email_data['to_email']
    msg['Subject'] = email_data['subject']
    msg.attach(MIMEText(email_data['text_body'], 'plain'))
    msg.attach(MIMEText(email_data['html_body'], 'html'))

    logger.info(f"Sending test email from {email_data['from_email']} to {email_data['to_email']}")
    success = await sendmail_async(
        from_address=email_data['from_email'],
        recipients=email_data['to_email'],
        subject=email_data['subject'],
        body=email_data['text_body']
    )

    if success:
        logger.info("Test invitation email sent successfully!")
    else:
        logger.error("Failed to send test invitation email")
    return success


async def test_template(tenant: str = "uva") -> bool:
    """Generate test HTML and text files from the first invitation in the database."""
    from domain.stores import get_invitation_store
    from domain.invitations import get_invitation_with_roles

    logger.info(f"Generating test template files for tenant: {tenant}")

    store = get_invitation_store(tenant)
    invitations = await store.read_items()
    if not invitations:
        logger.error(f"No invitations found for tenant {tenant}")
        return False

    invitation = await get_invitation_with_roles(tenant, invitations[0]["code"])
    if not invitation:
        logger.error("Could not load invitation with roles")
        return False

    invitation['tenant'] = tenant
    email_data = await prepare_invite_message(invitation)

    static_dir = Path(__file__).parent.parent.parent / 'static'
    static_dir.mkdir(exist_ok=True)

    try:
        (static_dir / 'test_output.html').write_text(email_data['html_body'], encoding='utf-8')
        (static_dir / 'test_output.txt').write_text(email_data['text_body'], encoding='utf-8')
        logger.info(f"From: {email_data['from_name']} <{email_data['from_email']}>")
        logger.info(f"To: {email_data['to_email']}")
        logger.info(f"Subject: {email_data['subject']}")
        return True
    except Exception as e:
        logger.error(f"Failed to write test files: {e}")
        return False
