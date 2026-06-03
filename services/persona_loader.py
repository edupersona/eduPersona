"""Load and validate persona configs from per-tenant settings.

Personas live under `tenants.<t>.personas` in settings.json during the pivot
(Phase A–H). This module is the only place that turns that raw config into a
typed `PersonaConfig`, and the only place that validates client-supplied
`persona_params` against a persona's `expected_params` schema.

Both failure modes surface as `ValueError` subclasses so callers (Phase E API)
can map them: unknown persona → 404, params violation → 400.
"""

from typing import Any

from domain.persona import PersonaConfig
from services.settings import get_tenant_config


class UnknownPersonaError(ValueError):
    """Raised when a tenant has no persona under the requested key.

    Message is prefixed `"Unknown persona '"` so the API layer can map it to a
    404 NOT_FOUND without re-deriving the condition.
    """


class PersonaParamsError(ValueError):
    """Raised when client-supplied persona_params violate the persona's schema."""


def get_persona_config(tenant: str, key: str) -> PersonaConfig:
    """Resolve and validate the persona `key` for `tenant`.

    Raises UnknownPersonaError if absent, pydantic ValidationError if the stored
    config is malformed.
    """
    tc = get_tenant_config(tenant)
    personas = tc.get("personas") or {}
    if key not in personas:
        raise UnknownPersonaError(f"Unknown persona '{key}' for tenant '{tenant}'")
    # personas[key] is a DotDict (dict subclass); pydantic validates it as a mapping.
    return PersonaConfig.model_validate(dict(personas[key]))


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
