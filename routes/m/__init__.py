"""
Routes for /m pages
"""

# Import the page functions to register them with NiceGUI
from .groups import groups_page
from .invitations import invitations_page
from .login import admin_login_page, admin_oidc_login_redirect, admin_logout_page

# Export the page functions
__all__ = ['groups_page', 'invitations_page', 'admin_login_page', 'admin_oidc_login_redirect', 'admin_logout_page']
