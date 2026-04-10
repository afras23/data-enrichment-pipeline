"""
Pydantic models for HTTP request and response bodies.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EnrichmentRunCreateRequest(BaseModel):
    """Body for POST /enrichment/run."""

    companies: list[str] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Company names to enrich in this batch",
    )


class EnrichmentRunSummary(BaseModel):
    """Single run row for list endpoints."""

    id: UUID
    status: str
    correlation_id: str | None
    created_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    total_companies: int
    succeeded_count: int
    failed_count: int
    total_ai_cost_usd: float


class EnrichmentRunCreateResponse(BaseModel):
    """Immediate response after scheduling a run."""

    run_id: UUID
    status: str
    total_companies: int


class CompanyRecordSummary(BaseModel):
    """Per-company enrichment row (list view)."""

    id: UUID
    run_id: UUID
    company_name: str
    status: str
    website_url: str | None
    quality_score: float | None
    created_at: datetime


class CompanyRecordDetail(BaseModel):
    """Full record including JSON payloads."""

    id: UUID
    run_id: UUID
    company_name: str
    status: str
    website_url: str | None
    website_confidence: float | None
    discovery_metadata: dict | None
    scrape_bundle: dict | None
    ai_payload: dict | None
    quality_report: dict | None
    error_code: str | None
    error_message: str | None
    prompt_version: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    ai_cost_usd: float | None
    ai_latency_ms: float | None
    created_at: datetime
    updated_at: datetime


class PaginatedRuns(BaseModel):
    """Paginated list of runs."""

    items: list[EnrichmentRunSummary]
    total: int
    skip: int
    limit: int
    has_more: bool


class PaginatedCompanies(BaseModel):
    """Paginated list of company records."""

    items: list[CompanyRecordSummary]
    total: int
    skip: int
    limit: int
    has_more: bool


class PipelineMetricsResponse(BaseModel):
    """Operational metrics for monitoring dashboards."""

    runs_total: int
    records_total: int
    avg_quality_score: float | None
    total_ai_cost_usd: float
    runs_last_24h: int
    records_completed: int
