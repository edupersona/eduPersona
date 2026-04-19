"""
Internationalization (i18n) service for edupersona.

Provides a simple _() translation function that reads user language
from app.storage.user['language'], falling back to DEFAULT_LANGUAGE.

Source strings in code are 'en_gb'. Translations are stored in
Python dicts below for flexibility (multi-line, format strings, etc.).
"""
from nicegui import app

DEFAULT_LANGUAGE = 'nl_nl'

translations: dict[str, dict[str, str]] = {
    'nl_nl': {
        # General (used across multiple files)
        'Add': 'Toevoegen',
        'as': 'als',
        'Cancel': 'Annuleren',
        'Close': 'Sluiten',
        'Dates': 'data',
        'Delete': 'Verwijderen',
        'Edit': 'Bewerken',
        'Email': 'mail',
        'End': 'einde',
        'Error': 'Fout',
        'No': 'Nee',
        'Save': 'Opslaan',
        'Send': 'Versturen',
        'Start': 'start',
        'Status': 'status',
        'This action cannot be undone.': 'Deze actie kan niet ongedaan worden gemaakt.',
        'This field is required': 'Dit veld kan niet leeg blijven',
        'Updated': 'Bijgewerkt',
        'Welcome': 'Welkom',
        'Yes': 'Ja',

        # Landing & Navigation (routes/landing.py)
        'Accept a received invitation': 'Accepteer een ontvangen uitnodiging',
        'Accept invitation': 'Uitnodiging accepteren',
        'Accept an invitation': 'Accepteer een uitnodiging',
        'Access your apps': 'Jouw apps & diensten',
        'Note: you will need an eduID for this': 'Let op: eduID nodig voor toegang',
        'Management': 'Beheer',
        'Admin login': 'Log in als beheerder',
        'Manage roles and invitations': 'Rollen en uitnodigingen beheren',
        "Click here if you've received an invitation": 'Klik hier als je een uitnodiging hebt ontvangen',
        'Access your apps & services with eduID': 'Toegang naar je apps & diensten met eduID',
        'Login with eduID': 'Inloggen met eduID',

        # Apps page
        '{name}: Your Apps & Services': '{name}: applicaties & diensten',
        'You have unclaimed invitations for other roles — click here to accept': 'Je hebt nog uitnodigingen voor andere rollen open staan — klik hier',
        'active': 'actief',
        'starts later': 'toekomstig',

        # Login (routes/m/login.py)
        'Authentication failed': 'Authenticatie mislukt',
        'eduPersona management': 'eduPersona beheer',
        'Invalid username or password': 'Ongeldige gebruikersnaam of wachtwoord',
        'Local account': 'Lokaal account',
        'Login': 'Inloggen',
        'Login with SURFconext': 'Inloggen met SURFconext',
        'OIDC login failed': 'OIDC login mislukt',
        'password': 'wachtwoord',
        'Tenant': 'Tenant',
        'username': 'gebruikersnaam',
        'Username and password are required': 'Gebruikersnaam en wachtwoord zijn verplicht',

        # Roles (routes/m/roles.py)
        'active role(s)': 'actieve rol(len)',
        'Admin functions coming soon': 'Beheersautorisaties: in ontwikkeling',
        'Admins': 'beheerders',
        'All roles already assigned': 'Alle beschikbare rollen zijn al toegekend',
        'Application': 'applicatie',
        'Application name': 'applicatielink: naam',
        'Application name is required': 'applicatienaam is verplicht',
        'Application URL': 'applicatielink: url',
        'Application URL is required': 'applicatie URL is verplicht',
        'Are you sure you want to delete the role "{name}"?':
            'Weet je zeker dat je de rol "{name}" wilt verwijderen?',
        'Assign': 'Toekennen',
        'Assign "{name}" to Guest': 'Rol "{name}" toekennen aan gast',
        'Assign Role': 'Rol toekennen',
        'Assign Role to {name}': 'Rol toekennen aan {name}',
        'Assign Role...': 'Rol toekennen...',
        'Dates are updated': 'Start- en/of einddatum bijgewerkt',
        'days': 'dagen',
        'Default duration (days) (optional)': 'default looptijd vanaf start, in dagen (optioneel)',
        'Default start date (optional)': 'default startdatum (optioneel)',
        'Delete Role': 'Rol verwijderen',
        'Details': 'details',
        'Duration': 'looptijd',
        'e.g., Faculty of Physics & Mathematics': 'bijv. Faculteit Wis- & Natuurkunde',
        'e.g. Visiting Professor of Mathematics': 'bijv. Gastdocent Wiskunde',
        'e.g. visiting professor term II / 2026-2027': 'Bijv. Kunsteducatie III / 2026-2027 2e semester',
        'Edit dates for {role}': 'Start- en einddatum bewerken voor {role}',
        'Edit Role': 'Rol bewerken',
        'End date': 'einddatum',
        'Error creating role': 'Er is een fout opgetreden bij het aanmaken van de rol',
        'Error deleting role': 'Er is een fout opgetreden bij het verwijderen van rol',
        'Error updating role': 'Er is een fout opgetreden bij het bijwerken van rol',
        'Guests': 'gasten',
        'Name': 'naam',
        'New Role': 'Nieuwe Rol',
        'New Role...': 'Nieuwe rol...',
        'No role assignments': 'Geen rollen toegekend',
        'No roles found': 'Geen rollen gevonden',
        'Organization': 'organisatie',
        'Organization name': 'organisatienaam',
        'Organizational unit inviting the guest': 'het uitnodigende organisatieonderdeel',
        'Overall end date (optional)': 'default einddatum (optioneel)',
        'Revoke': 'Intrekken',
        'Revoke role "{role}"?': 'Rol "{role}" intrekken?',
        'Role': 'rol',
        'Role Assignments': 'toegekende rollen',
        'Role assigned': 'Rol is toegekend',
        'Role details (course, term, period, code)': 'details (vak, periode, cursuscode)',
        'Role has been revoked': 'Rol is ingetrokken',
        'Role name': 'rolnaam',
        'Role name is required': 'rolnaam is verplicht',
        'Role "{name}" has been created': 'rol "{name}" is aangemaakt',
        'Role "{name}" has been deleted': 'rol "{name}" is verwijderd',
        'Role "{name}" has been updated': 'rol "{name}" is bijgewerkt',
        'Roles': 'rollen',
        'Scope': 'scope',
        'Scope (who can use and manage this role)': 'scope (wie kan deze rol zien en gebruiken)',
        'Select a guest to see their role assignments': 'Selecteer een gast om toegekende rollen te zien',
        'Select a role': 'Selecteer een rol',
        'Select Guest': 'Selecteer een gast',
        'Start date': 'startdatum',
        'Synchronize': 'Synchroniseren',
        'This will remove the role assignment.': 'Deze gast verliest deze rol.',
        'View full role': 'Naar de rolpagina',
        'YYYY-MM-DD (optional)': 'YYYY-MM-DD (leeglaten als je de standaard-roldatum wilt gebruiken)',

        # Guests (routes/m/guests.py)
        'Add Guest...': 'Gast toevoegen...',
        'App': 'applicatie',
        'Attributes': 'Attributen',
        'Display name': 'display name',
        'Family name': 'achternaam',
        'Given name': 'voornaam',
        'Identity': 'identiteit',
        'Latest end date': 'laatste einddatum',
        'New Guest...': 'Nieuwe gast...',
        'No guests found': 'Geen gasten gevonden',
        'User ID': 'userid',
        'View full profile': 'Naar de gastpagina',

        # Invitations (routes/m/invitations.py)
        # status values: 'pending', 'invited', 'accepted', 'error'
        'accepted': 'geaccepteerd',
        'expired': 'verlopen',
        'pending': 'verstuurd',
        #
        'Accepted': 'geaccepteerd',
        'All fields are required': 'Alle velden zijn verplicht',
        'code': 'code',
        'Create Invitation': 'Uitnodiging aanmaken',
        'e.g., Carol Johnson': 'bijv. Ingrid Jansen',
        'e.g., Servicedesk': 'bijv. Servicedesk',
        'e.g., servicedesk@university.com': 'bijv. servicedesk@hvh_hogeschool.nl',
        'Email address': 'mailadres',
        'email address': 'mailadres',
        'Email for this invitation': 'het mailadres voor deze uitnodiging',
        'For more info, contact name (optional)': 'naam van contact voor meer info (optioneel)',
        'For more info, mail to (optional)': 'mailadres voor meer info (optioneel)',
        'Guest': 'gast',
        'Guest ID': 'userid',
        'Invitation details': 'Details van de uitnodiging',
        'Invitation email': 'uitnodiging (mail)',
        'Invitation sent': 'uitnodiging verstuurd',
        'Invited': 'uitgenodigd',
        'invited': 'uitgenodigd',
        "Invite sender's mail address": 'afzender van uitnodiging',
        'Mail Preview': 'Mail Preview',
        'New Invitation': 'Nieuwe uitnodiging',
        'New invitation...': 'Nieuwe uitnodiging...',
        'No invitations found.': 'Geen uitnodigingen gevonden',
        'No role assignments for this guest': 'Deze gast heeft nog geen rollen toegekend gekregen',
        'Optional': 'optioneel',
        'Personal message': 'persoonlijke aanvulling aan de mailtekst',
        'Or add a new role:': 'Of ken een nieuwe rol toe:',
        'Resend invitation email': 'uitnodiging opnieuw versturen',
        'Resend invitation': 'Opnieuw versturen',
        'role': 'rol',
        'Select Role': 'rol',
        'Select roles to include': 'Selecteer de rollen voor de uitnodiging',
        'Sender email': 'mailadres afzender',
        'Sender name': 'naam van afzender',
        'Subject': 'Onderwerp',
        'The mail address to send the invitation to': 'de uitnodiging wordt naar dit adres verstuurd',
        'To': 'Aan',
        'User identifier in our systems': 'interne userid in onze systemen',

        # Accept page & Step cards (routes/accept.py, components/step_cards.py)
        'Accept invitation  ▶︎': 'Uitnodiging accepteren  ▶︎',
        'Click here to log in to {app}': 'Klik hier om in te loggen op {app}',
        "Come back here after you've created it!": "Kom hier terug als je 'm hebt aangemaakt!",
        'Confirm code': 'Code bevestigen',
        'Create one here': 'Maak hem hier aan',
        'Enter your invitation code here': 'Voer hier uw uitnodigingscode in',
        'Follow the step-by-step plan below to accept your invitation{suffix}.':
            'Volg het stappenplan hieronder om je uitnodiging{suffix} te accepteren.',
        'Invalid invite code': 'Ongeldige uitnodigingscode',
        'Invalid invite code (role not found)': 'Ongeldige uitnodigingscode (rol niet gevonden)',
        'Invitation code': 'Uitnodigingscode',
        'Log in via test-IDP to verify your institutional identity.':
            'Log in via test-IDP om uw instellingsidentiteit te verifiëren.',
        'Login via (dummy) institution': 'Inloggen via (dummy) instelling',
        'Login with (test!) eduID': 'Inloggen met (test!) eduID',
        "No - I don't have a (test!) eduID yet": "Nee - ik heb nog geen (test!) eduID",
        'No test-eduID yet?': 'Nog geen test-eduID?',
        'View attributes': 'Bekijk attributen',
        'Welcome{suffix}': 'Welkom{suffix}',
        'YES! I already have a (test!) eduID': 'JA! Ik heb al een (test!) eduID',
        '✓ Your eduID is now linked!': '✓ Uw eduID is nu gekoppeld!',

        # SCIM Sync
        'Are you sure you want to continue?': 'Weet je zeker dat je wilt doorgaan?',
        'Guests: {count} synchronized': 'Guests: {count} gesynchroniseerd',
        'Memberships: {count} synchronized': 'Memberships: {count} gesynchroniseerd',
        'Roles: {count} synchronized': 'Roles: {count} gesynchroniseerd',
        'SCIM Sync': 'SCIM Sync',
        'SCIM sync completed!': 'SCIM sync voltooid!',
        'SCIM sync error': 'SCIM sync fout',
        'SCIM sync failed': 'SCIM sync mislukt',
        'SCIM Synchronization': 'SCIM Synchronisatie',
        'Synchronizing...': 'Bezig met synchroniseren...',
        'This will synchronize all existing guests, roles and memberships to the SCIM server.':
            'Dit zal alle bestaande guests, roles en memberships synchroniseren naar de SCIM server.',
    },
    'en_gb': {
        # Source language - empty dict, returns key as-is
    }
}


def _(key: str, lang: str | None = None, **kwargs) -> str:
    """
    Translate key to user's language.

    Reads language from app.storage.user['language'] unless lang is specified.
    Falls back to DEFAULT_LANGUAGE (nl_nl) if not set.

    Supports format strings via kwargs:
        _('Welcome as {suffix}', suffix='Guest')

    Args:
        key: The source text to translate (in en_gb)
        lang: Optional language override (e.g., for email templates)
        **kwargs: Format string parameters

    Returns:
        Translated string, or key if no translation found
    """
    if lang is None:
        try:
            lang = app.storage.user.get('language', DEFAULT_LANGUAGE)
        except (AttributeError, RuntimeError):
            # Not in a user context (startup, API call without session)
            lang = DEFAULT_LANGUAGE

    # Ensure lang is a string (for type checker)
    lang = str(lang) if lang else DEFAULT_LANGUAGE

    # Source language - return key as-is
    if lang == 'en_gb':
        result = key
    else:
        # Return translated string or fall back to key
        result = translations.get(lang, {}).get(key, key)

    # Apply format parameters if provided
    if kwargs:
        try:
            result = result.format(**kwargs)
        except KeyError:
            pass  # Ignore missing format keys

    return result
