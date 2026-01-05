from nicegui import ui

def create_navigation_header(current_page: str):
    nav_items = [
        {'name': 'Home', 'path': '/', 'key': 'home'},
        {'name': 'Uitnodigingen', 'path': '/m/invitations', 'key': 'invitations'},
        {'name': 'Groepen', 'path': '/m/groups', 'key': 'groups'},
        {'name': 'Accept', 'path': '/accept', 'key': 'accept'}
    ]

    active_classes = 'px-4 py-2 rounded bg-blue-500 text-white font-semibold'
    inactive_classes = 'px-4 py-2 rounded bg-gray-200 text-gray-700 hover:bg-gray-300 transition-colors'

    with ui.row().classes('w-full mb-6 p-4 bg-gray-100 rounded-lg gap-4'):
        for item in nav_items:
            if current_page == item['key']:
                ui.label(item['name']).classes(active_classes).style('font-size: 12pt;')
            else:
                ui.link(item['name'], item['path']).classes(inactive_classes).style('font-size: 12pt;')
