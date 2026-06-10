"""UI error-handling helper.

Convention: a runtime error with a UI aspect is logged and surfaced via
`ui.notify` (or `RdmComponent._notify` inside ng_rdm components) — never raised into
the global 500 page (services/exception_handlers.py), which in prod emails the admins.
Hard `raise` is reserved for config/schema validation and the API layer (translated to
REST via `api_error`). `ui_guard` is the seam that restores that discipline at the few
`@ui.page` call sites that invoke shared domain functions which raise for the API.
"""
from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from ng_rdm.utils import logger
from services.i18n import _


@contextmanager
def ui_guard(
    message: str | None = None,
    *,
    catch: type[Exception] | tuple[type[Exception], ...] = ValueError,
    notify: bool = True,
) -> Iterator[None]:
    """Guard a block of UI work against EXPECTED runtime errors.

    Logs the exception and (optionally) `ui.notify`s a friendly message instead of letting
    it escalate to the global 500 page + admin email. Catches `catch` only (default
    `ValueError`, which covers the persona/param/step-class domain errors) so genuine bugs
    still reach the 500 boundary. Pydantic `ValidationError` (malformed config) is not a
    `ValueError`, so it deliberately escalates. Pass `notify=False` where the caller renders
    its own fallback.
    """
    try:
        yield
    except catch as e:
        logger.error(f"ui_guard caught: {e}")
        if notify:
            ui.notify(message or _("Something went wrong. Please try again."), type="negative")
