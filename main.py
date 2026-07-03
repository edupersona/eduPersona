from nicegui import app, ui

# from tortoise import Tortoise
# register routes
import routes.accept
import routes.api
import routes.contact
from routes.api import api_router
import routes.landing
import routes.m  # all /m routes
import routes.m.simulator  # /m/{tenant}/simulator (registered here, not via routes.m.__init__)
import routes.register
from ng_rdm.store.orm import init_db
from ng_rdm.utils import logger, configure_logging
from services.auth.oidc import init_edupersona_oidc
from services.exception_handlers import register_exception_handlers
from services.settings import config
from services.persona_loader import validate_personas_or_raise
from domain.migrations import run_migrations
from domain.stores import initialize_multitenancy

DTAP, STORAGE_SECRET, LOG_LEVEL, CONSOLE_LOGGING = (
    config.get('DTAP', 'dev'),
    config.get('storage_secret', 'your-secret-here'),
    config.get('log_level', 'INFO'),
    config.get('console_logging', False)
)

configure_logging(
    log_file='edupersona.log',
    level=LOG_LEVEL,
    console=CONSOLE_LOGGING
)

app.add_static_files('/static', 'static')
app.include_router(api_router)


@app.middleware('http')
async def _no_cache_html(request, call_next):
    """iOS Safari aggressively caches the page HTML — and since base.css / ng_rdm.css are
    inlined into that HTML (ui.add_css reads + injects them), a cached page = stale CSS.
    Mark only the HTML document non-cacheable; /static assets keep their normal caching."""
    response = await call_next(request)
    if response.headers.get('content-type', '').startswith('text/html'):
        response.headers['Cache-Control'] = 'no-store'
    return response

register_exception_handlers(app)
init_edupersona_oidc()
initialize_multitenancy()
validate_personas_or_raise()  # fail fast on broken persona/step/mail config

# repairing butt ugly Quasar/Material defaults
# note: any default_styles are hard-coded into element styles
ui.button.default_props('no-caps')
# button color/size now in static/css/base.css (.q-btn)
ui.tabs.default_props('no-caps')
ui.tab_panels.default_props('animated=false')


# call this to run in production (from uvicorn)
def run(fastapi_app) -> None:
    import asyncio
    from services.webhook import webhook_retry_loop

    # Initialize Tortoise ORM with SQLite database
    init_db(
        fastapi_app,
        db_url='sqlite://edupersona.db',
        modules={"models": ["domain.models"]},
        generate_schemas=True,
    )
    app.on_startup(run_migrations)
    app.on_startup(lambda: asyncio.create_task(webhook_retry_loop()))
    ui.run_with(fastapi_app, storage_secret=STORAGE_SECRET, title='eduPersona',
                favicon='static/img/favicons/favicon.ico')


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(storage_secret=STORAGE_SECRET, title='eduPersona',
           favicon='static/img/favicons/favicon.ico')

