"""
Persistence helpers for enrichment runs and records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrichment import (
    EnrichmentRecord,
    EnrichmentRun,
    EnrichmentRunStatus,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class EnrichmentRepository:
    """Database access for enrichment entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self, *, total_companies: int, correlation_id: str | None
    ) -> EnrichmentRun:
        run = EnrichmentRun(
            status=EnrichmentRunStatus.PENDING.value,
            correlation_id=correlation_id,
            total_companies=total_companies,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run(self, run_id: UUID) -> EnrichmentRun | None:
        return await self._session.get(EnrichmentRun, run_id)

    async def update_run_totals(
        self,
        run_id: UUID,
        *,
        status: EnrichmentRunStatus,
        succeeded: int,
        failed: int,
        total_cost: float,
        error_message: str | None = None,
    ) -> None:
        run = await self._session.get(EnrichmentRun, run_id)
        if not run:
            return
        completed = _utc_now()
        started = _ensure_utc(run.started_at) or completed
        duration = (completed - started).total_seconds()
        run.status = status.value
        run.succeeded_count = succeeded
        run.failed_count = failed
        run.total_ai_cost_usd = total_cost
        run.completed_at = completed
        run.duration_seconds = duration
        run.error_message = error_message

    async def add_record(self, record: EnrichmentRecord) -> EnrichmentRecord:
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_runs(self, *, skip: int, limit: int) -> tuple[list[EnrichmentRun], int]:
        count_stmt = select(func.count()).select_from(EnrichmentRun)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = (
            select(EnrichmentRun)
            .order_by(EnrichmentRun.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def list_companies(self, *, skip: int, limit: int) -> tuple[list[EnrichmentRecord], int]:
        count_stmt = select(func.count()).select_from(EnrichmentRecord)
        total = int((await self._session.execute(count_stmt)).scalar_one())
        stmt = (
            select(EnrichmentRecord)
            .order_by(EnrichmentRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def get_company(self, company_id: UUID) -> EnrichmentRecord | None:
        return await self._session.get(EnrichmentRecord, company_id)
