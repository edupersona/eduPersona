"""/{tenant}/apps — returning-guest portal: eduID login, role-card list, pending invitations."""
from datetime import date

from nicegui import app, ui

from domain.stores import (
    get_invitation_store,
    get_role_assignment_store,
    get_role_store,
)
from ng_rdm.components import Button, Col, Row
from services.auth.guest_auth import create_guest_oidc_handler
from services.i18n import _
from services.oidc_mt.multitenant import start_oidc_login
from services.tenant import get_default_tenant
from services.theme import frame


def _session_tenant() -> str:
    """Tenant from session if set, else default."""
    return app.storage.user.get("tenant") or get_default_tenant()


def _is_guest_session() -> bool:
    return app.storage.user.get("authenticated", False) and app.storage.user.get("user_type") == "guest"


def _role_status(ra: dict) -> str:
    """Classify a role assignment as 'active', 'future', or 'expired' by today's date."""
    today = date.today()
    start = ra.get("start_date")
    end = ra.get("end_date")
    if start and isinstance(start, str):
        start = date.fromisoformat(start)
    if end and isinstance(end, str):
        end = date.fromisoformat(end)
    if end and today > end:
        return "expired"
    if start and today < start:
        return "future"
    return "active"


_STATUS_META = {
    "active": {"label_key": "active", "color": "positive"},
    "future": {"label_key": "starts later", "color": "warning"},
    "expired": {"label_key": "expired", "color": "grey"},
}


def _render_role_card(tenant: str, ra: dict, status: str) -> None:
    role = ra["role"]
    meta = _STATUS_META[status]
    clickable = status == "active" and bool(role.get("redirect_url"))

    # Wrap clickable cards in a native <a target="_blank"> so the click is a real
    # user-initiated navigation — avoids Safari's popup blocker that trips
    # ui.navigate.to(new_tab=True) after the WebSocket round-trip.
    wrapper = (
        ui.link(target=role["redirect_url"], new_tab=True).classes('role-card-link')
        if clickable
        else ui.element('div')
    )
    with wrapper:
        card = ui.card().classes('role-card')
        card.classes('role-card-clickable' if clickable else 'role-card-inactive')
        with card:
            logo = role.get('logo_file_name')
            if logo:
                ui.image(f'/static/{tenant}/logos/{logo}?v=2').classes('role-card-logo')
            with Col(classes='role-card-body'):
                ui.label(role.get('redirect_text') or role.get('name') or '-').classes('card-title')
                if role.get('org_name'):
                    ui.label(role['org_name'])
                if role.get('role_details'):
                    ui.label(role['role_details'])
            # TO DO: create Badge in ng_rdm...
            ui.badge(_(meta['label_key'])).props(f"color={meta['color']}").style('font-size: 1.3rem;')

@ui.page('/apps/no_account')
async def apps_no_account_page() -> None:
    """Shown when eduID login succeeds but no matching Guest exists (or onboarding wasn't completed)."""
    tenant = _session_tenant()

    with frame('no_account', tenant):
        with Col(classes='centered-content'):
            ui.label(_('No services found')).classes('section-heading')
            with ui.card().tight().classes('login-card login-card-wide'):
                ui.label(_("Your eduID has (not yet) been registered here. Have you received an invitation?")
                         ).classes('text')
                with Row().classes('button-row').style('margin-top: 1rem; gap: 0.75rem;'):
                    Button(_('Enter invitation code'),
                           on_click=lambda: ui.navigate.to('/accept'))
                    Button(_('Try a different eduID'), color='secondary',
                           on_click=lambda: ui.navigate.to('/apps?relogin=1'))


@ui.page('/apps')
async def apps_page(relogin: int = 0) -> None:
    """Guest portal: role-assignment cards (active / future / expired) + pending invitations."""
    tenant = _session_tenant()

    if relogin or not _is_guest_session():
        if app.storage.user.get("authenticated"):
            app.storage.user.clear()
        await start_oidc_login(
            tenant=tenant, idp="eduid",
            callback_handler=create_guest_oidc_handler(tenant),
            next_url="/apps", force_login=True,
        )
        return

    guest_id = app.storage.user.get("guest_id")
    ra_store = get_role_assignment_store(tenant)
    role_store = get_role_store(tenant)
    invitation_store = get_invitation_store(tenant)

    ras = await ra_store.read_items(filter_by={"guest_id": guest_id})
    for ra in ras:
        role = await role_store.read_item_by_id(ra["role_id"])
        if role:
            ra["role"] = role
    ras = [ra for ra in ras if ra.get("role")]

    buckets: dict[str, list[dict]] = {"active": [], "future": [], "expired": []}
    for ra in ras:
        buckets[_role_status(ra)].append(ra)

    pending = await invitation_store.read_items(filter_by={"guest_id": guest_id, "status": "pending"})

    with frame('apps', tenant):
        ui.label(_('{name}: Your Apps & Services',
                 name=app.storage.user.get("username", ""))).classes('page-title')

        for status in ['active', 'future', 'expired']:
            ras = buckets[status]
            for ra in ras:
                _render_role_card(tenant, ra, status)

        if pending:
            ui.link(
                _('You have unclaimed invitations for other roles — click here to accept'),
                '/accept',
            ).classes('apps-other-invites')

        ui.link(_('Click here to use a different eduID'), '/apps?relogin=1').classes('text')
