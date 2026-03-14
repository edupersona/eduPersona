"""
Domain layer: models, stores, business logic, and API schemas.
"""

from .models import (
    Guest, GuestAttribute, Role, RoleAssignment,
    Invitation, InvitationRoleAssignment, InvitationStatus,
)
from .stores import (
    initialize_multitenancy,
    get_guest_store, get_role_store, get_role_assignment_store,
    get_invitation_store, get_guest_attribute_store,
)
from .invitation_flow import (
    create_role_assignment, update_role_assignment,
    create_invitation, accept_invitation,
    assign_role, revoke_role,
    resend_invitation, get_invitation_with_roles,
    validate_assignment_end_date,
)

__all__ = [
    # Models
    'Guest', 'GuestAttribute', 'Role', 'RoleAssignment',
    'Invitation', 'InvitationRoleAssignment', 'InvitationStatus',
    # Stores
    'initialize_multitenancy',
    'get_guest_store', 'get_role_store', 'get_role_assignment_store',
    'get_invitation_store', 'get_guest_attribute_store',
    # Business logic
    'create_role_assignment', 'update_role_assignment',
    'create_invitation', 'accept_invitation',
    'assign_role', 'revoke_role',
    'resend_invitation', 'get_invitation_with_roles',
    'validate_assignment_end_date',
]
