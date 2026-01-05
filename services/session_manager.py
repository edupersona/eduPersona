"""
State management utilities for edupersona application.
Provides state initialization for pages using NiceGUI tab storage.
"""
from nicegui import app
from services.logging import logger


def initialize_state():
    """Initialize tab state if it doesn't exist"""
    if not hasattr(app.storage, 'tab') or not app.storage.tab:
        logger.debug("Initializing new tab state")
        app.storage.tab.update({
            'invite_code': '',
            'group_name': '',
            'redirect_url': '',
            'redirect_text': '',
            'steps_completed': {
                'code_matched': False,
                'eduid_login': False,
                'mfa_verified': False,
                'completed': False
            },
            'eduid_userinfo': {},
            'oidc_state': {}
        })
        logger.info("Tab state initialized successfully")
    else:
        logger.debug("Tab state already exists")
    return app.storage.tab
