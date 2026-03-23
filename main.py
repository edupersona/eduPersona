from nicegui import app, ui

# from tortoise import Tortoise
# register routes
import routes.accept
import routes.api
from routes.api import api_router
import routes.landing
import routes.m  # all /m routes
from ng_rdm.store.orm import close_db, init_db
from ng_rdm.utils import logger, setup_logging
from services.auth.oidc import init_edupersona_oidc
from services.exception_handlers import register_exception_handlers
from services.settings import config
from domain.stores import initialize_multitenancy

DTAP, STORAGE_SECRET, LOG_LEVEL, CONSOLE_LOGGING = (
    config.get('DTAP', 'dev'),
    config.get('storage_secret', 'your-secret-here'),
    config.get('log_level', 'INFO'),
    config.get('console_logging', False)
)

setup_logging(
    log_file='edupersona.log',
    level=LOG_LEVEL,
    enable_console_logging=CONSOLE_LOGGING
)

app.on_shutdown(close_db)
app.add_static_files('/static', 'static')
app.include_router(api_router)

register_exception_handlers(app)
init_edupersona_oidc()
initialize_multitenancy()

# repairing butt ugly Quasar/Material defaults
# note: any default_styles are hard-coded into element styles
ui.button.default_props('no-caps')
# button color/size now in static/css/base.css (.q-btn)
ui.tabs.default_props('no-caps')
ui.tab_panels.default_props('animated=false')


# call this to run in production (from uvicorn)
def run(fastapi_app) -> None:
    # Initialize Tortoise ORM with SQLite database
    init_db(
        fastapi_app,
        db_url='sqlite://edupersona.db',
        modules={"models": ["domain.models"]}
    )
    ui.run_with(fastapi_app, storage_secret=STORAGE_SECRET, title='eduPersona')


if __name__ in {"__main__", "__mp_main__"}:
    if DTAP == "dev":
        HOST = 'localhost'
        PORT = 8090
        logger.info(f"Starting edupersona on {HOST}:{PORT}")
        ui.run(host=HOST, port=PORT, storage_secret=STORAGE_SECRET, title='eduPersona', show=False)
    else:
        print("For production use: run main_fastapi:fastapi_app from uvicorn")
