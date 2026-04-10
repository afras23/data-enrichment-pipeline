"""
Metrics aggregation after mixed-success enrichment records (DB-backed, no live HTTP).
"""

from __future__ import annotations

import pytest

import app.db.session as session_module
from app.models.enrichment import (
    EnrichmentRecord,
    EnrichmentRecordStatus,
    EnrichmentRun,
    EnrichmentRunStatus,
)
from app.services.metrics_service import MetricsService


@pytest.mark.asyncio
async def test_metrics_avg_quality_reflects_completed_records_only(
    patch_session_factory: object,
) -> None:
    """avg_quality_score averages final_score from completed rows; failed rows ignored."""

    async with session_module.async_session_factory() as session:
        run = EnrichmentRun(
            status=EnrichmentRunStatus.COMPLETED.value,
            total_companies=3,
            succeeded_count=2,
            failed_count=1,
            total_ai_cost_usd=0.05,
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                EnrichmentRecord(
                    run_id=run.id,
                    company_name="A",
                    normalized_name_key="a",
                    status=EnrichmentRecordStatus.COMPLETED.value,
                    quality_report={"final_score": 0.2},
                ),
                EnrichmentRecord(
                    run_id=run.id,
                    company_name="B",
                    normalized_name_key="b",
                    status=EnrichmentRecordStatus.COMPLETED.value,
                    quality_report={"final_score": 0.8},
                ),
                EnrichmentRecord(
                    run_id=run.id,
                    company_name="C",
                    normalized_name_key="c",
                    status=EnrichmentRecordStatus.PARTIAL.value,
                    quality_report=None,
                ),
            ]
        )
        await session.commit()

    async with session_module.async_session_factory() as session:
        svc = MetricsService(session)
        m = await svc.pipeline_metrics()

    assert m["records_total"] == 3
    assert m["runs_total"] == 1
    assert m["avg_quality_score"] == pytest.approx(0.5, rel=1e-3)
    assert m["records_completed"] == 2


@pytest.mark.asyncio
async def test_metrics_runs_last_24h_counts_recent_runs(
    patch_session_factory: object,
) -> None:
    """runs_last_24h uses created_at filter (production MetricsService logic)."""

    from datetime import UTC, datetime, timedelta

    async with session_module.async_session_factory() as session:
        old = EnrichmentRun(
            status=EnrichmentRunStatus.COMPLETED.value,
            total_companies=1,
            succeeded_count=1,
            failed_count=0,
            total_ai_cost_usd=0.0,
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
        new = EnrichmentRun(
            status=EnrichmentRunStatus.COMPLETED.value,
            total_companies=1,
            succeeded_count=1,
            failed_count=0,
            total_ai_cost_usd=0.0,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
        session.add_all([old, new])
        await session.commit()

    async with session_module.async_session_factory() as session:
        svc = MetricsService(session)
        m = await svc.pipeline_metrics()

    assert m["runs_total"] == 2
    assert m["runs_last_24h"] == 1
