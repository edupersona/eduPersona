# /m/{tenant}/simulator — admin dogfoods the persona API by creating invitations.

import httpx
from fastapi import Depends
from nicegui import ui

from ng_rdm.utils import logger
from services.simulator_helpers import _default_for_spec, _persona_options, build_request_body
from services.auth.dependencies import require_invite_auth
from services.i18n import _
from services.persona_loader import get_persona_config
from services.settings import config, get_tenant_config
from services.theme import frame


@ui.page('/m/{tenant}/simulator')
async def simulator_page(tenant: str = Depends(require_invite_auth)):
    """Dynamic form bound to a persona's expected_params; submits over HTTP to the
    persona API (not an internal call) so it exercises the real ingress path."""
    options = _persona_options(tenant)
    tenant_cfg = get_tenant_config(tenant)
    tenant_mail = tenant_cfg.get("mail") or {}

    form: dict = {
        "persona_key": next(iter(options), None),
        "email": "", "given_name": "", "family_name": "", "client_ref": "",
        "sender_email": tenant_mail.get("sender_email", ""),
        "sender_name": tenant_mail.get("sender_name", ""),
        "callback_url": "",
        "persona_params": {},
    }

    def _load_persona_defaults() -> None:
        key = form["persona_key"]
        if not key:
            return
        cfg = get_persona_config(tenant, key)
        form["callback_url"] = cfg.callback_url or ""
        form["persona_params"] = {name: _default_for_spec(spec) for name, spec in cfg.expected_params.items()}

    _load_persona_defaults()

    with frame("simulator", tenant):
        ui.label(_("Guest simulator")).classes("page-title")

        with ui.column().classes("form-column").style("gap: 0.6rem; max-width: 30rem;"):
            persona_select = ui.select(options, label=_("Persona")) \
                .bind_value(form, "persona_key").classes("form-input")
            ui.input(_("Email"), placeholder="guest@example.org").bind_value(form, "email").classes("form-input")
            ui.input(_("Given name")).bind_value(form, "given_name").classes("form-input")
            ui.input(_("Family name")).bind_value(form, "family_name").classes("form-input")
            ui.input(_("Client reference")).bind_value(form, "client_ref").classes("form-input")
            ui.input(_("Sender email")).bind_value(form, "sender_email").classes("form-input")
            ui.input(_("Sender name")).bind_value(form, "sender_name").classes("form-input")
            ui.input(_("Callback URL")).bind_value(form, "callback_url").classes("form-input")

            @ui.refreshable
            def dynamic_fields() -> None:
                key = form["persona_key"]
                if not key:
                    return
                expected = get_persona_config(tenant, key).expected_params
                if expected:
                    ui.label(_("Persona parameters")).classes("text")
                for name, spec in expected.items():
                    label = name + (" *" if spec.required else "")
                    if spec.type == "bool":
                        ui.checkbox(label).bind_value(form["persona_params"], name)
                    elif spec.type == "int":
                        ui.number(label).bind_value(form["persona_params"], name).classes("form-input")
                    elif spec.type == "enum":
                        ui.select(spec.enum or [], label=label).bind_value(form["persona_params"], name).classes("form-input")
                    else:
                        ui.input(label).bind_value(form["persona_params"], name).classes("form-input")

            dynamic_fields()

            def _on_persona_change() -> None:
                _load_persona_defaults()
                dynamic_fields.refresh()

            persona_select.on_value_change(lambda _e: _on_persona_change())

            result = ui.column().classes("result-area")

            async def submit() -> None:
                if not form["persona_key"] or not (form["email"] or "").strip():
                    ui.notify(_("Persona and email are required"), type="negative")
                    return
                body = build_request_body(
                    persona_key=form["persona_key"], email=form["email"].strip(),
                    given_name=form["given_name"], family_name=form["family_name"],
                    client_ref=form["client_ref"], sender_email=form["sender_email"],
                    sender_name=form["sender_name"], callback_url=form["callback_url"],
                    persona_params=form["persona_params"],
                )
                base = config.get("base_url", "http://localhost:8080")
                headers = {"X-API-Key": tenant_cfg.get("api_key", "")}
                url = f"{base}/api/v1/{tenant}/persona-invitations"
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(url, json=body, headers=headers)
                except Exception as e:
                    logger.error(f"simulator submit failed: {e}")
                    ui.notify(f"{_('Error')}: {e}", type="negative")
                    return

                result.clear()
                with result:
                    if resp.status_code == 200:
                        accept_url = resp.json()["data"]["accept_url"]
                        ui.notify(_("Invitation created"), type="positive")
                        ui.link(accept_url, accept_url).props("target=_blank")
                    else:
                        ui.notify(f"{_('Failed')}: {resp.status_code}", type="negative")
                        ui.label(resp.text).classes("text")

            ui.button(_("Create invitation"), on_click=submit).style("margin-top: 0.5rem;")
