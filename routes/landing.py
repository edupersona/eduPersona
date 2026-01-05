from nicegui import ui
from services.logging import logger

@ui.page('/')
def landing_page():
    logger.debug("Landing page accessed")

    ui.page_title('eduPersona')

    # Main container with centered content
    with ui.column().classes('w-full min-h-screen bg-gray-50'):
        # Content wrapper
        with ui.column().classes('mx-auto p-8'):

            # Choice cards
            with ui.row().classes('w-full gap-4 justify-center'):
                ui.image('/img/edupersona.png').style('width: 150px;')

                # Accept invitation card
                with ui.card().classes('p-8 hover:shadow-xl transition-shadow cursor-pointer').style('width: 450px') as accept_card:
                    with ui.column().classes('gap-2'):
                        ui.icon('mail_outline', size='3em').classes('text-green-600')
                        ui.label('Uitnodiging accepteren').classes('text-2xl font-semibold text-gray-800')
                        ui.label('Accepteer een ontvangen uitnodiging').classes('text-center text-gray-600')

                # Beheer card
                with ui.card().classes('p-8 hover:shadow-xl transition-shadow cursor-pointer').style('width: 450px') as beheer_card:
                    with ui.column().classes('gap-2'):
                        ui.icon('admin_panel_settings', size='3em').classes('text-blue-600')
                        ui.label('Beheer').classes('text-2xl font-semibold text-gray-800')
                        ui.label('Groepen en uitnodigingen beheren').classes('text-center text-gray-600')

            # Make entire cards clickable
            accept_card.on('click', lambda: ui.navigate.to('/accept'))
            beheer_card.on('click', lambda: ui.navigate.to('/m/invitations'))
