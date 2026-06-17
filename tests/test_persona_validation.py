"""Startup persona-config validation (fail fast on misconfig).

A missing mandatory step-config key must surface as a clear `ValueError` at construction
(so the accept page's ui_guard degrades gracefully) and be caught by the startup validator
(so the server refuses to boot with broken config) rather than as a guest-facing 500.
"""
import pytest

import services.persona_loader as pl
from steps import Steps


def test_missing_step_config_key_raises_clear_valueerror():
    """OIDCLoginStep without its required `idp` → ValueError naming the key (not KeyError)."""
    steps_cfg = {"steps": [{
        "class": "OIDCLoginStep", "id": "eduid_login",
        "config": {"title": "t", "completed_text": "c"},  # no idp
    }]}
    with pytest.raises(ValueError, match="idp"):
        Steps("hvh", {}, steps_cfg)


def test_validate_personas_passes_on_real_config():
    """The shipped settings.json personas all construct + resolve their mail templates."""
    pl.validate_personas_or_raise()


def test_validate_personas_aggregates_and_raises(monkeypatch):
    """Any broken persona → a single RuntimeError at startup."""
    def boom(tenant, key):
        raise pl.UnknownPersonaError("nope")

    monkeypatch.setattr(pl, "get_persona_config", boom)
    with pytest.raises(RuntimeError, match="Invalid persona configuration"):
        pl.validate_personas_or_raise()
