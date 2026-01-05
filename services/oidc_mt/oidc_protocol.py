"""
Pure OIDC client implementation.
Generic OIDC protocol functions with no application-specific logic.
"""

import base64
import hashlib
import os
import re
import urllib.parse
import httpx


def generate_pkce() -> tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge.

    Returns:
        tuple[code_verifier, code_challenge]
    """
    code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')
    code_verifier = re.sub('[^a-zA-Z0-9]+', '', code_verifier)
    code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8')
    code_challenge = code_challenge.replace('=', '')
    return code_verifier, code_challenge


def build_auth_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    scope: str = "openid profile email",
    acr_values: str | None = None,
    prompt: str | None = None,
    login_hint: str | None = None
) -> str:
    """
    Build OIDC authorization URL.

    Args:
        authorization_endpoint: OIDC authorization endpoint URL
        client_id: OAuth2 client ID
        redirect_uri: Callback URL
        code_challenge: PKCE code challenge
        scope: OAuth2 scopes
        acr_values: Authentication Context Class Reference values
        prompt: OIDC prompt parameter (e.g., 'login' to force re-authentication)
        login_hint: Login hint for directing authentication to specific identity provider

    Returns:
        Authorization URL
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    if acr_values:
        params["acr_values"] = acr_values

    if prompt:
        params["prompt"] = prompt

    if login_hint:
        params["login_hint"] = login_hint

    param_string = "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])  # type: ignore
    return f"{authorization_endpoint}?{param_string}"


def exchange_code(
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    code_verifier: str
) -> dict:
    """
    Exchange authorization code for access token.

    Args:
        token_endpoint: OIDC token endpoint URL
        client_id: OAuth2 client ID
        client_secret: OAuth2 client secret
        redirect_uri: Callback URL
        code: Authorization code
        code_verifier: PKCE code verifier

    Returns:
        Token response data

    Raises:
        httpx.HTTPStatusError: If token exchange fails
    """
    token_params = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'code_verifier': code_verifier,
    }

    response = httpx.post(token_endpoint, data=token_params)
    response.raise_for_status()
    return response.json()


def get_userinfo(userinfo_endpoint: str, token_data: dict) -> dict:
    """
    Get user information using access token.

    Args:
        userinfo_endpoint: OIDC userinfo endpoint URL
        token_data: Token response data from exchange_code()

    Returns:
        User information

    Raises:
        httpx.HTTPStatusError: If userinfo request fails
    """
    response = httpx.post(userinfo_endpoint, data=token_data)
    response.raise_for_status()
    return response.json()


def complete_oidc_flow(
    code: str,
    code_verifier: str,
    config: dict
) -> tuple[dict, dict, dict]:
    """
    Complete generic OIDC flow: exchange code for tokens and get userinfo.

    Args:
        code: Authorization code
        code_verifier: PKCE code verifier
        config: OIDC configuration

    Returns:
        tuple of (userinfo, id_token_claims, token_data)

    Raises:
        httpx.HTTPStatusError: If token exchange or userinfo request fails
    """
    import jwt

    # Exchange code for token
    token_data = exchange_code(
        token_endpoint=config['token_endpoint'],
        client_id=config['CLIENT_ID'],
        client_secret=config['CLIENT_SECRET'],
        redirect_uri=config['REDIRECT_URI'],
        code=code,
        code_verifier=code_verifier
    )

    # Decode ID token (without signature verification for now)
    id_token_claims = jwt.decode(token_data['id_token'], options={"verify_signature": False})

    # Get userinfo
    userinfo = get_userinfo(
        userinfo_endpoint=config['userinfo_endpoint'],
        token_data=token_data
    )

    return userinfo, id_token_claims, token_data


def load_well_known_config(well_known_url: str) -> dict:
    """
    Load OIDC configuration from .well-known endpoint.

    Args:
        well_known_url: .well-known/openid-configuration URL

    Returns:
        OIDC configuration

    Raises:
        httpx.HTTPStatusError: If config request fails
    """
    response = httpx.get(well_known_url)
    response.raise_for_status()
    return response.json()


def prepare_oidc_login(config: dict) -> tuple[str, str]:
    """
    Prepare OIDC login by generating PKCE parameters and building authorization URL.

    Args:
        config: OIDC configuration containing:
            - authorization_endpoint: OIDC authorization endpoint
            - CLIENT_ID: OAuth2 client ID
            - REDIRECT_URI: Callback URL
            - Optional: acr_values, force_login, login_hint

    Returns:
        tuple of (authorization_url, code_verifier)
    """
    code_verifier, code_challenge = generate_pkce()

    # Build authorization URL
    auth_url = build_auth_url(
        authorization_endpoint=config['authorization_endpoint'],
        client_id=config['CLIENT_ID'],
        redirect_uri=config['REDIRECT_URI'],
        code_challenge=code_challenge,
        acr_values=config.get('acr_values'),
        prompt="login" if config.get('force_login') else None,
        login_hint=config.get('login_hint'),
    )
    return auth_url, code_verifier
