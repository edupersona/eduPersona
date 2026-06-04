"""ui_guard contract: suppress EXPECTED (caught) exceptions, propagate the rest.

The UI error-handling discipline (log + notify, never 500) hinges on this helper, so
pin its catch semantics. notify=False keeps these free of a NiceGUI client context.
"""
import httpx
import jinja2
import pytest

from services.persona_loader import PersonaParamsError, UnknownPersonaError
from services.ui_errors import ui_guard


def test_suppresses_default_valueerror_subclasses():
    # default catch=ValueError covers the persona/param domain errors
    with ui_guard(notify=False):
        raise UnknownPersonaError("gone")
    with ui_guard(notify=False):
        raise PersonaParamsError("bad")
    # reaching here means both were suppressed


def test_propagates_uncaught_so_real_bugs_still_500():
    with pytest.raises(KeyError):
        with ui_guard(notify=False, catch=ValueError):
            raise KeyError("genuine bug")


def test_widened_catch_tuple_for_resend():
    # the do_resend site widens to transport + template errors
    catch = (ValueError, jinja2.TemplateError, httpx.HTTPError)
    for exc in (UnknownPersonaError("x"), jinja2.TemplateNotFound("t"), httpx.HTTPError("h")):
        with ui_guard(notify=False, catch=catch):
            raise exc
    # all three suppressed
