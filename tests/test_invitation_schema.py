"""Phase C — Invitation gains persona fields as additive nullable columns.

Verifies both modes coexist on one table: legacy role-mode rows (with a Guest FK)
still round-trip, and persona-mode rows persist the new columns with guest=None.
Direct Tortoise-model usage against the autouse in-memory SQLite fixture.
"""

from domain.models import Guest, Invitation


async def test_legacy_invitation_roundtrip(test_tenant):
    """Role-mode shape (guest FK + personal_message) still persists unchanged."""
    guest = await Guest.create(
        tenant=test_tenant, email="g@example.org", given_name="Gwen", family_name="Guest",
    )
    inv = await Invitation.create(
        tenant=test_tenant, code="LEGACY1", guest=guest,
        invitation_email="g@example.org", personal_message="hi there", status="pending",
    )
    fetched = await Invitation.get(id=inv.id)
    assert fetched.code == "LEGACY1"
    assert fetched.guest_id == guest.id  # type: ignore[attr-defined]
    assert fetched.personal_message == "hi there"
    assert fetched.persona_key is None  # new columns default NULL for legacy rows


async def test_persona_columns_persist(test_tenant):
    """Persona-mode row: new columns persist, JSON round-trips, guest is NULL."""
    inv = await Invitation.create(
        tenant=test_tenant, code="PERSONA1", guest=None,
        invitation_email="anna@example.org",
        given_name="Anna", family_name="Verver",
        persona_key="gastdocent", client_ref="EMP-42",
        persona_params={"department": "CS", "personal_message": "welcome"},
        sender_email="noreply@edupersona.nl", sender_name="eduPersona",
        callback_url="https://client.example.org/hook",
        step_outputs={"eduid": {"sub": "abc", "uids": ["anna"]}},
    )
    fetched = await Invitation.get(id=inv.id)
    assert fetched.guest_id is None  # type: ignore[attr-defined]
    assert fetched.given_name == "Anna"
    assert fetched.family_name == "Verver"
    assert fetched.persona_key == "gastdocent"
    assert fetched.client_ref == "EMP-42"
    # JSON fields round-trip as native dicts
    assert fetched.persona_params == {"department": "CS", "personal_message": "welcome"}
    assert fetched.step_outputs["eduid"]["uids"] == ["anna"]  # type: ignore[index]
    assert fetched.callback_url == "https://client.example.org/hook"


async def test_filter_by_persona_key_and_client_ref(test_tenant):
    """Persona-mode filtering works at SQL level (persona_key, client_ref indexed)."""
    for code, persona, ref in [
        ("A", "gastdocent", "R1"), ("B", "gastdocent", "R2"), ("C", "alumnus", "R1"),
    ]:
        await Invitation.create(
            tenant=test_tenant, code=code, guest=None,
            invitation_email=f"{code}@example.org", persona_key=persona, client_ref=ref,
        )
    by_persona = await Invitation.filter(tenant=test_tenant, persona_key="gastdocent").all()
    assert {i.code for i in by_persona} == {"A", "B"}
    by_ref = await Invitation.filter(tenant=test_tenant, client_ref="R1").all()
    assert {i.code for i in by_ref} == {"A", "C"}
    # cross-invitation grouping by email works without a Guest entity (§2.7)
    by_email = await Invitation.filter(invitation_email="A@example.org").all()
    assert len(by_email) == 1
