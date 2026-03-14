#!/usr/bin/env python3
"""
Database import/export utility for edupersona.

Usage:
    python db_io.py import db_export.json --tenant uva
    python db_io.py export db_export_new.json --tenant uva
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import date, datetime
from tortoise import Tortoise
from models.models import (Guest, Role, RoleAssignment, Invitation, InvitationRoleAssignment, GuestAttribute)

HELP = """Usage: db_io.py COMMAND FILE [OPTIONS]

Database import/export for edupersona

Commands:
  import FILE [--tenant NAME] [--recreate]    Import JSON to database
  export FILE [--tenant NAME]                 Export database to JSON

Options:
  --tenant NAME   Tenant identifier (default: uva)
  --recreate      Drop and recreate all tables first (import only)
"""

async def populate_from_json(json_file_path: str, tenant: str = "uva"):
    with open(json_file_path) as f:
        data = json.load(f)

    # Handle tenant-wrapped format ({"tenant": {"name": "uva", "guests": [...], ...}})
    if "tenant" in data:
        tenant_data = data["tenant"]
        tenant = tenant_data.get("name", tenant)
        data = tenant_data  # Use the inner tenant data

    # Clear all tables in dependency order
    await InvitationRoleAssignment.all().delete()
    await Invitation.all().delete()
    await RoleAssignment.all().delete()
    await GuestAttribute.all().delete()
    await Guest.all().delete()
    await Role.all().delete()

    stats = {"guests": 0, "attributes": 0, "roles": 0, "role_assignments": 0, "invitations": 0}

    # Map JSON id (int) -> Guest instance
    guest_map = {}
    for guest_data in data.get("guests", []):
        json_guest_id = guest_data.get("id")
        guest = await Guest.create(
            tenant=tenant,
            user_id=guest_data["user_id"],
            scim_id=guest_data.get("scim_id"),
            given_name=guest_data.get("given_name"),
            family_name=guest_data.get("family_name"),
            email=guest_data.get("email", ""),
        )
        guest_map[json_guest_id] = guest
        stats["guests"] += 1

        # Create attributes from dict
        for attr_name, attr_value in guest_data.get("attributes", {}).items():
            await GuestAttribute.create(
                guest=guest,
                name=attr_name,
                value=json.dumps(attr_value)
            )
            stats["attributes"] += 1

    # Map JSON role id -> Role instance
    role_map = {}
    for role_data in data.get("roles", []):
        json_role_id = role_data.get("role_id") or role_data.get("id")
        role = await Role.create(
            tenant=tenant,
            scim_id=role_data.get("scim_id"),
            name=role_data["name"],
            role_details=role_data.get("role_details"),
            scope=role_data.get("scope"),
            org_name=role_data.get("org_name"),
            logo_file_name=role_data.get("logo_file_name"),
            mail_sender_email=role_data.get("mail_sender_email", ""),
            mail_sender_name=role_data.get("mail_sender_name", ""),
            more_info_email=role_data.get("more_info_email"),
            more_info_name=role_data.get("more_info_name"),
            redirect_url=role_data.get("redirect_url", ""),
            redirect_text=role_data.get("redirect_text", ""),
            default_start_date=role_data.get("default_start_date"),
            default_end_date=role_data.get("default_end_date"),
            role_end_date=role_data.get("role_end_date"),
        )
        role_map[json_role_id] = role
        stats["roles"] += 1

    # Handle NEW format: role_assignments + invitations (separate)
    if "role_assignments" in data:
        # Map JSON role_assignment id -> RoleAssignment instance
        ra_map = {}
        for ra_data in data.get("role_assignments", []):
            json_ra_id = ra_data.get("id")
            json_guest_id = ra_data.get("guest_id")
            json_role_id = ra_data.get("role_id")

            start_date = ra_data.get("start_date") or None
            end_date = ra_data.get("end_date") or None

            ra = await RoleAssignment.create(
                tenant=tenant,
                guest=guest_map[json_guest_id],
                role=role_map[json_role_id],
                start_date=start_date,
                end_date=end_date,
            )
            if json_ra_id:
                ra_map[json_ra_id] = ra
            stats["role_assignments"] += 1

        # Create invitations with junction records
        for inv_data in data.get("invitations", []):
            json_guest_id = inv_data.get("guest_id")
            accepted_at = inv_data.get("accepted_at") or None

            invitation = await Invitation.create(
                code=inv_data.get("code") or uuid.uuid4().hex,
                tenant=tenant,
                guest=guest_map[json_guest_id],
                personal_message=inv_data.get("personal_message"),
                invitation_email=inv_data["invitation_email"],
                invited_at=inv_data.get("invited_at"),
                accepted_at=accepted_at,
                status=inv_data.get("status", "pending"),
            )
            stats["invitations"] += 1

            # Link to role assignments via junction table
            for ra_id in inv_data.get("role_assignment_ids", []):
                if ra_id in ra_map:
                    await InvitationRoleAssignment.create(
                        invitation=invitation,
                        role_assignment=ra_map[ra_id],
                    )

    # Handle OLD format: memberships (combined role assignment + invitation)
    elif "memberships" in data:
        for membership_data in data.get("memberships", []):
            # JSON uses "user_id" or "guest_id" to reference guest
            json_guest_id = membership_data.get("guest_id") or membership_data.get("user_id")
            json_role_id = membership_data["role_id"]

            # Handle empty string -> None for datetime/date fields
            accepted_at = membership_data.get("accepted_at") or None
            start_date = membership_data.get("start_date") or None
            end_date = membership_data.get("end_date") or None

            # Create RoleAssignment (the binding)
            role_assignment = await RoleAssignment.create(
                tenant=tenant,
                guest=guest_map[json_guest_id],
                role=role_map[json_role_id],
                start_date=start_date,
                end_date=end_date,
            )
            stats["role_assignments"] += 1

            # Map old status to new invitation status
            old_status = membership_data.get("status", "invited")
            new_status = "accepted" if old_status == "accepted" else "pending"
            if old_status in ("expired", "revoked"):
                new_status = old_status

            # Create Invitation
            invitation = await Invitation.create(
                code=uuid.uuid4().hex,
                tenant=tenant,
                guest=guest_map[json_guest_id],
                personal_message=membership_data.get("personal_message"),
                invitation_email=membership_data["invitation_email"],
                invited_at=membership_data.get("invited_at"),
                accepted_at=accepted_at,
                status=new_status,
            )
            stats["invitations"] += 1

            # Link invitation to role assignment
            await InvitationRoleAssignment.create(
                invitation=invitation,
                role_assignment=role_assignment,
            )

    return stats


DB_PATH = Path(__file__).resolve().parent.parent / "edupersona.db"

async def init_db():
    await Tortoise.init(
        db_url=f"sqlite://{DB_PATH}",
        modules={"models": ["models.models"]}
    )


async def import_json(json_path: str, tenant: str, recreate: bool = False):
    """Import JSON file to database."""
    await init_db()
    if recreate:
        await Tortoise._drop_databases()
        await Tortoise.close_connections()
        await init_db()
        await Tortoise.generate_schemas(safe=False)
        print("Database schema recreated (tables dropped and recreated)")
    else:
        await Tortoise.generate_schemas(safe=True)

    print(f"\nImporting {json_path}...")
    stats = await populate_from_json(json_path, tenant=tenant)

    print("\nImport complete:")
    print(f"  Guests: {stats['guests']}")
    print(f"  Attributes: {stats['attributes']}")
    print(f"  Roles: {stats['roles']}")
    print(f"  Role assignments: {stats['role_assignments']}")
    print(f"  Invitations: {stats['invitations']}")

    await Tortoise.close_connections()


async def export_json(json_path: str, tenant: str):
    """Export database to JSON file."""
    await init_db()

    def serialize(val):
        if isinstance(val, (date, datetime)):
            return val.isoformat()
        return val

    guests_data = []
    for guest in await Guest.filter(tenant=tenant):
        attrs = {}
        for attr in await GuestAttribute.filter(guest=guest):
            try:
                attrs[attr.name] = json.loads(attr.value)
            except json.JSONDecodeError:
                attrs[attr.name] = attr.value
        guests_data.append({
            "id": guest.id,
            "user_id": guest.user_id,
            "scim_id": guest.scim_id,
            "given_name": guest.given_name,
            "family_name": guest.family_name,
            "email": guest.email,
            "attributes": attrs,
        })

    roles_data = []
    for role in await Role.filter(tenant=tenant):
        roles_data.append({
            "id": role.id,
            "scim_id": role.scim_id,
            "name": role.name,
            "role_details": role.role_details,
            "scope": role.scope,
            "org_name": role.org_name,
            "mail_sender_name": role.mail_sender_name,
            "mail_sender_email": role.mail_sender_email,
            "more_info_name": role.more_info_name,
            "more_info_email": role.more_info_email,
            "redirect_url": role.redirect_url,
            "redirect_text": role.redirect_text,
            "default_start_date": serialize(role.default_start_date),
            "default_end_date": serialize(role.default_end_date),
            "role_end_date": serialize(role.role_end_date),
            "logo_file_name": role.logo_file_name,
        })

    role_assignments_data = []
    for ra in await RoleAssignment.filter(tenant=tenant).prefetch_related("guest", "role"):
        role_assignments_data.append({
            "id": ra.id,
            "guest_id": ra.guest.id,
            "role_id": ra.role.id,
            "start_date": serialize(ra.start_date),
            "end_date": serialize(ra.end_date),
        })

    ra_id_map = {ra["id"]: ra["id"] for ra in role_assignments_data}

    invitations_data = []
    for inv in await Invitation.filter(tenant=tenant).prefetch_related("guest"):
        junctions = await InvitationRoleAssignment.filter(invitation=inv).prefetch_related("role_assignment")
        ra_ids = [j.role_assignment.id for j in junctions if j.role_assignment.id in ra_id_map]
        invitations_data.append({
            "id": inv.id,
            "code": inv.code,
            "guest_id": inv.guest.id,
            "personal_message": inv.personal_message,
            "invitation_email": inv.invitation_email,
            "invited_at": serialize(inv.invited_at),
            "accepted_at": serialize(inv.accepted_at),
            "status": inv.status,
            "role_assignment_ids": ra_ids,
        })

    export_data = {
        "tenant": {
            "name": tenant,
            "guests": guests_data,
            "roles": roles_data,
            "role_assignments": role_assignments_data,
            "invitations": invitations_data,
        }
    }

    with open(json_path, 'w') as f:
        json.dump(export_data, f, indent=4)

    print(f"Exported to {json_path}:")
    print(f"  Guests: {len(guests_data)}")
    print(f"  Roles: {len(roles_data)}")
    print(f"  Role assignments: {len(role_assignments_data)}")
    print(f"  Invitations: {len(invitations_data)}")

    await Tortoise.close_connections()


def parse_args(args: list[str]) -> tuple[str, str, str, bool]:
    """Parse command line arguments. Returns (command, file, tenant, recreate)."""
    if not args or args[0] in ('-h', '--help') or args[0] not in ('import', 'export'):
        print(HELP)
        sys.exit(0 if args and args[0] in ('-h', '--help') else 1)

    command = args[0]
    args = args[1:]

    if not args:
        print(f"Error: {command} requires FILE argument\n")
        print(HELP)
        sys.exit(1)

    json_file = None
    tenant = 'uva'
    recreate = False
    i = 0
    while i < len(args):
        if args[i] == '--tenant' and i + 1 < len(args):
            tenant = args[i + 1]
            i += 2
        elif args[i] == '--recreate':
            recreate = True
            i += 1
        elif args[i] in ('-h', '--help'):
            print(HELP)
            sys.exit(0)
        elif not args[i].startswith('-'):
            json_file = args[i]
            i += 1
        else:
            print(f"Unknown option: {args[i]}\n")
            print(HELP)
            sys.exit(1)

    if not json_file:
        print(f"Error: {command} requires FILE argument\n")
        print(HELP)
        sys.exit(1)

    return command, json_file, tenant, recreate


if __name__ == "__main__":
    command, json_file, tenant, recreate = parse_args(sys.argv[1:])

    if command == 'import':
        asyncio.run(import_json(json_file, tenant, recreate))
    elif command == 'export':
        asyncio.run(export_json(json_file, tenant))
