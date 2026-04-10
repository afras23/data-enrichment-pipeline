"""
Health and readiness endpoints.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""

    return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/health/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_db_session)]) -> dict[str, object]:
    """Readiness — verifies database connectivity."""

    try:
        await session.execute(text("SELECT 1"))
        db_ok = "ok"
    except Exception as exc:
        logger.error("Database readiness check failed", extra={"error": str(exc)})
        db_ok = f"error: {exc!s}"

    return {
        "status": "ready" if db_ok == "ok" else "degraded",
        "database": db_ok,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/metrics")
async def metrics(session: Annotated[AsyncSession, Depends(get_db_session)]) -> dict[str, object]:
    """Pipeline metrics backed by persisted enrichment data."""

    from app.services.metrics_service import MetricsService

    svc = MetricsService(session)
    data = await svc.pipeline_metrics()
    pool: Any = engine.sync_engine.pool
    pool_size = pool.size() if hasattr(pool, "size") else -1
    pool_out = pool.checkedout() if hasattr(pool, "checkedout") else -1
    return {
        **data,
        "system": {
            "db_pool_size": pool_size,
            "db_pool_checked_out": pool_out,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
