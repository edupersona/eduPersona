"""Persona contract + loader.

Covers the typed persona config (domain/persona.py) and the loader/validator
(services/persona_loader.py): happy load, missing persona, persona_params
validation (required-missing, unknown-key, type coercion, enum bounds).

Pure unit tests — no DB, no UI, no event loop.
"""

import pytest
from pydantic import ValidationError

from domain.persona import ExpectedParam, MailRef, PersonaConfig
from services.persona_loader import (
    PersonaParamsError,
    UnknownPersonaError,
    get_persona_config,
    validate_persona_params,
)


def _cfg(**expected_params) -> PersonaConfig:
    """Minimal PersonaConfig for params-validation tests."""
    return PersonaConfig(
        display_name={"en": "Test"},
        steps=[],
        mail=MailRef(layout="layouts/hvh.jinja2", body="personas/test.jinja2"),
        expected_params=expected_params,
    )


# --- happy: load the real gastdocent persona from settings.json ---

def test_get_alumnus_persona():
    """Lock in the demo alumnus persona (eduid + verify_mobile + alumni_db outputs)."""
    cfg = get_persona_config("hvh", "alumnus")
    assert cfg.label("nl") == "Alumnus"
    assert [s["id"] for s in cfg.steps] == ["eduid_login", "verify_mobile", "alumni_db"]
    assert cfg.callback_outputs == ["eduid", "verify_mobile", "alumni_db"]
    assert cfg.cta("nl") == "Naar het alumniportaal"


def test_get_persona_config_happy():
    cfg = get_persona_config("hvh", "gastdocent")
    assert isinstance(cfg, PersonaConfig)
    assert cfg.display_name["nl"] == "Gastdocent"
    assert cfg.label("nl") == "Gastdocent"
    assert cfg.label("xx") == "Gastdocent"  # falls back to first defined name
    assert cfg.mail.layout == "layouts/hvh.jinja2"
    assert cfg.callback_outputs == ["eduid"]
    assert set(cfg.expected_params) == {"department", "personal_message"}
    assert cfg.expected_params["department"].type == "string"
    assert [s["id"] for s in cfg.steps] == [
        "eduid_login", "institutional_login",
    ]
    assert cfg.completion_text("nl").startswith("Je onboarding is voltooid")


# --- miss: unknown persona raises with the documented message prefix ---

def test_get_persona_config_unknown_raises():
    with pytest.raises(UnknownPersonaError) as exc:
        get_persona_config("hvh", "does_not_exist")
    assert str(exc.value).startswith("Unknown persona '")


# --- required-missing ---

def test_required_param_missing_raises():
    cfg = _cfg(department=ExpectedParam(type="string", required=True))
    with pytest.raises(PersonaParamsError, match="Missing required persona_param 'department'"):
        validate_persona_params(cfg, {})


def test_required_param_present_ok():
    cfg = _cfg(department=ExpectedParam(type="string", required=True))
    assert validate_persona_params(cfg, {"department": "CS"}) == {"department": "CS"}


# --- unknown-key ---

def test_unknown_param_key_raises():
    cfg = _cfg(department=ExpectedParam(type="string"))
    with pytest.raises(PersonaParamsError, match="Unknown persona_param 'bogus'"):
        validate_persona_params(cfg, {"bogus": "x"})


# --- omitted optional param is simply absent (no default injection) ---

def test_optional_param_omitted_not_in_output():
    cfg = _cfg(personal_message=ExpectedParam(type="string"))
    assert validate_persona_params(cfg, {}) == {}
    assert validate_persona_params(cfg, None) == {}


# --- type coercion ---

@pytest.mark.parametrize("raw,expected", [("hello", "hello"), (42, "42"), (True, "True")])
def test_coerce_string(raw, expected):
    assert ExpectedParam(type="string").coerce(raw) == expected


@pytest.mark.parametrize("raw,expected", [("42", 42), (42, 42), ("0", 0)])
def test_coerce_int_ok(raw, expected):
    assert ExpectedParam(type="int").coerce(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "1.5", True, None])
def test_coerce_int_bad(raw):
    with pytest.raises(ValueError):
        ExpectedParam(type="int").coerce(raw)


@pytest.mark.parametrize("raw,expected", [
    (True, True), (False, False), ("true", True), ("False", False),
    ("yes", True), ("no", False), (1, True), (0, False),
])
def test_coerce_bool_ok(raw, expected):
    assert ExpectedParam(type="bool").coerce(raw) is expected


def test_coerce_bool_bad():
    with pytest.raises(ValueError):
        ExpectedParam(type="bool").coerce("maybe")


def test_validate_coerces_through_loader():
    cfg = _cfg(
        department=ExpectedParam(type="string"),
        headcount=ExpectedParam(type="int"),
        remote=ExpectedParam(type="bool"),
    )
    out = validate_persona_params(cfg, {"department": "CS", "headcount": "3", "remote": "yes"})
    assert out == {"department": "CS", "headcount": 3, "remote": True}


def test_validate_bad_type_raises_params_error():
    cfg = _cfg(headcount=ExpectedParam(type="int"))
    with pytest.raises(PersonaParamsError, match="Invalid persona_param 'headcount'"):
        validate_persona_params(cfg, {"headcount": "lots"})


# --- enum bounds ---

def test_enum_param_accepts_member():
    cfg = _cfg(faculty=ExpectedParam(type="enum", enum=["science", "arts"]))
    assert validate_persona_params(cfg, {"faculty": "science"}) == {"faculty": "science"}


def test_enum_param_rejects_non_member():
    cfg = _cfg(faculty=ExpectedParam(type="enum", enum=["science", "arts"]))
    with pytest.raises(PersonaParamsError, match="Invalid persona_param 'faculty'"):
        validate_persona_params(cfg, {"faculty": "law"})


def test_enum_type_requires_values():
    with pytest.raises(ValidationError):
        ExpectedParam(type="enum")


def test_enum_values_only_for_enum_type():
    with pytest.raises(ValidationError):
        ExpectedParam(type="string", enum=["a"])


# --- contract: the loader rejects unknown config keys (typed contract, not a bag) ---

def test_loader_forbids_unknown_keys():
    from services.persona_loader import _build_persona_config

    with pytest.raises(ValueError, match="unknown persona config key"):
        _build_persona_config({
            "display_name": {"en": "X"},
            "steps": [],
            "mail": {"layout": "l", "body": "b"},
            "surprise": "nope",  # intentional: assert extra keys are rejected
        })
