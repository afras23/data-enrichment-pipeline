"""
ORM models for enrichment runs and per-company enrichment records.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EnrichmentRunStatus(StrEnum):
    """Lifecycle state for a batch enrichment run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class EnrichmentRecordStatus(StrEnum):
    """Per-company processing outcome."""

    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EnrichmentRun(Base):
    """Batch run metadata and aggregate counters."""

    __tablename__ = "enrichment_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(
        String(32),
        default=EnrichmentRunStatus.PENDING.value,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_companies: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    total_ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    records: Mapped[list["EnrichmentRecord"]] = relationship(
        "EnrichmentRecord",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EnrichmentRecord(Base):
    """Single company enrichment result and audit payload."""

    __tablename__ = "enrichment_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("enrichment_runs.id", ondelete="CASCADE"),
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name_key: Mapped[str] = mapped_column(String(512), index=True)

    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    website_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    discovery_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    scrape_bundle: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quality_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        default=EnrichmentRecordStatus.PENDING.value,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    run: Mapped["EnrichmentRun"] = relationship("EnrichmentRun", back_populates="records")
