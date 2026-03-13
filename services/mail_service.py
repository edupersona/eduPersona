# services/mail_service.py
# not really sending mail yet...

from services.settings import get_tenant_config
from services.storage.storage import get_membership_store
from ng_loba.utils import logger


async def create_mail(tenant: str, invite_code: str):
    """Create mail content for invitation (returns mail object, no UI)"""
    logger.info(f"Mail service called for invitation: {invite_code}")

    membership_store = get_membership_store(tenant)
    memberships = await membership_store.read_items(
        filter_by={"code": invite_code},
        join_fields=["role__name"]
    )

    if not memberships:
        logger.error(f"No membership found for code: {invite_code}")
        return None

    membership = memberships[0]

    # Get role details from joined data
    role_name = membership.get('role__name', 'Onbekende rol')

    # Get base URL from tenant config (with fallback)
    tenant_config = get_tenant_config(tenant)
    base_url = tenant_config.get('base_url', 'https://edupersona.nl')

    # Build invitation URL with tenant in path
    accept_url = f"{base_url}/{tenant}/accept/{invite_code}"

    logger.info(
        f"Creating mail content for guest: {membership.get('guest')} to {membership.get('invitation_email')}")

    # Create mail content
    body = f"""Geachte collega,
    
U bent uitgenodigd als "{role_name}".

Klik op onderstaande link om de uitnodiging te accepteren:
<a href="{accept_url}">{accept_url}</a>

Of ga naar {base_url}/{tenant}/accept en kopieer en plak daar deze code:
    {invite_code}

Met vriendelijke groet,
ICT Ondersteuning
Universitaire PABO Universiteit van Amsterdam"""

    mail_content = {
        'to': membership.get('invitation_email', 'N/A'),
        'from': 'icto_upva_someone@uva.nl',
        'subject': f'Uitnodiging als {role_name} voor de Universiteit van Amsterdam',
        'body': body
    }

    logger.info(f"Mail content created for invitation: {invite_code}")
    return mail_content
