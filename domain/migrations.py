"""Ad-hoc schema migrations for columns added after initial generate_schemas."""
from tortoise import connections

from ng_rdm.utils import logger


# async def ensure_eduid_pseudonym_column() -> None:
#     """Add guests.eduid_pseudonym column + index if missing (SQLite)."""
#     conn = connections.get("default")
#     _, rows = await conn.execute_query("PRAGMA table_info(guests)")
#     col_names = {row["name"] for row in rows}
#     if "eduid_pseudonym" in col_names:
#         return
#     logger.info("Migrating: adding guests.eduid_pseudonym column")
#     await conn.execute_script(
#         "ALTER TABLE guests ADD COLUMN eduid_pseudonym VARCHAR(255);"
#         "CREATE INDEX IF NOT EXISTS idx_guests_eduid_pseudonym ON guests(eduid_pseudonym);"
#     )


async def run_migrations() -> None:
    """Run all pending schema migrations."""
    pass
