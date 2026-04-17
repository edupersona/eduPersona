"""
Guest-level cross-store operations: cascade delete of guest + related records.
"""
from domain.assignments import delete_role_assignment
from domain.invitations import delete_invitation
from domain.stores import (
    get_guest_attribute_store,
    get_guest_store,
    get_invitation_store,
    get_role_assignment_store,
)


async def delete_guest(tenant: str, guest_id: int) -> None:
    """Delete a guest and cascade to related records.

    Cascade order: role assignments (and their junctions) → invitations (and their
    junctions) → guest attributes → guest itself. Each delete goes through its
    store so observers see a StoreEvent("delete") for every affected row.
    """
    ra_store = get_role_assignment_store(tenant)
    inv_store = get_invitation_store(tenant)
    attr_store = get_guest_attribute_store(tenant)
    guest_store = get_guest_store(tenant)

    for ra in await ra_store.read_items(filter_by={"guest_id": guest_id}):
        await delete_role_assignment(tenant, ra)
    for inv in await inv_store.read_items(filter_by={"guest_id": guest_id}):
        await delete_invitation(tenant, inv)
    for attr in await attr_store.read_items(filter_by={"guest_id": guest_id}):
        await attr_store.delete_item(attr)
    await guest_store.delete_item({"id": guest_id})
