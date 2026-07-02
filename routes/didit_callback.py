# /didit_callback route: return redirect from Didit's hosted verification flow.
#
# Front-channel: the user's browser lands here after finishing at Didit. We resolve the
# transaction from the pending registry (the SOLE source of tenant + session_id — query
# params are never trusted), poll the decision, hand it to the bound card handler, and
# redirect back to /accept/{code}. Mirrors services/oidc_mt/oidc_callback.py.

from nicegui import app, ui

from ng_rdm.utils import logger

from services.didit import consume_pending_state, get_decision
from services.i18n import _


@ui.page('/didit_callback')
async def didit_callback(state: str = "") -> None:
    ui.add_css('static/css/base.css')
    ui.page_title('eduPersona')

    with ui.column().classes('status-page'):
        ui.label(_('Processing your verification...')).classes('section-heading')
        ui.spinner(size='lg')
        try:
            await ui.context.client.connected()
            # CSRF + isolation: state must be bound to THIS browser and still live in the
            # registry. The entry carries tenant + session_id; nothing is read from the URL.
            entry = consume_pending_state(app.storage.user.get('didit_pending_states', []), state)
            if entry is None:
                raise ValueError("no matching didit state — session may have expired or is invalid")

            decision = await get_decision(entry['tenant'], entry['session_id'])
            await entry['callback_handler'](decision)  # records complete()/fail() on the card
            ui.navigate.to(entry['next_url'])
        except Exception as e:
            logger.error(f"Didit callback failed: {e}")
            ui.label(_('Your verification could not be processed.')).classes('section-heading text-error')
            ui.button(_('Back'), on_click=lambda: ui.navigate.to('/')).classes('btn-primary')
