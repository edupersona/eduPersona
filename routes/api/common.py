"""
Common utilities for API v1 endpoints.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Query

from ng_rdm.utils import logger
from services.tenant import validate_tenant


def validate_tenant_or_raise(tenant: str) -> None:
    """Validate tenant, raising HTTPException if invalid."""
    validate_tenant(tenant)


def api_response(data: Any, total: int | None = None, limit: int | None = None, offset: int | None = None) -> dict:
    """Format successful API response.

    Single resource: { "data": {...}, "meta": {"timestamp": "..."} }
    Collection: { "data": [...], "meta": {"total": N, "limit": N, "offset": N, "timestamp": "..."} }
    """
    meta: dict = {"timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    if total is not None:
        meta["total"] = total
    if limit is not None:
        meta["limit"] = limit
    if offset is not None:
        meta["offset"] = offset
    return {"data": data, "meta": meta}


def api_error(code: str, message: str, status_code: int = 400, details: dict | None = None) -> HTTPException:
    """Create standardized API error response."""
    error_body: dict = {"code": code, "message": message}
    if details:
        error_body["details"] = details
    return HTTPException(status_code=status_code, detail={"error": error_body})


def parse_expand(expand: str | None) -> list[str]:
    """Parse expand query parameter into list of field names."""
    if not expand:
        return []
    return [f.strip() for f in expand.split(",") if f.strip()]


def apply_pagination(items: list, limit: int, offset: int) -> list:
    """Apply pagination to a list of items."""
    return items[offset:offset + limit]


def log_api_call(method: str, path: str, tenant: str, **kwargs):
    """Log API call with standard format."""
    extra = ", ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
    logger.info(f"API {method} /{tenant}/api/v1{path}" + (f" ({extra})" if extra else ""))
