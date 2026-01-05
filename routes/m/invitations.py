# /invitations page

from fastapi import Depends
from nicegui import ui
from services.auth.dependencies import require_invite_auth
from services.storage import (
    create_invitation, find
)
from services.logging import logger
from services.mail_service import create_mail
from .nav_header import create_navigation_header

TITLE = "Uitnodigingen"

# Global reference for dialog management
current_dialog = None


@ui.refreshable
def invitations_table(page_state: dict):
    logger.info("Rendering invitations table")
    if not page_state['invitations']:
        ui.label('Geen uitnodigingen gevonden.').classes('text-gray-500 text-center py-8')
    else:
        with ui.card().classes('w-full').style('font-size: 12pt;'):
            # Table headers
            with ui.row().classes('w-full font-bold border-b py-2'):
                ui.label('groep').style('width:15%;')
                ui.label('mailadres').style('width:20%;')
                ui.label('code').style('width:25%;')
                ui.label('uitgenodigd').style('width:15%;')
                ui.label('geaccepteerd').style('width:15%;')

            # Table rows
            for membership in page_state['invitations']:
                group = membership.get("group", {})
                with ui.row().classes('w-full border-b py-2'):
                    ui.label(group.get("name", "") if group else "").style('width:15%;')
                    ui.label(membership.get("invitation_email", "")).style('width:20%;')
                    ui.label(membership["membership_id"]).style('width:25%;')
                    ui.label(membership["datetime_invited_formatted"]).style('width:15%;')
                    ui.label(membership["datetime_accepted_formatted"] or '-').style('width:15%;')


def manual_invite_dialog(page_state):
    """Show unified dialog with invitation form and mail preview"""
    logger.info("Opening invite dialog")

    # Initialize content mode for reactive binding inside dialog
    page_state['content_mode'] = 'invite'

    dialog_state = {
        'invitation_mail_address': '',
        'guest_id': '',
        'selected_group_id': ''
    }

    def create_and_send():
        # Validate and create invitation
        if not all([dialog_state['invitation_mail_address'].strip(),
                   dialog_state['guest_id'].strip(),
                   dialog_state['selected_group_id']]):
            ui.notify('Alle velden zijn verplicht', type='negative')
            return

        try:
            # Step 1: Close dialog first
            main_dialog.close()

            # Step 2: Create invitation
            invitation_id = create_invitation(
                dialog_state['guest_id'].strip(),
                dialog_state['selected_group_id'],
                dialog_state['invitation_mail_address'].strip()
            )

            # Step 3: Refresh data and table
            page_state['invitations'] = find("memberships", with_relations=["guest", "group"])
            invitations_table.refresh()

            # Step 4: Prepare mail content
            page_state['mail_content'] = create_mail(invitation_id)
            page_state['content_mode'] = 'mail_preview'

            # Step 5: Reopen dialog with mail preview
            ui.timer(0.1, lambda: main_dialog.open(), once=True)

        except Exception as e:
            logger.error(f"Failed to create invitation: {e}")
            ui.notify(f'Fout: {str(e)}', type='negative')

    def close_dialog():
        main_dialog.close()

    with ui.dialog().props('full-width') as main_dialog:
        # Invitation form
        with ui.card().style('width:760px !important;').bind_visibility_from(page_state, 'content_mode',
                                                                             backward=lambda x: x == 'invite'):
            ui.label('Nieuwe Uitnodiging').classes('text-xl font-bold mb-4')
            ui.input('Email adres', placeholder='gebruiker@example.com').bind_value(dialog_state,
                                                                                    'invitation_mail_address').classes('w-full mb-3')
            ui.input('Guest ID', placeholder='guest123').bind_value(dialog_state, 'guest_id').classes('w-full mb-3')

            group_options = {group['id']: group['name'] for group in page_state['groups']}
            if group_options:
                ui.select(options=group_options, label='Selecteer Groep', value=None).bind_value(
                    dialog_state, 'selected_group_id').classes('w-full mb-4')

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Annuleren', on_click=close_dialog).classes('bg-gray-500')
                ui.button('Versturen', on_click=create_and_send).classes('bg-blue-500')

        # Mail preview
        with ui.card().style('width: 960px !important;').bind_visibility_from(page_state, 'content_mode',
                                                                              backward=lambda x: x == 'mail_preview'):
            ui.label('Mail Preview').classes('text-xl font-bold mb-4')
            ui.label().bind_text_from(page_state, 'mail_content',
                                      backward=lambda x: f"Aan: {x['to']}" if x else '').classes('mb-2')
            ui.label().bind_text_from(page_state, 'mail_content',
                                      backward=lambda x: f"Onderwerp: {x['subject']}" if x else '').classes('mb-4')
            ui.label().bind_text_from(page_state, 'mail_content',
                                      backward=lambda x: x['body'] if x else '').classes('mb-4 whitespace-pre-line')
            ui.button('Sluiten', on_click=close_dialog).classes('bg-blue-500 w-full')

    # Imperatively open the dialog
    main_dialog.open()


@ui.page('/m/invitations')
def invitations_page(tenant: str = Depends(require_invite_auth)):
    logger.debug(f"invitations page accessed by tenant: {tenant}")

    ui.page_title(TITLE)

    page_state = {
        'invitations': find("memberships", with_relations=["guest", "group"]),
        'groups': find("groups"),
        'mail_content': None
    }

    with ui.column().classes('mx-auto p-6').style('width:1200px;'):
        create_navigation_header('invitations')

        invitations_table(page_state)
        ui.button('Nieuwe uitnodiging...', on_click=lambda: manual_invite_dialog(page_state)).classes('mb-4')

        # # Store reference to refresh function for later use
        # page_state['refresh_function'] = invitations_table.refresh
        # # Store reference to refresh function for later use
        # page_state['refresh_function'] = invitations_table.refresh
