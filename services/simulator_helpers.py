"""Pure helpers for the simulator page.

Lives under `services` (a namespace package with no @ui.page side effects) rather
than under `routes.m`: importing anything from `routes.m` runs its __init__ and
registers @ui.page routes, which pins `routes.m` in sys.modules and breaks NiceGUI
per-test route re-registration (gotcha 2). Keeping these here lets the unit tests
import them at top level safely.
"""
from typing import Any

from domain.persona import ExpectedParam
from services.persona_loader import get_persona_config
from services.settings import get_tenant_config


def _persona_options(tenant: str) -> dict[str, str]:
    """{persona_key: display label} for a tenant's personas (label = nl name, fallback key)."""
    personas = get_tenant_config(tenant).get("personas") or {}
    options: dict[str, str] = {}
    for key in personas:
        try:
            options[key] = get_persona_config(tenant, key).label("nl")
        except Exception:
            options[key] = key
    return options


def _default_for_spec(spec: ExpectedParam) -> Any:
    """Typed default value for an expected_param input widget."""
    if spec.type == "bool":
        return False
    if spec.type == "int":
        return None
    if spec.type == "enum":
        return (spec.enum or [None])[0]
    return ""  # string


def build_request_body(
    *,
    persona_key: str,
    email: str,
    guest_id: str,
    given_name: str | None = None,
    family_name: str | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
    callback_url: str | None = None,
    persona_params: dict | None = None,
) -> dict:
    """Assemble the POST /persona-invitations body, stripping empty optionals.

    persona_key, email and guest_id are always present; other top-level fields are
    included only when non-empty; persona_params drops empty values and is omitted
    entirely when nothing remains.
    """
    body: dict[str, Any] = {"persona_key": persona_key, "email": email, "guest_id": guest_id}
    optionals = {
        "given_name": given_name,
        "family_name": family_name,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "callback_url": callback_url,
    }
    for field, value in optionals.items():
        if value not in (None, ""):
            body[field] = value

    cleaned = {k: v for k, v in (persona_params or {}).items() if v not in (None, "")}
    if cleaned:
        body["persona_params"] = cleaned
    return body
