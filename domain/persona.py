"""Persona contract — the typed, code-level definition of "what a persona is".

A persona is the *kind* of guest (visiting lecturer, alumnus, …). It owns only
what makes one persona differ from another: which onboarding steps run, the mail
templates, optional post-success redirect, the param schema a client may pass,
and which step outputs surface in the callback envelope. Authorization, validity
windows and deprovisioning live in the client app's IAM/IGA — never here.

This module is the source of truth for the persona shape. `services/persona_loader.py`
loads/validates instances from per-tenant settings; the API and accept flow consume
`PersonaConfig` instances, not raw dicts.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

# A callback-output key: either an IdP name (e.g. "eduid") for OIDC steps or a
# step id for non-OIDC steps. Always a plain string; documented as its own name
# so callers read intent, not just `str`.
CallbackOutputKey = str

ParamType = Literal["string", "int", "bool", "enum"]


class ExpectedParam(BaseModel):
    """Schema for one client-supplied `persona_param`.

    The client app may pass extra context at invite time (department, a personal
    message, …). Each declared param has a type used to coerce/validate the raw
    value once, at API ingress. `enum` lists the allowed values for `type="enum"`.
    """

    model_config = ConfigDict(extra="forbid")

    type: ParamType
    required: bool = False
    enum: list[str] | None = None

    @model_validator(mode="after")
    def _enum_present_when_typed(self) -> "ExpectedParam":
        if self.type == "enum" and not self.enum:
            raise ValueError("expected_param of type 'enum' must declare a non-empty 'enum' list")
        if self.type != "enum" and self.enum is not None:
            raise ValueError("'enum' is only valid for type 'enum'")
        return self

    def coerce(self, value: Any) -> Any:
        """Coerce a raw value to this param's type. Raises ValueError on mismatch."""
        if self.type == "string":
            return str(value)
        if self.type == "int":
            # bool is an int subclass; reject so True doesn't silently become 1.
            if isinstance(value, bool):
                raise ValueError(f"expected int, got bool {value!r}")
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValueError(f"expected int, got {value!r}")
        if self.type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return bool(value)
            s = str(value).strip().lower()
            if s in ("true", "1", "yes", "on"):
                return True
            if s in ("false", "0", "no", "off", ""):
                return False
            raise ValueError(f"expected bool, got {value!r}")
        if self.type == "enum":
            sv = str(value)
            if self.enum is not None and sv not in self.enum:
                raise ValueError(f"value {sv!r} not in {self.enum}")
            return sv
        raise ValueError(f"unknown param type {self.type!r}")  # unreachable; Literal guards it


@dataclass(frozen=True)
class MailRef:
    """References to the per-tenant layout frame and per-persona body template."""

    layout: str
    body: str


@dataclass(frozen=True)
class PersonaConfig:
    """The full persona definition (one entry under a tenant's `personas`).

    A plain dataclass, not a pydantic model: the persona config is developer-authored
    settings, and its correctness is enforced at startup by
    `services.persona_loader.validate_personas_or_raise` (which builds the real `Steps`
    and resolves templates — covering the variant `steps` a schema can't model). Only
    `ExpectedParam` stays pydantic, because that schema validates *incoming client*
    `persona_params` at the API boundary. The loader builds these instances via
    `_build_persona_config`, which does the shape checks (required + unknown keys).
    """

    display_name: dict[str, str]
    # `steps` array — raw step dicts; the step-card framework owns their inner shape.
    steps: list[dict[str, Any]]
    mail: MailRef
    success_redirect_url: str | None = None
    callback_url: str | None = None
    expected_params: dict[str, ExpectedParam] = field(default_factory=dict)
    callback_outputs: list[CallbackOutputKey] = field(default_factory=list)

    def label(self, lang: str = "nl") -> str:
        """Display label for a language, falling back to any defined name then key-less '?'."""
        return self.display_name.get(lang) or next(iter(self.display_name.values()), "?")
