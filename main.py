import json

from nicegui import app, ui

# register routes
import routes.accept
import routes.api
import routes.landing
import routes.m  # all /m routes
from services.auth.oidc import init_edupersona_oidc
from services.logging import logger, setup_logging

try:
    settings = json.load(open('settings.json'))
except Exception:
    settings = {}
    print("Warning: could not load settings.json; set storage_secret for production use!")

DTAP, STORAGE_SECRET, LOG_LEVEL, CONSOLE_LOGGING = (
    settings.get('DTAP', 'dev'),
    settings.get('storage_secret', 'your-secret-here'),
    settings.get('log_level', 'INFO'),
    settings.get('console_logging', False)
)

setup_logging(
    log_file='edupersona.log',
    level=LOG_LEVEL,
    enable_console_logging=CONSOLE_LOGGING
)

# Initialize OIDC
init_edupersona_oidc()

app.add_static_files('/img', 'img')


# repairing butt ugly Quasar/Material defaults
ui.button.default_props('no-caps')
ui.button.default_style('color:white; font-size:14pt;')
ui.button.__init__.__kwdefaults__['color'] = '#3b82f6'  # type: ignore
ui.label.default_style('text-align: left;')

# call this to run in production (from uvicorn)
def run(fastapi_app) -> None:
    ui.run_with(fastapi_app, storage_secret=STORAGE_SECRET, title='eduPersona', prod_js=True)

if __name__ in {"__main__", "__mp_main__"}:
    if DTAP == "dev":
        HOST = 'localhost'
        PORT = 8090
        logger.info(f"Starting edupersona on {HOST}:{PORT}")
        ui.run(host=HOST, port=PORT, storage_secret=STORAGE_SECRET, title='eduPersona', show=False)
    else:
        print("For production use: run main_fastapi:fastapi_app from uvicorn")
