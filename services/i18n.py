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
        # General (multiple appearances)
        'Continue': 'Doorgaan',
        'Email': 'mail',
        'Guest ID': 'guest_id',
        'Invitation parameters': 'Uitnodigingsgegevens',
        'Name': 'naam',
        'Persona': 'persona',

        # Collected-data confirmation modal (steps/collected_data.py)
        'Collected data (delivery via SCIM and/or callback)':
            'Verzamelde gegevens (levering via SCIM en/of callback)',
        'Close': 'Sluiten',
        'General information': 'Algemene gegevens',
        'Persona parameters': 'Persona-parameters',
        'No data collected.': 'Geen gegevens verzameld.',

        # Landing & Navigation (routes/landing.py)
        'Accept an invitation': 'Accepteer een uitnodiging',
        'Admin access': 'Toegang als beheerder',
        'Bridging eduID and institution identity': 'De brug tussen eduID en instellingsidentiteit',
        "Click here if you've received an invitation": 'Klik hier als je een uitnodiging hebt ontvangen',

        # Login (routes/m/login.py)
        'Authentication failed': 'Authenticatie mislukt',
        'eduPersona management': 'eduPersona beheer',
        'Invalid username or password': 'Ongeldige gebruikersnaam of wachtwoord',
        'Local account': 'Lokaal account',
        'Login': 'Inloggen',
        'Login with eduID': 'Inloggen met eduID',
        'Login with (test!) eduID': 'Inloggen met (test!) eduID',
        'Login with SURFconext': 'Inloggen met SURFconext',
        'password': 'wachtwoord',
        'Register for PoC access here': 'Zelf proberen? Registreer hier voor toegang naar de PoC-omgeving',
        'username': 'gebruikersnaam',
        'Username and password are required': 'Gebruikersnaam en wachtwoord zijn verplicht',

        # Invitations (routes/m/invitations.py) — lowercase entries are status values
        'Accepted': 'geaccepteerd',
        'accepted': 'geaccepteerd',
        'Accepted at': 'geaccepteerd op',
        'Code': 'code',
        'Email sent successfully!': 'Mail succesvol verstuurd!',
        'expired': 'verlopen',
        'Expires': 'verloopt',
        'Expires at': 'verloopt op',
        'Failed to send email': 'Versturen van mail mislukt',
        'Guest': 'gast',
        'Inputs': 'Inputs',
        'Invitation details': 'Details van de uitnodiging',
        'invited': 'uitgenodigd',
        'Invited': 'uitgenodigd',
        'Invited at': 'uitgenodigd op',
        'No collected facts.': 'Geen gegevens verzameld.',
        'No invitations found.': 'Geen uitnodigingen gevonden',
        'No parameters.': 'Geen parameters.',
        'Outputs': 'Outputs',
        'pending': 'verstuurd',
        'Resend': 'Opnieuw versturen',
        'Status': 'status',
        'Verified facts': 'Geverifieerde data',

        # Simulator (routes/m/simulator.py)
        'Callback URL': 'Callback URL',
        'Could not load persona defaults': 'Kon persona-standaardwaarden niet laden',
        'Could not load persona parameters': 'Kon persona-parameters niet laden',
        'Create invitation': 'Uitnodiging aanmaken',
        'Error': 'Fout',
        'Failed': 'Mislukt',
        'Family name': 'achternaam',
        'Given name': 'voornaam',
        'Guest data': 'Gastgegevens',
        'Invitation created': 'Uitnodiging aangemaakt',
        'Persona, email and Guest ID are required': 'Persona, mailadres en guest_id zijn verplicht',
        'Sender email': 'mailadres afzender',
        'Sender name': 'naam van afzender',

        # Accept page & Step cards (routes/accept.py, steps/)
        'Accept invitation': 'Uitnodiging accepteren',
        'as': 'als',
        'Could not start ID verification. Please try again later.': 'ID-verificatie kon niet worden gestart. Probeer het later opnieuw.',
        'Open verification on this device': 'Verifieer op dit apparaat',
        'Scan this QR code with your phone to start:': 'Scan deze QR-code met je telefoon om te beginnen:',
        'Try again': 'Opnieuw proberen',
        'Verification timed out. Please try again.': 'De verificatie is verlopen. Probeer het opnieuw.',
        "We'll continue automatically when you're done — keep this page open.": 'We gaan automatisch verder zodra je klaar bent — houd deze pagina open.',
        'Your verification needs manual review. Please contact the sender of your invitation.': 'Je verificatie moet handmatig worden beoordeeld. Neem contact op met de afzender van je uitnodiging.',
        'Change number / resend': 'Ander nummer / opnieuw versturen',
        "Come back here after you've created it!": "Kom hier terug als je 'm hebt aangemaakt!",
        'Confirm code': 'Code bevestigen',
        'Date of birth': 'Geboortedatum',
        'Enter a valid mobile number': 'Voer een geldig mobiel nummer in',
        'Enter code: {code}': 'Voer code in: {code}',
        'Enter your invitation code here': 'Voer hier uw uitnodigingscode in',
        'Five digits required': 'Vijf cijfers vereist',
        'Follow the step-by-step plan below to accept your invitation{suffix}.': 'Volg het stappenplan hieronder om je uitnodiging{suffix} te accepteren.',
        'Four digits required': 'Vier cijfers vereist',
        'Incorrect code — please try again.': 'Onjuiste code — probeer het opnieuw.',
        'Invalid invite code': 'Ongeldige uitnodigingscode',
        'Invitation code': 'Uitnodigingscode',
        'Mobile number': 'Mobiel nummer',
        "No - I don't have an eduID yet": 'Nee - ik heb nog geen eduID',
        "No - I don't have a (test!) eduID yet": 'Nee - ik heb nog geen (test!) eduID',
        'No matching alumni record found — check your details and try again.': 'Geen alumnigegevens gevonden — controleer je gegevens en probeer het opnieuw.',
        'Please contact the sender of your invitation.': 'Neem contact op met de afzender van je uitnodiging.',
        'Register': 'Registreren',
        # Verification gate (steps/base.py render_match_failed)
        "We couldn't verify that this matches your invitation.": 'We konden niet vaststellen dat dit overeenkomt met je uitnodiging.',
        '{label}: invitation shows “{expected}”, we found “{found}”.': '{label}: uitnodiging vermeldt “{expected}”, wij vonden “{found}”.',
        'If your details are wrong, contact the sender of your invitation.': 'Kloppen je gegevens niet? Neem contact op met de afzender van je uitnodiging.',
        'Start over': 'Opnieuw beginnen',
        'Authentication level': 'Authenticatieniveau',
        'Send code': 'Code versturen',
        'Student number': 'Studentnummer',
        'This invitation cannot be processed right now.': 'Deze uitnodiging kan op dit moment niet worden verwerkt.',
        'This invitation has expired.': 'Deze uitnodiging is verlopen.',
        'Verification code': 'Verificatiecode',
        'Verify': 'Verifiëren',
        'Verify alumni status': 'Controleer in alumnidatabase',
        'View attributes': 'Bekijk attributen',
        'Welcome': 'Welkom',
        'Welcome{suffix}': 'Welkom{suffix}',
        'YES! I already have a (test!) eduID': 'JA! Ik heb al een (test!) eduID',
        'YES! I already have an eduID': 'JA! Ik heb al een eduID',
        'Your onboarding has been completed successfully.': 'Je onboarding is succesvol afgerond.',

        # Registration (routes/register.py)
        'Could not start your registration — please try again later': 'Je registratie kon niet worden gestart — probeer het later opnieuw',
        'Could not send your invitation — please try again later': 'Je uitnodiging kon niet worden verstuurd — probeer het later opnieuw',
        'Email address': 'mailadres',
        'First name': 'voornaam',
        'Last name': 'achternaam',
        'Please fill in all fields with a valid email': 'Vul alle velden in met een geldig mailadres',
        'Register for PoC access': 'Registreer hier voor toegang naar de eduPersona PoC',
        'Send': 'Versturen',
        'Thank you!': 'Bedankt!',
        "We've sent you an invitation by e-mail. Open the link to onboard with your (test-)eduID and get access to this PoC environment.": 'We hebben je een uitnodiging gemaild. Open de link om je aan te melden met je (test-)eduID en toegang te krijgen tot deze PoC-omgeving.',
        "We've sent you an invitation by e-mail. Open the link to onboard with your eduID and get access to this PoC environment.": 'We hebben je een uitnodiging gemaild. Open de link om je aan te melden met je eduID en toegang te krijgen tot deze PoC-omgeving.',

        # Errors (services/ui_errors.py)
        'Something went wrong. Please try again.': 'Er is iets misgegaan. Probeer het opnieuw.',
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
