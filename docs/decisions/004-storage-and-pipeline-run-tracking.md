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

Use **Option A: PostgreSQL** as the **system of record** (SQLite supported for dev/tests):

- **Run table:** batch metadata, timestamps (UTC), terminal `status`, aggregate `succeeded_count` / `failed_count`, `total_ai_cost_usd`, optional `correlation_id`, `error_message` on the run when needed.
- **Record table:** per-company rows linked to a run; `normalized_name_key`; JSON payloads for discovery metadata, scrape bundle, AI output, quality report; model telemetry and error fields.

**Idempotency (policy):** Duplicate submission of the same names is **not** automatically deduplicated at the API—each `POST /enrichment/run` creates a **new** run. Callers may add idempotency keys in a future API revision if required.

**Migrations:** All schema changes via **Alembic**; application code does not rely on implicit `CREATE TABLE` in production (dev may use `init_db` for SQLite demos).

## Implementation (current codebase)

Concrete table names and columns match migration **`001_enrichment_tables`**:

| Table | Purpose |
|-------|---------|
| `enrichment_runs` | Batch run: `status` includes `pending`, `running`, `completed`, `failed`, `partial` (not `cost_limited` as a separate enum—cost-limited rows use record-level error codes). |
| `enrichment_records` | Per-company: `website_url`, `website_confidence`, `discovery_metadata`, `scrape_bundle`, `ai_payload`, `quality_report`, `status`, errors, token/cost fields. |

ORM models: `app/models/enrichment.py`. Repository: `app/repositories/enrichment_repository.py`.

## Consequences

- **Positive:** Straightforward metrics SQL; easy backup with `pg_dump`; aligns with portfolio checklist.
- **Negative:** DB size grows with JSONB; enforce **max sizes** on stored text previews and strip raw HTML from persistence (store extracted text summary only, per privacy/size policy).
- **Backups:** Document in runbook; automated backups out of scope for dev demo.
