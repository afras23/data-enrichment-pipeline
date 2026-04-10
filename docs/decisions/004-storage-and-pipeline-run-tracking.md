# ADR 004: Storage and Pipeline Run Tracking

## Status

Accepted

## Context

The system processes **batches** of up to **~5,000** company names. Operators need:

- **Run-level** visibility: started/finished, counts by status, cost rollups.
- **Row-level** audit: inputs, chosen URL, scrape metadata, model id, prompt version, tokens, errors.
- **Resumability / idempotency:** safe restarts without duplicating charged work where possible.

The tech stack mandates **PostgreSQL** and **Alembic** migrations.

## Options Considered

### Option A: PostgreSQL only (normalised tables)

Tables such as `pipeline_run`, `company_job`, optional `discovery_candidate`, store JSONB for flexible audit payloads.

- **Pro:** Single source of truth; great for metrics queries; fits SQLAlchemy async.
- **Con:** Schema design must be disciplined to avoid unbounded JSON.

### Option B: Object storage for raw HTML + Postgres for metadata

Store page HTML in S3/MinIO; DB holds pointers.

- **Pro:** Smaller DB; good for heavy crawling.
- **Con:** Extra infra; out of scope for minimal portfolio demo unless required.

### Option C: Event log only (append-only) without relational model

- **Pro:** Simple ingestion story.
- **Con:** Harder to query “latest state per job”; metrics more painful.

### Option D: External queue (Redis/RabbitMQ) as source of truth

- **Pro:** Great for large distributed workers.
- **Con:** Beyond 10–12h baseline; Postgres-backed job state is sufficient for v1.

## Decision

Use **Option A: PostgreSQL** as the **system of record**:

- **`pipeline_run`:** `id`, timestamps (UTC), `status` (`pending`, `running`, `completed`, `failed`, `cost_limited`), `submitted_by` optional, aggregate counters, `total_cost_usd` (optional rollup).
- **`company_job`:** `id`, `pipeline_run_id`, normalised `company_name`, `normalised_name_key` for dedup hints, `status`, `stage` (`discovery`, `scrape`, `enrich`, `score`), `website_url`, `discovery_confidence`, `scrape_metadata` JSONB, `enrichment_payload` JSONB (validated snapshot), `quality_breakdown` JSONB, `error_code`, `error_message` (sanitised), `prompt_version`, `model`, token counts, cost.

**Idempotency:** Re-submitting the **same run payload** may be rejected or returns existing `pipeline_run_id` based on a deterministic hash of (sorted names + optional batch label)—exact behaviour documented in API and implemented once to avoid duplicate charges.

**Migrations:** All schema changes via **Alembic**; no raw `CREATE TABLE` in application startup.

## Consequences

- **Positive:** Straightforward metrics SQL; easy backup with `pg_dump`; aligns with portfolio checklist.
- **Negative:** DB size grows with JSONB; enforce **max sizes** on stored text previews and strip raw HTML from persistence (store extracted text summary only, per privacy/size policy).
- **Backups:** Document in runbook; automated backups out of scope for dev demo.
