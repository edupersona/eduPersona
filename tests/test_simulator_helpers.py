"""Pure simulator helpers (no UI).

Helpers live in services/ (not routes.m) so this top-level import doesn't pin a
@ui.page package and break NiceGUI per-test route re-registration.
"""

from domain.persona import ExpectedParam
from services.simulator_helpers import _default_for_spec, _persona_options, build_request_body


def test_build_request_body_minimal():
    body = build_request_body(persona_key="gastdocent", email="a@example.org", guest_id="EMP-1")
    assert body == {"persona_key": "gastdocent", "email": "a@example.org", "guest_id": "EMP-1"}


def test_build_request_body_strips_empty_optionals():
    body = build_request_body(
        persona_key="gastdocent", email="a@example.org",
        given_name="", family_name=None, guest_id="EMP-1",
    )
    assert "given_name" not in body
    assert "family_name" not in body
    assert body["guest_id"] == "EMP-1"


def test_build_request_body_includes_names_when_present():
    body = build_request_body(
        persona_key="gastdocent", email="a@example.org", guest_id="EMP-1",
        given_name="Anna", family_name="Verver",
    )
    assert body["given_name"] == "Anna"
    assert body["family_name"] == "Verver"


def test_build_request_body_drops_empty_persona_params():
    body = build_request_body(
        persona_key="gastdocent", email="a@example.org", guest_id="EMP-1",
        persona_params={"department": "", "personal_message": None},
    )
    assert "persona_params" not in body


def test_build_request_body_keeps_nonempty_persona_params():
    body = build_request_body(
        persona_key="gastdocent", email="a@example.org", guest_id="EMP-1",
        persona_params={"department": "CS", "personal_message": ""},
    )
    assert body["persona_params"] == {"department": "CS"}


def test_persona_options(test_tenant):
    assert _persona_options(test_tenant) == {"gastdocent": "Gastdocent", "alumnus": "Alumnus"}


def test_default_for_spec_typed():
    assert _default_for_spec(ExpectedParam(type="string")) == ""
    assert _default_for_spec(ExpectedParam(type="int")) is None
    assert _default_for_spec(ExpectedParam(type="bool")) is False
    assert _default_for_spec(ExpectedParam(type="enum", enum=["a", "b"])) == "a"
