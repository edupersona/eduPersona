"""
Global cleanup endpoint (non-tenant scoped).

POST /api/v1/cleanup - Trigger daily cleanup tasks

Cleans up:
- Roles past their role_end_date (cascade deletes assignments)
- Role assignments past their end_date
- Pending invitations older than invitation_expiration_days
"""
from fastapi import HTTPException

from . import api_router

from ng_rdm.utils import logger
from services.cleanup import run_all_cleanup_tasks
from services.settings import config
from .common import api_response, api_error


@api_router.post("/api/v1/cleanup")
async def run_cleanup(api_key: str = ""):
    """Trigger daily cleanup tasks (called by external scheduler)."""
    expected_key = config.get("cleanup_api_key", "")
    if not expected_key:
        raise api_error("NOT_CONFIGURED", "Cleanup not configured", status_code=503)
    if api_key != expected_key:
        raise api_error("UNAUTHORIZED", "Invalid API key", status_code=401)

    logger.info("API POST /api/v1/cleanup - starting cleanup")
    results = await run_all_cleanup_tasks()
    logger.info(f"API POST /api/v1/cleanup - completed: {results['totals']}")
    return api_response(results)
