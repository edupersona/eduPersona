"""Reusable 'Collected data' receipt modal (Verzamelde gegevens).

Shown after a completed onboarding to surface exactly what edupersona delivers via
SCIM and/or the callback — the PoC stand-in for a real listener, which prod would
remove/disable. One accordion per data source/segment, mirroring the step cards.
Also drives the dev preview button on /accept.

Built ONCE per page — Dialog attaches its backdrop to the client root layout, so
rebuilding it inside a refreshable would leak backdrops; call open(segments) to
(re)populate and show. Purely informational: the footer button, header ×, and ESC
all just close it.
"""
from nicegui import html, ui

from ng_rdm.components import Button, Dialog

from services.i18n import _

Segments = list[tuple[str, dict]]


def _render_kv(data: dict) -> None:
    """Two-column key→value grid (reuses .facts-dialog styling)."""
    with html.div().classes('facts-kv'):
        for key, value in data.items():
            ui.label(str(key)).classes('facts-kv-key')
            ui.label('' if value is None else str(value)).classes('facts-kv-val')


class CollectedDataModal:
    """Large accordion modal listing all data delivered via SCIM and/or callback."""

    def __init__(self, close_label: str = 'Close') -> None:
        self._segments: Segments = []
        self.dlg = Dialog(title=_('Collected data (delivery via SCIM and/or callback)'),
                          dialog_class='panel-dialog facts-dialog collected-dialog')
        with self.dlg:
            self._body()
            with self.dlg.actions():
                Button(_(close_label), on_click=self.dlg.close).classes('step-primary-button')

    @ui.refreshable
    def _body(self) -> None:
        if not self._segments:
            ui.label(_('No data collected.')).classes('rdm-detail-text-sm')
            return
        for title, data in self._segments:
            with ui.expansion(title, icon='info').classes('collected-expansion'):
                _render_kv(data)

    def open(self, segments: Segments) -> None:
        self._segments = segments
        self._body.refresh()
        self.dlg.open()
