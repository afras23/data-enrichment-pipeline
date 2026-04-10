"""Metrics service tests."""

from __future__ import annotations

import pytest

from app.models.enrichment import (
    EnrichmentRecord,
    EnrichmentRecordStatus,
    EnrichmentRun,
    EnrichmentRunStatus,
)
from app.services.metrics_service import MetricsService


@pytest.mark.asyncio
async def test_pipeline_metrics_empty_db(patch_session_factory: object) -> None:
    """Metrics return zeros on an empty database."""

    import app.db.session as session_module

    async with session_module.async_session_factory() as session:
        svc = MetricsService(session)
        m = await svc.pipeline_metrics()
        assert m["runs_total"] == 0
        assert m["records_total"] == 0
        assert m["avg_quality_score"] is None


@pytest.mark.asyncio
async def test_pipeline_metrics_with_completed_record(patch_session_factory: object) -> None:
    """Average quality aggregates completed rows."""

    import app.db.session as session_module

    async with session_module.async_session_factory() as session:
        run = EnrichmentRun(
            status=EnrichmentRunStatus.COMPLETED.value,
            total_companies=1,
            succeeded_count=1,
            failed_count=0,
            total_ai_cost_usd=0.01,
        )
        session.add(run)
        await session.flush()
        rec = EnrichmentRecord(
            run_id=run.id,
            company_name="X",
            normalized_name_key="x",
            status=EnrichmentRecordStatus.COMPLETED.value,
            quality_report={"final_score": 0.9},
        )
        session.add(rec)
        await session.commit()

    async with session_module.async_session_factory() as session:
        svc = MetricsService(session)
        m = await svc.pipeline_metrics()
        assert m["runs_total"] == 1
        assert m["records_total"] == 1
        assert m["avg_quality_score"] == pytest.approx(0.9)
