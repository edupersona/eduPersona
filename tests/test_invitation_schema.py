"""Invitation model schema — persona-only after the Phase I cutover.

Verifies the persona columns persist and JSON round-trips, and that SQL-level
filtering (persona_key, client_ref, email) works without a Guest entity.
"""

from domain.models import Invitation


async def test_persona_columns_persist(test_tenant):
    inv = await Invitation.create(
        tenant=test_tenant, code="PERSONA1",
        invitation_email="anna@example.org",
        given_name="Anna", family_name="Verver",
        persona_key="gastdocent", client_ref="EMP-42",
        persona_params={"department": "CS", "personal_message": "welcome"},
        sender_email="noreply@edupersona.nl", sender_name="eduPersona",
        callback_url="https://client.example.org/hook",
        step_outputs={"eduid": {"sub": "abc", "uids": ["anna"]}},
    )
    fetched = await Invitation.get(id=inv.id)
    assert fetched.given_name == "Anna"
    assert fetched.family_name == "Verver"
    assert fetched.persona_key == "gastdocent"
    assert fetched.client_ref == "EMP-42"
    assert fetched.persona_params == {"department": "CS", "personal_message": "welcome"}
    assert fetched.step_outputs["eduid"]["uids"] == ["anna"]  # type: ignore[index]
    assert fetched.callback_url == "https://client.example.org/hook"


async def test_filter_by_persona_key_and_client_ref(test_tenant):
    for code, persona, ref in [
        ("A", "gastdocent", "R1"), ("B", "gastdocent", "R2"), ("C", "alumnus", "R1"),
    ]:
        await Invitation.create(
            tenant=test_tenant, code=code,
            invitation_email=f"{code}@example.org", persona_key=persona, client_ref=ref,
        )
    by_persona = await Invitation.filter(tenant=test_tenant, persona_key="gastdocent").all()
    assert {i.code for i in by_persona} == {"A", "B"}
    by_ref = await Invitation.filter(tenant=test_tenant, client_ref="R1").all()
    assert {i.code for i in by_ref} == {"A", "C"}
    by_email = await Invitation.filter(invitation_email="A@example.org").all()
    assert len(by_email) == 1
