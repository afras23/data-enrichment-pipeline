"""
Aggregate pipeline metrics from persisted enrichment data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enrichment import EnrichmentRecord, EnrichmentRecordStatus, EnrichmentRun


class MetricsService:
    """Compute dashboard metrics from the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pipeline_metrics(self) -> dict[str, object]:
        """Return counts, average quality, and cost rollups."""

        runs_total = int(
            (
                await self._session.execute(select(func.count()).select_from(EnrichmentRun))
            ).scalar_one()
        )
        records_total = int(
            (
                await self._session.execute(select(func.count()).select_from(EnrichmentRecord))
            ).scalar_one()
        )

        completed = (
            (
                await self._session.execute(
                    select(EnrichmentRecord).where(
                        EnrichmentRecord.status == EnrichmentRecordStatus.COMPLETED.value,
                    )
                )
            )
            .scalars()
            .all()
        )

        scores: list[float] = []
        for rec in completed:
            qr = rec.quality_report
            if isinstance(qr, dict) and qr.get("final_score") is not None:
                try:
                    scores.append(float(qr["final_score"]))
                except (TypeError, ValueError):
                    continue

        avg_quality = mean(scores) if scores else None

        cost_stmt = select(func.coalesce(func.sum(EnrichmentRun.total_ai_cost_usd), 0.0))
        total_cost = float((await self._session.execute(cost_stmt)).scalar_one())

        since = datetime.now(UTC) - timedelta(hours=24)
        runs_24h = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(EnrichmentRun)
                    .where(EnrichmentRun.created_at >= since)
                )
            ).scalar_one()
        )

        return {
            "runs_total": runs_total,
            "records_total": records_total,
            "avg_quality_score": avg_quality,
            "total_ai_cost_usd": total_cost,
            "runs_last_24h": runs_24h,
            "records_completed": len(completed),
        }
