"""Load and validate persona configs from per-tenant settings.

Personas live under `tenants.<t>.personas` in settings.json during the pivot
(Phase A–H). This module is the only place that turns that raw config into a
typed `PersonaConfig`, and the only place that validates client-supplied
`persona_params` against a persona's `expected_params` schema.

Both failure modes surface as `ValueError` subclasses so callers (Phase E API)
can map them: unknown persona → 404, params violation → 400.
"""

from typing import Any

from pydantic import ValidationError

from domain.persona import ExpectedParam, MailRef, PersonaConfig
from services.settings import get_tenant_config

_PERSONA_KEYS = {
    "display_name", "steps", "mail", "success_redirect_url",
    "callback_url", "expected_params", "callback_outputs",
    "completion_message", "cta_label",
}


class UnknownPersonaError(ValueError):
    """Raised when a tenant has no persona under the requested key.

    Message is prefixed `"Unknown persona '"` so the API layer can map it to a
    404 NOT_FOUND without re-deriving the condition.
    """


class PersonaParamsError(ValueError):
    """Raised when client-supplied persona_params violate the persona's schema."""


def _build_persona_config(raw: dict) -> PersonaConfig:
    """Build a PersonaConfig from a raw settings dict, with explicit shape checks.

    Raises ValueError on any malformation (unknown/missing keys, bad expected_params)
    so the whole persona-load path raises one expected type — caught by the accept
    page's ui_guard and reported by the startup validator. No caching: the dataclass
    build is trivial, unlike the old per-request pydantic model_validate.
    """
    unknown = set(raw) - _PERSONA_KEYS
    if unknown:
        raise ValueError(f"unknown persona config key(s): {sorted(unknown)}")
    for req in ("display_name", "mail", "steps"):
        if req not in raw:
            raise ValueError(f"persona config missing required key '{req}'")
    mail = raw["mail"]
    if "layout" not in mail or "body" not in mail:
        raise ValueError("persona 'mail' config requires 'layout' and 'body'")
    try:
        expected = {k: ExpectedParam.model_validate(dict(v))
                    for k, v in (raw.get("expected_params") or {}).items()}
    except ValidationError as e:
        raise ValueError(f"invalid expected_params: {e}") from e
    return PersonaConfig(
        display_name=dict(raw["display_name"]),
        steps=[dict(s) for s in raw["steps"]],
        mail=MailRef(layout=mail["layout"], body=mail["body"]),
        success_redirect_url=raw.get("success_redirect_url"),
        callback_url=raw.get("callback_url"),
        expected_params=expected,
        callback_outputs=list(raw.get("callback_outputs") or []),
        completion_message=dict(raw.get("completion_message") or {}),
        cta_label=dict(raw.get("cta_label") or {}),
    )


def get_persona_config(tenant: str, key: str) -> PersonaConfig:
    """Resolve and validate the persona `key` for `tenant`.

    Raises UnknownPersonaError if absent, ValueError if the stored config is malformed.
    """
    tc = get_tenant_config(tenant)
    personas = tc.get("personas") or {}
    if key not in personas:
        raise UnknownPersonaError(f"Unknown persona '{key}' for tenant '{tenant}'")
    return _build_persona_config(dict(personas[key]))


def validate_persona_params(cfg: PersonaConfig, raw: dict | None) -> dict:
    """Validate + coerce raw persona_params against the persona's expected_params.

    Returns a new dict of coerced values (only keys actually supplied). No defaults
    are injected — a param the client omits simply isn't present (§2.2). Raises
    PersonaParamsError on unknown key, missing-required, or type/enum mismatch.
    """
    raw = raw or {}
    if not isinstance(raw, dict):
        raise PersonaParamsError("persona_params must be an object")

    for k in raw:
        if k not in cfg.expected_params:
            raise PersonaParamsError(f"Unknown persona_param '{k}'")

    out: dict[str, Any] = {}
    for name, spec in cfg.expected_params.items():
        if name in raw and raw[name] is not None:
            try:
                out[name] = spec.coerce(raw[name])
            except ValueError as e:
                raise PersonaParamsError(f"Invalid persona_param '{name}': {e}") from e
        elif spec.required:
            raise PersonaParamsError(f"Missing required persona_param '{name}'")
    return out


def validate_personas_or_raise() -> None:
    """Validate every tenant's persona configs at startup; fail fast on misconfig.

    Catches the "works until a guest clicks the link" class of errors at boot instead
    of as a runtime 500: persona shape (pydantic) and unknown-persona, per-step required
    config keys (by constructing the `Steps`), and missing mail templates. Raises a single
    `RuntimeError` listing every problem — the server must not start with broken config.
    """
    from jinja2 import Environment, FileSystemLoader
    from domain.step_cards import Steps
    from services.postmark.postmark import _TEMPLATE_DIR
    from services.settings import config

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    errors: list[str] = []
    for tenant in config.get("tenants", {}):
        personas = get_tenant_config(tenant).get("personas") or {}
        for key in personas:
            try:
                cfg = get_persona_config(tenant, key)     # shape + unknown persona
                Steps(tenant, {}, {"steps": cfg.steps})   # per-step required config keys
                env.get_template(cfg.mail.layout)         # mail templates resolve
                env.get_template(cfg.mail.body)
            except Exception as e:
                errors.append(f"  • tenant '{tenant}', persona '{key}': {type(e).__name__}: {e}")

    if errors:
        raise RuntimeError(
            "Invalid persona configuration (fix settings.json before startup):\n" + "\n".join(errors)
        )
