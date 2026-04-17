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
from .assignments import (
    create_role_assignment, update_role_assignment, delete_role_assignment,
    assign_role, revoke_role, validate_assignment_end_date,
)
from .invitations import (
    create_invitation, accept_invitation, delete_invitation,
    resend_invitation, get_invitation_with_roles,
)
from .guests import delete_guest

__all__ = [
    # Models
    'Guest', 'GuestAttribute', 'Role', 'RoleAssignment',
    'Invitation', 'InvitationRoleAssignment', 'InvitationStatus',
    # Stores
    'initialize_multitenancy',
    'get_guest_store', 'get_role_store', 'get_role_assignment_store',
    'get_invitation_store', 'get_guest_attribute_store',
    # Assignments
    'create_role_assignment', 'update_role_assignment', 'delete_role_assignment',
    'assign_role', 'revoke_role', 'validate_assignment_end_date',
    # Invitations
    'create_invitation', 'accept_invitation', 'delete_invitation',
    'resend_invitation', 'get_invitation_with_roles',
    # Guests
    'delete_guest',
]
