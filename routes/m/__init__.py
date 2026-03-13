"""
Routes for /m pages
"""

# Import the page functions to register them with NiceGUI
from .roles import roles_page
from .guests import guests_page
from .invitations import invitations_page
from .login import admin_login_page, admin_oidc_login_redirect, admin_logout_page

__all__ = ['roles_page', 'guests_page', 'invitations_page',
           'admin_login_page', 'admin_oidc_login_redirect', 'admin_logout_page']
