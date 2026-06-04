"""Idempotent schema migration for the persona pivot (Phase I.5).

Drops the role-mode tables and the legacy Invitation columns (personal_message,
guest_id) from an existing SQLite database. Fresh databases created by
generate_schemas already match the new schema, so this only matters for a
persistent dev DB carried across the cutover.

    python tools/migrate_persona_pivot.py [path/to/edupersona.db]

Safe to run repeatedly: every step checks existence first.
"""
import sqlite3
import sys

_DROP_TABLES = [
    "invitation_role_assignments",
    "role_assignments",
    "roles",
    "guest_attributes",
    "guests",
]

_DROP_INVITATION_COLUMNS = ["personal_message", "guest_id"]


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for table in _DROP_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"dropped (if existed): {table}")

        if "invitations" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            existing = _columns(conn, "invitations")
            for col in _DROP_INVITATION_COLUMNS:
                if col in existing:
                    # SQLite 3.35+ supports DROP COLUMN directly.
                    conn.execute(f"ALTER TABLE invitations DROP COLUMN {col}")
                    print(f"dropped column: invitations.{col}")
        conn.commit()
        print("migration complete")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate(sys.argv[1] if len(sys.argv) > 1 else "edupersona.db")
