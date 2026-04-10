"""Initial enrichment runs and records tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_enrichment"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrichment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_companies", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("total_ai_cost_usd", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "enrichment_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name_key", sa.String(length=512), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("website_confidence", sa.Float(), nullable=True),
        sa.Column("discovery_metadata", sa.JSON(), nullable=True),
        sa.Column("scrape_bundle", sa.JSON(), nullable=True),
        sa.Column("ai_payload", sa.JSON(), nullable=True),
        sa.Column("quality_report", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("ai_cost_usd", sa.Float(), nullable=True),
        sa.Column("ai_latency_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["enrichment_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrichment_records_run_id", "enrichment_records", ["run_id"])
    op.create_index("ix_enrichment_records_company_name", "enrichment_records", ["company_name"])
    op.create_index("ix_enrichment_records_normalized_name_key", "enrichment_records", ["normalized_name_key"])


def downgrade() -> None:
    op.drop_index("ix_enrichment_records_normalized_name_key", table_name="enrichment_records")
    op.drop_index("ix_enrichment_records_company_name", table_name="enrichment_records")
    op.drop_index("ix_enrichment_records_run_id", table_name="enrichment_records")
    op.drop_table("enrichment_records")
    op.drop_table("enrichment_runs")
