"""
Enrichment batch and query endpoints.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CompanyRecordDetail,
    CompanyRecordSummary,
    EnrichmentRunCreateRequest,
    EnrichmentRunCreateResponse,
    EnrichmentRunSummary,
    PaginatedCompanies,
    PaginatedRuns,
)
from app.config import settings
from app.db.session import async_session_factory, get_db_session
from app.models.enrichment import EnrichmentRunStatus
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.alerting import AlertEvaluationService, MockCompositeNotifier
from app.services.enrichment_pipeline import EnrichmentPipelineService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["enrichment"])


def _alert_service(notifier: MockCompositeNotifier) -> AlertEvaluationService:
    return AlertEvaluationService(
        notifier,
        failure_streak_threshold=settings.alert_consecutive_failure_threshold,
        avg_quality_threshold=settings.alert_avg_quality_threshold,
    )


async def _run_pipeline_job(
    run_id: UUID,
    companies: list[str],
    notifier: MockCompositeNotifier,
) -> None:
    svc = EnrichmentPipelineService(
        async_session_factory,
        alerts=_alert_service(notifier),
    )
    await svc.process_run(run_id, companies)


@router.post("/enrichment/run", response_model=EnrichmentRunCreateResponse)
async def create_enrichment_run(
    request: Request,
    body: EnrichmentRunCreateRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> EnrichmentRunCreateResponse:
    """Queue a batch enrichment run for the given company names."""

    repo = EnrichmentRepository(session)
    run = await repo.create_run(
        total_companies=len(body.companies),
        correlation_id=x_correlation_id,
    )
    await session.commit()
    notifier: MockCompositeNotifier = request.app.state.notifier
    background_tasks.add_task(_run_pipeline_job, run.id, body.companies, notifier)
    logger.info(
        "Enrichment run scheduled",
        extra={
            "run_id": str(run.id),
            "companies": len(body.companies),
            "correlation_id": x_correlation_id or "",
        },
    )
    return EnrichmentRunCreateResponse(
        run_id=run.id,
        status=EnrichmentRunStatus.PENDING.value,
        total_companies=len(body.companies),
    )


@router.get("/runs", response_model=PaginatedRuns)
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedRuns:
    """List enrichment runs with pagination."""

    repo = EnrichmentRepository(session)
    rows, total = await repo.list_runs(skip=skip, limit=limit)
    items = [
        EnrichmentRunSummary(
            id=r.id,
            status=r.status,
            correlation_id=r.correlation_id,
            created_at=r.created_at,
            completed_at=r.completed_at,
            duration_seconds=r.duration_seconds,
            total_companies=r.total_companies,
            succeeded_count=r.succeeded_count,
            failed_count=r.failed_count,
            total_ai_cost_usd=r.total_ai_cost_usd,
        )
        for r in rows
    ]
    return PaginatedRuns(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )


@router.get("/companies", response_model=PaginatedCompanies)
async def list_companies(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginatedCompanies:
    """List enrichment records across all runs."""

    repo = EnrichmentRepository(session)
    rows, total = await repo.list_companies(skip=skip, limit=limit)
    items: list[CompanyRecordSummary] = []
    for r in rows:
        qr = r.quality_report
        qscore = None
        if isinstance(qr, dict) and qr.get("final_score") is not None:
            try:
                qscore = float(qr["final_score"])
            except (TypeError, ValueError):
                qscore = None
        items.append(
            CompanyRecordSummary(
                id=r.id,
                run_id=r.run_id,
                company_name=r.company_name,
                status=r.status,
                website_url=r.website_url,
                quality_score=qscore,
                created_at=r.created_at,
            )
        )
    return PaginatedCompanies(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )


@router.get("/companies/{company_id}", response_model=CompanyRecordDetail)
async def get_company_record(
    company_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyRecordDetail:
    """Return a single enrichment record by id."""

    repo = EnrichmentRepository(session)
    rec = await repo.get_company(company_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Company record not found")
    return CompanyRecordDetail(
        id=rec.id,
        run_id=rec.run_id,
        company_name=rec.company_name,
        status=rec.status,
        website_url=rec.website_url,
        website_confidence=rec.website_confidence,
        discovery_metadata=rec.discovery_metadata,
        scrape_bundle=rec.scrape_bundle,
        ai_payload=rec.ai_payload,
        quality_report=rec.quality_report,
        error_code=rec.error_code,
        error_message=rec.error_message,
        prompt_version=rec.prompt_version,
        model=rec.model,
        input_tokens=rec.input_tokens,
        output_tokens=rec.output_tokens,
        ai_cost_usd=rec.ai_cost_usd,
        ai_latency_ms=rec.ai_latency_ms,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )
