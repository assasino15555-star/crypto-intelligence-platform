from __future__ import annotations

import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from ...core.config import get_settings
from ...core.logging import get_logger
from ...db.session import get_engine

router = APIRouter(prefix="/health", tags=["health"])
log = get_logger(__name__)


@router.get("/live", status_code=200)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(response: Response) -> dict[str, object]:
    start = time.monotonic()
    settings = get_settings()
    db_ok = True
    db_error: str | None = None
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)[:200] if not settings.is_production else "unavailable"
    elapsed_ms = int((time.monotonic() - start) * 1000)
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "db_error": db_error,
        "environment": settings.environment,
        "elapsed_ms": elapsed_ms,
    }
